# locals
import ro
import utils


class DummyVrf:
    """
    A dummy VRF dispatcher that just updates the state of the objects to whatever state they should end up.
    Used in systems where Robot does not / cannot build VRFs
    """

    def build(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for building it and requests to build it
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.dummy_vrf.build')
        vrf_id = vrf['idVRF']
        logger.info(f'Updating VRF #{vrf_id} to state 4')
        # Change the state to 4 and report a success to influx
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 4})

    def quiesce(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, it and requests to quiesce the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.dummy_vrf.quiesce')
        vrf_id = vrf['idVRF']
        logger.info(f'Updating VRF #{vrf_id} to state 6')
        # Change the state of the VRF to Quiesced (6) and report a success to influx
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 6})

    def scrub(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, it and requests to scrub the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.dummy_vrf.scrub')
        vrf_id = vrf['idVRF']
        logger.info(f'Updating VRF #{vrf_id} to state 9')
        # Change the state of the VRF to 9(Deleted) and report a success to influx
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 9})
