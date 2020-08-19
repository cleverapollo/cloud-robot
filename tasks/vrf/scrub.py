# stdlib
import logging
from datetime import datetime, timedelta
# lib
import opentracing
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier
from scrubbers import Vrf as VrfScrubber

__all__ = [
    'scrub_vrf',
]


@app.task
def scrub_vrf(vrf_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.scrub_vrf')
    span.set_tag('vrf_id', vrf_id)
    _scrub_vrf(vrf_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _scrub_vrf(vrf_id: int, span: Span):
    """
    Task to scrub the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.scrub')
    logger.info(f'Commencing scrub of VRF #{vrf_id}')

    # Read the VRF
    # Don't use utils so we can check the response code
    child_span = opentracing.tracer.start_span('read_vrf', child_of=span)
    response = IAAS.vrf.read(
        token=Token.get_instance().token,
        pk=vrf_id,
        span=child_span,
    )
    child_span.finish()

    if response.status_code == 404:
        logger.info(
            f'Received scrub task for VRF #{vrf_id} but it was already deleted from the API',
        )
        span.set_tag('return_reason', 'already_deleted')
        return
    elif response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch VRF #{vrf_id};\n'
            f'Response Text: {response.content.decode()}',
        )
        span.set_tag('return_reason', 'invalid_vrf_id')
        return
    vrf = response.json()['content']

    # Ensure that the state of the vrf is still currently SCRUB_QUEUE
    if vrf['state'] != state.SCRUB_QUEUE:
        logger.warn(
            f'Cancelling scrub of VRF #{vrf_id}. Expected state to be SCRUB, found {vrf["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # Also ensure that all the VMs under this project are scrubbed
    child_span = opentracing.tracer.start_span('read_project_vms', child_of=span)
    vms_request_data = {'project_id': vrf['idProject']}
    vrf_vms = utils.api_list(IAAS.vm, vms_request_data, span=child_span)[0]
    child_span.finish()
    vm_count = len(vrf_vms)
    if vm_count > 0:
        logger.error(
            f'{vm_count} VMs are still in this project, we cannot scrub VRF #{vrf_id} so postponing the scrub',
        )
        # since vms are yet in the project so wait for 1 min and try again.
        scrub_vrf.s(vrf_id).apply_async(eta=datetime.now() + timedelta(seconds=60))

    # There's no in-between state for Scrub tasks, just jump straight to doing the work
    success: bool = False
    child_span = opentracing.tracer.start_span('scrub', child_of=span)
    try:
        success = VrfScrubber.scrub(vrf, child_span)
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to scrub VRF #{vrf_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully scrubbed VRF #{vrf_id}')
        metrics.vrf_scrub_success()
        # Delete the VRF from the DB
        child_span = opentracing.tracer.start_span('delete_vrf_from_api', child_of=span)
        response = IAAS.vrf.delete(
            token=Token.get_instance().token,
            pk=vrf_id,
            span=child_span,
        )
        child_span.finish()

        if response.status_code == 204:
            logger.info(f'VRF #{vrf_id} successfully deleted from the API')
        else:
            logger.error(
                f'HTTP {response.status_code} response received when attempting to delete VRF #{vrf_id};\n'
                f'Response Text: {response.content.decode()}',
            )

        child_span = opentracing.tracer.start_span('delete_project_from_api', child_of=span)
        utils.project_delete(vrf['idProject'], child_span)
        child_span.finish()
    else:
        logger.error(f'Failed to scrub VRF #{vrf_id}')
        metrics.vrf_scrub_failure()

        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        try:
            EmailNotifier.vrf_failure(vrf, 'scrub')
        except Exception:
            logger.error(
                f'Failed to send build failure email for VRF #{vrf["idVRF"]}',
                exc_info=True,
            )
        child_span.finish()
