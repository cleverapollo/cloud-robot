# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from quiescers import Vrf as VrfQuiescer
from celery_app import app, tracer
from cloudcix_token import Token

__all__ = [
    'quiesce_vrf',
]


@app.task
def quiesce_vrf(vrf_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = tracer.start_span('quiesce_vrf')
    _quiesce_vrf(vrf_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _quiesce_vrf(vrf_id: int, span: Span):
    """
    Task to quiesce the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.quiesce')
    logger.info(f'Commencing quiesce of VRF #{vrf_id}')

    # Read the VRF
    child_span = tracer.start_span('read_vrf', child_of=span)
    vrf = utils.api_read(IAAS.vrf, vrf_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_quiesce_failure()
        span.set_tag('return_reason', 'invalid_vrf_id')
        return

    # Ensure that the state of the vrf is still currently SCRUBBING or QUIESCING
    valid_states = [state.QUIESCING, state.SCRUBBING]
    if vrf['state'] not in valid_states:
        logger.warn(
            f'Cancelling quiesce of VRF #{vrf_id}. Expected state to be one of {valid_states}, found {vrf["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for Quiesce tasks, just jump straight to doing the work
    child_span = tracer.start_span('quiesce', child_of=span)
    success = VrfQuiescer.quiesce(vrf, child_span)
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully quiesced VRF #{vrf_id}')
        metrics.vrf_quiesce_success()
        # Update state, depending on what state the VRF is currently in (QUIESCING -> QUIESCED, SCRUBBING -> DELETED)
        if vrf['state'] == state.QUIESCING:
            child_span = tracer.start_span('update_to_quiescing', child_of=span)
            response = IAAS.vrf.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.QUIESCED},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != 204:
                logger.error(
                    f'Could not update VRF #{vrf_id} to state QUIESCED. Response: {response.content.decode()}.',
                )
        elif vrf['state'] == state.SCRUBBING:
            child_span = tracer.start_span('update_to_deleted', child_of=span)
            response = IAAS.vrf.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.DELETED},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != 204:
                logger.error(
                    f'Could not update VRF #{vrf_id} to state DELETED. Response: {response.content.decode()}.',
                )
        else:
            logger.error(
                f'VRF #{vrf_id} has been quiesced despite not being in a valid state. '
                f'Valid states: {valid_states}, VRF is in state {vrf["state"]}',
            )
    else:
        logger.error(f'Failed to quiesce VRF #{vrf_id}')
        metrics.vrf_quiesce_failure()
        # There's no fail state here either
