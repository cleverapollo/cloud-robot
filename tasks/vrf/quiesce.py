# stdlib
import logging
# lib
from cloudcix.api import IAAS
# local
import metrics
import state
import utils
from quiescers import Vrf as VrfQuiescer
from celery_app import app
from cloudcix_token import Token


@app.task
def quiesce_vrf(vrf_id: int):
    """
    Task to build the specified vrf
    """
    # TODO - Start a tracing span here
    logger = logging.getLogger('tasks.vrf.quiesce')
    logger.info(f'Commencing quiesce of VRF #{vrf_id}')

    # Read the VRF
    vrf = utils.api_read(IAAS.vrf, vrf_id)

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_quiesce_failure()
        return

    # Ensure that the state of the vrf is still currently SCRUBBING or QUIESCING
    valid_states = [state.QUIESCING, state.SCRUBBING]
    if vrf['state'] not in valid_states:
        logger.warn(
            f'Cancelling quiesce of VRF #{vrf_id}. Expected state to be one of {valid_states}, found {vrf["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # There's no in-between state for Quiesce tasks, just jump straight to doing the work
    if VrfQuiescer.quiesce(vrf):
        logger.info(f'Successfully quiesced VRF #{vrf_id}')
        metrics.vrf_quiesce_success()
        # Update state, depending on what state the VRF is currently in (QUIESCING -> QUIESCED, SCRUBBING -> DELETED)
        if vrf['state'] == state.QUIESCING:
            response = IAAS.vrf.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.QUIESCED},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update VRF #{vrf_id} to state QUIESCED. Response: {response.content.decode()}.',
                )
        elif vrf['state'] == state.SCRUBBING:
            response = IAAS.vrf.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.DELETED},
            )
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

    # Flush the loggers
    utils.flush_logstash()
