# stdlib
import logging
# lib
from cloudcix.api import IAAS
# local
import metrics
import state
import utils
from restarters import Vrf as VrfRestarter
from celery_app import app
from cloudcix_token import Token


@app.task
def restart_vrf(vrf_id: int):
    """
    Task to build the specified vrf
    """
    # TODO - Start a tracing span here
    logger = logging.getLogger('tasks.vrf.restart')
    logger.info(f'Commencing restart of VRF #{vrf_id}')

    # Read the VRF
    vrf = utils.api_read(IAAS.vrf, vrf_id)

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_restart_failure()
        return

    # Ensure that the state of the vrf is still currently SCRUBBING or QUIESCING
    if vrf['state'] != state.RESTARTING:
        logger.warn(
            f'Cancelling restart of VRF #{vrf_id}. Expected state to be RESTARTING, found {vrf["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # There's no in-between state for Restart tasks, just jump straight to doing the work
    if VrfRestarter.restart(vrf):
        logger.info(f'Successfully restarted VRF #{vrf_id}')
        metrics.vrf_restart_success()
        # Update state to RUNNING in the API
        response = IAAS.vrf.partial_update(token=Token.get_instance().token, pk=vrf_id, data={'state': state.RUNNING})
        if response.status_code != 204:
            logger.error(
                f'Could not update VRF #{vrf_id} to state RUNNING. Response: {response.content.decode()}.',
            )
    else:
        logger.error(f'Failed to restart VRF #{vrf_id}')
        metrics.vrf_restart_failure()
        # There's no fail state here either

    # Flush the loggers
    utils.flush_logstash()
