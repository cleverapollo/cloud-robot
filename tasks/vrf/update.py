# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from updaters import Vrf as VrfUpdater
from celery_app import app, tracer
from cloudcix_token import Token

__all__ = [
    'update_vrf',
]


@app.task
def update_vrf(vrf_id: int):
    """
    Task to update the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.update')
    logger.info(f'Commencing update of VRF #{vrf_id}')

    # Read the VRF
    vrf = utils.api_read(IAAS.vrf, vrf_id)

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_update_failure()
        return

    # Ensure that the state of the vrf is still currently REQUESTED (it hasn't been picked up by another runner)
    if vrf['state'] != state.UPDATE:
        logger.warn(f'Cancelling update of VRF #{vrf_id}. Expected state to be UPDATE, found {vrf["state"]}.')
        # Return out of this function without doing anything as it was already handled
        return

    # If all is well and good here, update the VRF state to UPDATING and pass the data to the updater
    response = IAAS.vrf.partial_update(
        token=Token.get_instance().token,
        pk=vrf_id,
        data={'state': state.UPDATING},
    )
    if response.status_code != 204:
        logger.error(
            f'Could not update VRF #{vrf_id} to state UPDATING. Response: {response.content.decode()}.',
        )
        metrics.vrf_update_failure()
        return

    if VrfUpdater.update(vrf):
        logger.info(f'Successfully updated VRF #{vrf_id}')
        metrics.vrf_update_success()

        # Update state to RUNNING in the API
        response = IAAS.vrf.partial_update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'Could not update VRF #{vrf_id} to state RUNNING. Response: {response.content.decode()}.',
            )
    else:
        logger.error(f'Failed to update VRF #{vrf_id}')
        metrics.vrf_update_failure()
        # No fail state for update

    # Flush the logs
    utils.flush_logstash()
