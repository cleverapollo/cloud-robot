# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from restarters import Vrf as VrfRestarter
from celery_app import app, tracer
from cloudcix_token import Token

__all__ = [
    'restart_vrf',
]


@app.task
def restart_vrf(vrf_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    with tracer.start_span('restart_vrf') as span:
        _restart_vrf(vrf_id, span)
    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _restart_vrf(vrf_id: int, span: Span):
    """
    Task to restart the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.restart')
    logger.info(f'Commencing restart of VRF #{vrf_id}')

    # Read the VRF
    with tracer.start_span('read_vrf', child_of=span) as child_span:
        vrf = utils.api_read(IAAS.vrf, vrf_id, span=child_span)

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_restart_failure()
        span.set_tag('return_reason', 'invalid_vrf_id')
        return

    # Ensure that the state of the vrf is still currently SCRUBBING or QUIESCING
    if vrf['state'] != state.RESTARTING:
        logger.warn(
            f'Cancelling restart of VRF #{vrf_id}. Expected state to be RESTARTING, found {vrf["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for Restart tasks, just jump straight to doing the work
    with tracer.start_span('restart', child_of=span) as child_span:
        success = VrfRestarter.restart(vrf, child_span)

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully restarted VRF #{vrf_id}')
        metrics.vrf_restart_success()
        # Update state to RUNNING in the API
        with tracer.start_span('update_to_running', child_of=span) as child_span:
            response = IAAS.vrf.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.RUNNING},
                span=child_span,
            )
        if response.status_code != 204:
            logger.error(
                f'Could not update VRF #{vrf_id} to state RUNNING. Response: {response.content.decode()}.',
            )
    else:
        logger.error(f'Failed to restart VRF #{vrf_id}')
        metrics.vrf_restart_failure()
        # There's no fail state here either
