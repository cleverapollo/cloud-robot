# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from scrubbers import Vrf as VrfScrubber
from celery_app import app, tracer
from cloudcix_token import Token

__all__ = [
    'scrub_vrf',
]


@app.task
def scrub_vrf(vrf_id: int):
    """
    Task to scrub the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.scrub')
    logger.info(f'Commencing scrub of VRF #{vrf_id}')

    # Read the VRF
    # Don't use utils so we can check the response code
    response = IAAS.vrf.read(
        token=Token.get_instance().token,
        pk=vrf_id,
    )

    if response.status_code == 404:
        logger.info(
            f'Received scrub task for VRF #{vrf_id} but it was already deleted from the API',
        )
        return
    elif response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch VRF #{vrf_id};\n'
            f'Response Text: {response.content.decode()}',
        )
        return
    vrf = response.json()['content']

    # Ensure that the state of the vrf is still currently SCRUBBING or QUIESCING
    if vrf['state'] != state.DELETED:
        logger.warn(
            f'Cancelling scrub of VRF #{vrf_id}. Expected state to be SCRUBBING, found {vrf["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # There's no in-between state for Scrub tasks, just jump straight to doing the work
    if VrfScrubber.scrub(vrf):
        logger.info(f'Successfully scrubbed VRF #{vrf_id}')
        metrics.vrf_scrub_success()
        # Delete the VRF from the DB
        response = IAAS.vrf.delete(
            token=Token.get_instance().token,
            pk=vrf_id,
        )

        if response.status_code == 204:
            logger.info(f'VRF #{vrf_id} successfully deleted from the API')
        else:
            logger.error(
                f'HTTP {response.status_code} response received when attempting to delete VRF #{vrf_id};\n'
                f'Response Text: {response.content.decode()}',
            )
        utils.project_delete(vrf['idProject'])
    else:
        logger.error(f'Failed to scrub VRF #{vrf_id}')
        metrics.vrf_scrub_failure()

    # Flush the logs
    utils.flush_logstash()
