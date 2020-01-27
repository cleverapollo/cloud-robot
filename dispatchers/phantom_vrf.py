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


class PhantomVrf:
    """
    A phantom VRF dispatcher that just updates the state of the objects to whatever state they should end up.
    Used in systems where Robot does not / cannot build VRFs
    """

    def build(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for building it and requests to build it
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vrf.build')
        logger.info(f'Updating VRF #{vrf_id} to state BUILDING')
        # Change the state to BUILDING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.BUILDING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VRF #{vrf_id} to state BUILDING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vrf_build_failure()
        logger.info(f'Updating VRF #{vrf_id} to state RUNNING')
        # Change the state to RUNNING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VRF #{vrf_id} to state RUNNING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vrf_build_failure()
        else:
            metrics.vrf_build_success()

    def quiesce(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, it and requests to quiesce the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vrf.quiesce')
        # In order to change the state to the correct value we need to read the VRF and check its state
        vrf = utils.api_read(Compute.virtual_router, vrf_id)
        if vrf is None:
            return
        if vrf['state'] == state.QUIESCE:
            logger.info(f'Updating VRF #{vrf_id} to state QUIESCING')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.QUIESCING},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update VRF #{vrf_id} to state QUIESCING. Response: {response.content.decode()}.',
                )
                metrics.vrf_quiesce_failure()
                return
            logger.info(f'Updating VRF #{vrf_id} to state QUIESCED')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.QUIESCED},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update VRF #{vrf_id} to state QUIESCED. Response: {response.content.decode()}.',
                )
                metrics.vrf_quiesce_failure()
                return
            metrics.vrf_quiesce_success()
        elif vrf['state'] == state.SCRUB:
            logger.info(f'Updating VRF #{vrf_id} to state SCRUB_PREP')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.SCRUB_PREP},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update VRF #{vrf_id} to state SCRUB_PREP. Response: {response.content.decode()}.',
                )
                metrics.vrf_quiesce_failure()
                return
            logger.info(f'Updating VRF #{vrf_id} to state SCRUB_QUEUE')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'state': state.SCRUB_QUEUE},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update VRF #{vrf_id} to state SCRUB_QUEUE. Response: {response.content.decode()}.',
                )
                metrics.vrf_quiesce_failure()
                return
            metrics.vrf_quiesce_success()
        else:
            logger.error(
                f'VRF #{vrf_id} has been quiesced despite not being in a valid state. '
                f'Valid states: [{state.QUIESCE}, {state.SCRUB}], VRF is in state {vrf["state"]}',
            )
            metrics.vrf_quiesce_failure()

    def restart(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, it and requests to restart the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vrf.restart')
        logger.info(f'Updating VRF #{vrf_id} to state RESTARTING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.RESTARTING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VRF #{vrf_id} to state RESTARTING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vrf_restart_failure()
        logger.info(f'Updating VRF #{vrf_id} to state RUNNING')
        # Change the state of the VRF to RUNNING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VRF #{vrf_id} to state RUNNING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vrf_restart_failure()
        else:
            metrics.vrf_restart_success()

    def scrub(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, it and requests to scrub the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vrf.scrub')
        logger.debug(f'Scrubbing phantom VRF #{vrf_id}')
        # In order to check the project for deletion, we need to read the vrf and get the project id from it
        vrf = utils.api_read(Compute.virtual_router, vrf_id)
        if vrf is None:
            return
        span = opentracing.tracer.start_span('phantom_vrf_project_delete')
        utils.project_delete(vrf['project']['id'], span)
        span.finish()
        metrics.vrf_scrub_success()

    def update(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, it and requests to update the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_vrf.update')
        logger.info(f'Updating VRF #{vrf_id} to state UPDATING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.UPDATING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VRF #{vrf_id} to state UPDATING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vrf_update_failure()
        # Change the state of the VRF to RUNNING and report a success to influx
        logger.info(f'Updating VRF #{vrf_id} to state RUNNING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VRF #{vrf_id} to state RUNNING\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vrf_update_failure()
        else:
            metrics.vrf_update_success()
