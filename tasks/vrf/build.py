# stdlib
import logging
# lib
from cloudcix.api import IAAS
# local
import metrics
import state
import utils
from builders import Vrf as VrfBuilder
from celery_app import app
from cloudcix_token import Token

__all__ = [
    'build_vrf',
]


@app.task
def build_vrf(vrf_id: int):
    """
    Task to build the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.build')
    logger.info(f'Commencing build of VRF #{vrf_id}')

    # Read the VRF
    vrf = utils.api_read(IAAS.vrf, vrf_id)

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_build_failure()
        return

    # Ensure that the state of the vrf is still currently REQUESTED (it hasn't been picked up by another runner)
    if vrf['state'] != state.REQUESTED:
        logger.warn(f'Cancelling build of VRF #{vrf_id}. Expected state to be {state.REQUESTED}, found {vrf["state"]}.')
        # Return out of this function without doing anything as it was already handled
        return

    # If all is well and good here, update the VRF state to BUILDING and pass the data to the builder
    response = IAAS.vrf.partial_update(
        token=Token.get_instance().token,
        pk=vrf_id,
        data={'state': state.BUILDING},
    )

    if response.status_code != 204:
        logger.error(
            f'Could not update VRF #{vrf_id} to state BUILDING. Response: {response.content.decode()}.',
        )
        metrics.vrf_build_failure()
        return

    if VrfBuilder.build(vrf):
        logger.info(f'Successfully built VRF #{vrf_id}')
        metrics.vrf_build_success()

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
        logger.error(f'Failed to build VRF #{vrf_id}')
        metrics.vrf_build_failure()

        # Update state to UNRESOURCED in the API
        response = IAAS.vrf.partial_update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.UNRESOURCED},
        )

        if response.status_code != 204:
            logger.error(
                f'Could not update VRF #{vrf_id} to state UNRESOURCED. Response: {response.content.decode()}.',
            )

    # Flush the logs
    utils.flush_logstash()
