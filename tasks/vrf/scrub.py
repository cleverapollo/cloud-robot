# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
from opentracing import tracer
# local
import metrics
import state
import utils
from scrubbers import Vrf as VrfScrubber
from celery_app import app
from cloudcix_token import Token

__all__ = [
    'scrub_vrf',
]


@app.task
def scrub_vrf(vrf_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = tracer.start_span('tasks.scrub_vrf')
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
    child_span = tracer.start_span('read_vrf', child_of=span)
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

    # Ensure that the state of the vrf is still currently SCRUBBING or QUIESCING
    if vrf['state'] != state.DELETED:
        logger.warn(
            f'Cancelling scrub of VRF #{vrf_id}. Expected state to be SCRUBBING, found {vrf["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for Scrub tasks, just jump straight to doing the work
    child_span = tracer.start_span('scrub', child_of=span)
    success = VrfScrubber.scrub(vrf, child_span)
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully scrubbed VRF #{vrf_id}')
        metrics.vrf_scrub_success()
        # Delete the VRF from the DB
        child_span = tracer.start_span('delete_vrf_from_api', child_of=span)
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

        child_span = tracer.start_span('delete_project_from_api', child_of=span)
        utils.project_delete(vrf['idProject'], child_span)
        child_span.finish()
    else:
        logger.error(f'Failed to scrub VRF #{vrf_id}')
        metrics.vrf_scrub_failure()
