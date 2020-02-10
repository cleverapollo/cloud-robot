# stdlib
import logging
# lib
import opentracing
from cloudcix.api.compute import Compute
# local
import metrics
import state
import utils
from cloudcix_token import Token
from settings import UPDATE_STATUS_CODE


class PhantomVr:
    """
    A phantom VR dispatcher that just updates the state of the objects to whatever state they should end up.
    Used in systems where Robot does not / cannot build VRs
    """

    def build(self, vr_id: int):
        """
        Takes VR data from the CloudCIX API, adds any additional data needed for building it and requests to build it
        in the assigned physical Router.
        :param vr_id: The VR data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vr.build')
        logger.info(f'Updating VR #{vr_id} to state BUILDING')
        # Change the state to BUILDING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.BUILDING},
        )
        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VR #{vr_id} to state BUILDING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vr_build_failure()
        logger.info(f'Updating VR #{vr_id} to state RUNNING')
        # Change the state to RUNNING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VR #{vr_id} to state RUNNING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vr_build_failure()
        else:
            metrics.vr_build_success()

    def quiesce(self, vr_id: int):
        """
        Takes VR data from the CloudCIX API, it and requests to quiesce the Vr
        in the assigned physical Router.
        :param vr_id: The VR data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vr.quiesce')
        # In order to change the state to the correct value we need to read the VR and check its state
        vr = utils.api_read(Compute.virtual_router, vr_id)
        if vr is None:
            return
        if vr['state'] == state.QUIESCE:
            logger.info(f'Updating VR #{vr_id} to state QUIESCING')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vr_id,
                data={'state': state.QUIESCING},
            )
            if response.status_code != UPDATE_STATUS_CODE:
                logger.error(
                    f'Could not update VR #{vr_id} to state QUIESCING. Response: {response.content.decode()}.',
                )
                metrics.vr_quiesce_failure()
                return
            logger.info(f'Updating VR #{vr_id} to state QUIESCED')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vr_id,
                data={'state': state.QUIESCED},
            )
            if response.status_code != UPDATE_STATUS_CODE:
                logger.error(
                    f'Could not update VR #{vr_id} to state QUIESCED. Response: {response.content.decode()}.',
                )
                metrics.vr_quiesce_failure()
                return
            metrics.vr_quiesce_success()
        elif vr['state'] == state.SCRUB:
            logger.info(f'Updating VR #{vr_id} to state SCRUB_PREP')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vr_id,
                data={'state': state.SCRUB_PREP},
            )
            if response.status_code != UPDATE_STATUS_CODE:
                logger.error(
                    f'Could not update VR #{vr_id} to state SCRUB_PREP. Response: {response.content.decode()}.',
                )
                metrics.vr_quiesce_failure()
                return
            logger.info(f'Updating VR #{vr_id} to state SCRUB_QUEUE')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vr_id,
                data={'state': state.SCRUB_QUEUE},
            )
            if response.status_code != UPDATE_STATUS_CODE:
                logger.error(
                    f'Could not update VR #{vr_id} to state SCRUB_QUEUE. Response: {response.content.decode()}.',
                )
                metrics.vr_quiesce_failure()
                return
            metrics.vr_quiesce_success()
        else:
            logger.error(
                f'VR #{vr_id} has been quiesced despite not being in a valid state. '
                f'Valid states: [{state.QUIESCE}, {state.SCRUB}], VR is in state {vr["state"]}',
            )
            metrics.vr_quiesce_failure()

    def restart(self, vr_id: int):
        """
        Takes VR data from the CloudCIX API, it and requests to restart the Vr
        in the assigned physical Router.
        :param vr_id: The VR data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vr.restart')
        logger.info(f'Updating VR #{vr_id} to state RESTARTING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.RESTARTING},
        )
        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VR #{vr_id} to state RESTARTING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vr_restart_failure()
        logger.info(f'Updating VR #{vr_id} to state RUNNING')
        # Change the state of the VR to RUNNING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VR #{vr_id} to state RUNNING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vr_restart_failure()
        else:
            metrics.vr_restart_success()

    def scrub(self, vr_id: int):
        """
        Takes VR data from the CloudCIX API, it and requests to scrub the Vr
        in the assigned physical Router.
        :param vr_id: The VR data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vr.scrub')
        logger.debug(f'Scrubbing phantom VR #{vr_id}')
        # In order to check the project for deletion, we need to read the vr and get the project id from it
        vr = utils.api_read(Compute.virtual_router, vr_id)
        if vr is None:
            return
        span = opentracing.tracer.start_span('phantom_vr_project_delete')
        utils.project_delete(vr['project']['id'], span)
        span.finish()
        metrics.vr_scrub_success()

    def update(self, vr_id: int):
        """
        Takes VR data from the CloudCIX API, it and requests to update the Vr
        in the assigned physical Router.
        :param vr_id: The VR data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vr.update')
        logger.info(f'Updating VR #{vr_id} to state UPDATING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.UPDATING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VR #{vr_id} to state UPDATING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vr_update_failure()
        # Change the state of the VR to RUNNING and report a success to influx
        logger.info(f'Updating VR #{vr_id} to state RUNNING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VR #{vr_id} to state RUNNING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vr_update_failure()
        else:
            metrics.vr_update_success()
