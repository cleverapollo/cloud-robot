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


class PhantomVirtualRouter:
    """
    A phantom virtual router dispatcher that just updates the state of the objects to whatever state they should end up.
    Used in systems where Robot does not / cannot build virtual_routers
    """

    def build(self, virtual_router_id: int):
        """
        Takes virtual_router data from the CloudCIX API, adds any additional data needed for building it and
        requests to build it in the assigned physical Router.
        :param virtual_router_id: The virtual_router data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_virtual_router.build')
        logger.info(f'Updating virtual router #{virtual_router_id} to state BUILDING')
        # Change the state to BUILDING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=virtual_router_id,
            data={'state': state.BUILDING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating virtual_router #{virtual_router_id} '
                f'to state BUILDING\n Response Text: {response.content.decode()}',
            )
            metrics.virtual_router_build_failure()
        logger.info(f'Updating virtual_router #{virtual_router_id} to state RUNNING')
        # Change the state to RUNNING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=virtual_router_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating virtual_router #{virtual_router_id} '
                f'to state RUNNING\n Response Text: {response.content.decode()}',
            )
            metrics.virtual_router_build_failure()
        else:
            metrics.virtual_router_build_success()

    def quiesce(self, virtual_router_id: int):
        """
        Takes virtual_router data from the CloudCIX API, it and requests to quiesce the virtual_router
        in the assigned physical Router.
        :param virtual_router_id: The virtual_router data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_virtual_router.quiesce')
        # In order to change the state to the correct value we need to read the virtual_router and check its state
        virtual_router = utils.api_read(Compute.virtual_router, virtual_router_id)
        if virtual_router is None:
            return
        if virtual_router['state'] == state.QUIESCE:
            logger.info(f'Updating virtual_router #{virtual_router_id} to state QUIESCING')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=virtual_router_id,
                data={'state': state.QUIESCING},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update virtual_router #{virtual_router_id} to state QUIESCING. '
                    f'Response: {response.content.decode()}.',
                )
                metrics.virtual_router_quiesce_failure()
                return
            logger.info(f'Updating virtual_router #{virtual_router_id} to state QUIESCED')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=virtual_router_id,
                data={'state': state.QUIESCED},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update virtual_router #{virtual_router_id} to state QUIESCED. '
                    f'Response: {response.content.decode()}.',
                )
                metrics.virtual_router_quiesce_failure()
                return
            metrics.virtual_router_quiesce_success()
        elif virtual_router['state'] == state.SCRUB:
            logger.info(f'Updating virtual_router #{virtual_router_id} to state SCRUB_PREP')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=virtual_router_id,
                data={'state': state.SCRUB_PREP},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update virtual_router #{virtual_router_id} to state SCRUB_PREP. '
                    f'Response: {response.content.decode()}.',
                )
                metrics.virtual_router_quiesce_failure()
                return
            logger.info(f'Updating virtual_router #{virtual_router_id} to state SCRUB_QUEUE')
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=virtual_router_id,
                data={'state': state.SCRUB_QUEUE},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update virtual_router #{virtual_router_id} to state SCRUB_QUEUE. '
                    f'Response: {response.content.decode()}.',
                )
                metrics.virtual_router_quiesce_failure()
                return
            metrics.virtual_router_quiesce_success()
        else:
            logger.error(
                f'virtual_router #{virtual_router_id} has been quiesced despite not being in a valid state. '
                f'Valid states: [{state.QUIESCE}, {state.SCRUB}], virtual_router is in state {virtual_router["state"]}',
            )
            metrics.virtual_router_quiesce_failure()

    def restart(self, virtual_router_id: int):
        """
        Takes virtual_router data from the CloudCIX API, it and requests to restart the virtual_router
        in the assigned physical Router.
        :param virtual_router_id: The virtual_router data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_virtual_router.restart')
        logger.info(f'Updating virtual_router #{virtual_router_id} to state RESTARTING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=virtual_router_id,
            data={'state': state.RESTARTING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating virtual_router #{virtual_router_id}'
                f'to state RESTARTING\n Response Text: {response.content.decode()}',
            )
            metrics.virtual_router_restart_failure()
        logger.info(f'Updating virtual_router #{virtual_router_id} to state RUNNING')
        # Change the state of the virtual_router to RUNNING and report a success to influx
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=virtual_router_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating virtual_router #{virtual_router_id} '
                f'to state RUNNING\n Response Text: {response.content.decode()}',
            )
            metrics.virtual_router_restart_failure()
        else:
            metrics.virtual_router_restart_success()

    def scrub(self, virtual_router_id: int):
        """
        Takes virtual_router data from the CloudCIX API, it and requests to scrub the virtual_router
        in the assigned physical Router.
        :param virtual_router_id: The virtual_router data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_virtual_router.scrub')
        logger.debug(f'Scrubbing phantom virtual_router #{virtual_router_id}')
        # In order to check the project for deletion, we need to read the virtual_router and get the project id from it
        virtual_router = utils.api_read(Compute.virtual_router, virtual_router_id)
        if virtual_router is None:
            return
        span = opentracing.tracer.start_span('phantom_virtual_router_project_delete')
        utils.project_delete(virtual_router['project']['id'], span)
        span.finish()
        metrics.virtual_router_scrub_success()

    def update(self, virtual_router_id: int):
        """
        Takes virtual_router data from the CloudCIX API, it and requests to update the virtual_router
        in the assigned physical Router.
        :param virtual_router_id: The virtual_router data from the CloudCIX API
        """
        logger = logging.getLogger('robot.dispatchers.phantom_virtual_router.update')
        logger.info(f'Updating virtual_router #{virtual_router_id} to state UPDATING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=virtual_router_id,
            data={'state': state.UPDATING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating virtual_router #{virtual_router_id} '
                f'to state UPDATING\n Response Text: {response.content.decode()}',
            )
            metrics.virtual_router_update_failure()
        # Change the state of the virtual_router to RUNNING and report a success to influx
        logger.info(f'Updating virtual_router #{virtual_router_id} to state RUNNING')
        response = Compute.virtual_router.update(
            token=Token.get_instance().token,
            pk=virtual_router_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating virtual_router #{virtual_router_id} '
                f'to state RUNNING\n Response Text: {response.content.decode()}',
            )
            metrics.virtual_router_update_failure()
        else:
            metrics.virtual_router_update_success()
