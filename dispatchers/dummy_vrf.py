# stdlib
import logging
# lib
from cloudcix.api import IAAS
# local
import metrics
import state
import utils
from cloudcix_token import Token


class DummyVrf:
    """
    A dummy VRF dispatcher that just updates the state of the objects to whatever state they should end up.
    Used in systems where Robot does not / cannot build VRFs
    """

    def build(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for building it and requests to build it
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('dispatchers.dummy_vrf.build')
        logger.info(f'Updating VRF #{vrf_id} to state RUNNING')
        # Change the state to RUNNING and report a success to influx
        response = IAAS.vrf.update(
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
        logger = logging.getLogger('dispatchers.dummy_vrf.quiesce')
        logger.info(f'Updating VRF #{vrf_id} to state QUIESCED')
        # In order to change the state to the correct value we need to read the VRF and check its state
        vrf = utils.api_read(IAAS.vrf, vrf_id)
        if vrf is None:
            return
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
                metrics.vrf_quiesce_failure()
                return
            metrics.vrf_quiesce_success()
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
                metrics.vrf_quiesce_failure()
                return
            metrics.vrf_quiesce_success()
        else:
            logger.error(
                f'VRF #{vrf_id} has been quiesced despite not being in a valid state. '
                f'Valid states: [{state.QUIESCING}, {state.SCRUBBING}], VRF is in state {vrf["state"]}',
            )
            metrics.vrf_quiesce_failure()

    def restart(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, it and requests to restart the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('dispatchers.dummy_vrf.restart')
        logger.info(f'Updating VRF #{vrf_id} to state RUNNING')
        # Change the state of the VRF to RUNNING and report a success to influx
        response = IAAS.vrf.update(
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
        logger = logging.getLogger('dispatchers.dummy_vrf.scrub')
        logger.info(f'Updating VRF #{vrf_id} to state DELETED')
        # Change the state of the VRF to DELETED and report a success to influx
        response = IAAS.vrf.update(
            token=Token.get_instance().token,
            pk=vrf_id,
            data={'state': state.DELETED},
        )
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when updating VRF #{vrf_id} to state DELETED\n'
                f'Response Text: {response.content.decode()}',
            )
            metrics.vrf_scrub_failure()
        else:
            metrics.vrf_scrub_success()
            # In order to check the project for deletion, we need to read the vrf and get the project id from it
            vrf = utils.api_read(IAAS.vrf, vrf_id)
            if vrf is None:
                return
            utils.project_delete(vrf['idProject'])

    def update(self, vrf_id: int):
        """
        Takes VRF data from the CloudCIX API, it and requests to update the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = logging.getLogger('dispatchers.dummy_vrf.update')
        logger.info(f'Updating VRF #{vrf_id} to state RUNNING')
        # Change the state of the VRF to RUNNING and report a success to influx
        response = IAAS.vrf.update(
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
