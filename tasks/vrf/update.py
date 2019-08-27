# stdlib
import logging
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
from updaters import Vrf as VrfUpdater

__all__ = [
    'update_vrf',
]


@app.task
def update_vrf(vrf_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.update_vrf')
    span.set_tag('vrf_id', vrf_id)
    _update_vrf(vrf_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _update_vrf(vrf_id: int, span: Span):
    """
    Task to update the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.update')
    logger.info(f'Commencing update of VRF #{vrf_id}')

    # Read the VRF
    child_span = opentracing.tracer.start_span('read_vrf', child_of=span)
    vrf = utils.api_read(IAAS.vrf, vrf_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_update_failure()
        span.set_tag('return_reason', 'invalid_vrf_id')
        return

    # Ensure that the state of the vrf is still currently REQUESTED (it hasn't been picked up by another runner)
    if vrf['state'] != state.UPDATE:
        logger.warn(f'Cancelling update of VRF #{vrf_id}. Expected state to be UPDATE, found {vrf["state"]}.')
        # Return out of this function without doing anything as it was already handled
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # If all is well and good here, update the VRF state to UPDATING and pass the data to the updater
    child_span = opentracing.tracer.start_span('update_to_updating', child_of=span)
    response = IAAS.vrf.partial_update(
        token=Token.get_instance().token,
        pk=vrf_id,
        data={'state': state.UPDATING},
        span=child_span,
    )
    child_span.finish()

    if response.status_code != 204:
        logger.error(
            f'Could not update VRF #{vrf_id} to state UPDATING. Response: {response.content.decode()}.',
        )
        metrics.vrf_update_failure()

        span.set_tag('return_reason', 'could_not_update_state')
        return

    success: bool = False
    child_span = opentracing.tracer.start_span('update', child_of=span)
    try:
        success = VrfUpdater.update(vrf, child_span)
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to update VRF #{vrf_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully updated VRF #{vrf_id}')
        metrics.vrf_update_success()

        # Update state to RUNNING in the API
        child_span = opentracing.tracer.start_span('update_to_running', child_of=span)
        response = IAAS.vrf.partial_update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.RUNNING},
            span=child_span,
        )
        child_span.finish()

        if response.status_code != 204:
            logger.error(
                f'Could not update VRF #{vrf_id} to state RUNNING. Response: {response.content.decode()}.',
            )
    else:
        logger.error(f'Failed to update VRF #{vrf_id}')
        metrics.vrf_update_failure()

        # Update state to UNRESOURCED in the API
        child_span = opentracing.tracer.start_span('update_to_unresourced', child_of=span)
        response = IAAS.vrf.partial_update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.UNRESOURCED},
            span=child_span,
        )
        child_span.finish()

        if response.status_code != 204:
            logger.error(
                f'Could not update VRF #{vrf_id} to state UNRESOURCED. Response: {response.content.decode()}.',
            )

        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        try:
            EmailNotifier.vrf_failure(vrf, 'update')
        except Exception:
            logger.error(
                f'Failed to send build failure email for VRF #{vrf["idVRF"]}',
                exc_info=True,
            )
        child_span.finish()
