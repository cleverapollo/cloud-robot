"""
new robot that uses a class, methods and instance variables to clean up the code
"""
# stdlib
import logging
from typing import cast, Dict, Optional, Union
# lib
from cloudcix.api import IAAS
# local
import dispatchers
import metrics
import settings
import utils

# Define the filters for different states
BUILD_FILTERS = {'state': 1}
QUIESCE_FILTERS = {'state__in': [5, 8]}
RESTART_FILTERS = {'state': 7}
SCRUB_FILTERS: Dict[str, Union[str, int]] = {'state': 9}
UPDATE_FILTERS = {'state': 10}


class Robot:
    """
    Regionally Oriented Builder of Things.
    This is the powerhouse of CloudCIX, the script that handles all of the building of infrastructure for projects
    Robot is a singleton style class to prevent multiple instantiations
    """
    # logger instance for logging information that happens during the main loop
    logger: logging.Logger
    # Keep track of whether or not the script has detected a SIGTERM signal
    sigterm_recv: bool = False
    # vm dispatcher
    vm_dispatcher: dispatchers.Vm
    # vrf dispatcher
    vrf_dispatcher: Union[dispatchers.DummyVrf, dispatchers.Vrf]
    # instance
    __instance = None

    def __init__(self):
        # Ensure we only initialise once
        if Robot.__instance is not None:
            raise Exception('Trying to instantiate a singleton more than once!')
        # Instantiate a logger instance
        self.logger = logging.getLogger('robot.mainloop')
        # Instantiate the dispatchers
        self.vm_dispatcher = dispatchers.Vm(settings.NETWORK_PASSWORD)
        if settings.VRFS_ENABLED:
            self.vrf_dispatcher = dispatchers.Vrf(settings.NETWORK_PASSWORD)
        else:
            self.vrf_dispatcher = dispatchers.DummyVrf()
        # Save the instance
        Robot.__instance = self

    # Write the method that will retrieve the instance
    @staticmethod
    def get_instance():
        if Robot.__instance is None:
            Robot()
        return cast(Robot, Robot.__instance)

    def __call__(self):
        """
        This is the main looping part of the robot.
        This method will loop until an exception occurs or a sigterm is received
        """
        # Send info about uptime
        metrics.heartbeat()
        self.logger.info('Commencing loop.')
        # Handle loop events in separate functions

        # ############################################################## #
        #                              BUILD                             #
        # ############################################################## #
        self._vrf_build()
        self._vm_build()

        # ############################################################## #
        #                             QUIESCE                            #
        # ############################################################## #
        self._vrf_quiesce()
        self._vm_quiesce()

        # ############################################################## #
        #                             UPDATE                             #
        # ############################################################## #
        self._vrf_update()
        self._vm_update()

        # ############################################################## #
        #                             RESTART                            #
        # ############################################################## #
        self._vrf_restart()
        self._vm_restart()

        # Flush the loggers
        utils.flush_logstash()

    # ############################################################## #
    #                              BUILD                             #
    # ############################################################## #

    def _vrf_build(self):
        """
        Check the API for VRFs to build, and asyncronously build them
        """
        # Retrive the VRFs from the API
        to_build = utils.api_list(IAAS.vrf, BUILD_FILTERS)
        if len(to_build) == 0:
            self.logger.debug('No VRFs found in the "Requested" state')
            return
        for vrf in to_build:
            self.vrf_dispatcher.build(vrf['idVRF'])

    def _vm_build(self):
        """
        Check the API for VMs to build, and asyncronously build them
        """
        # Retrive the VMs from the API
        to_build = utils.api_list(IAAS.vm, BUILD_FILTERS)
        if len(to_build) == 0:
            self.logger.debug('No VMs found in the "Requested" state')
            return
        for vm in to_build:
            self.vm_dispatcher.build(vm['idVM'])

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    def _vrf_quiesce(self):
        """
        Check the API for VRFs to quiesce, and asyncronously quiesce them
        """
        # Retrive the VRFs from the API
        to_quiesce = utils.api_list(IAAS.vrf, QUIESCE_FILTERS)
        if len(to_quiesce) == 0:
            self.logger.debug('No VRFs found in the "Quiesce" state')
            return
        for vrf in to_quiesce:
            self.vrf_dispatcher.quiesce(vrf['idVRF'])

    def _vm_quiesce(self):
        """
        Check the API for VMs to quiesce, and asyncronously quiesce them
        """
        # Retrive the VMs from the API
        to_quiesce = utils.api_list(IAAS.vm, QUIESCE_FILTERS)
        if len(to_quiesce) == 0:
            self.logger.debug('No VMs found in the "Quiesce" state')
            return
        for vm in to_quiesce:
            self.vm_dispatcher.quiesce(vm['idVM'])

    # ############################################################## #
    #                             RESTART                            #
    # ############################################################## #

    def _vrf_restart(self):
        """
        Check the API for VRFs to restart, and asyncronously restart them
        """
        # Retrive the VRFs from the API
        to_restart = utils.api_list(IAAS.vrf, RESTART_FILTERS)
        if len(to_restart) == 0:
            self.logger.debug('No VRFs found in the "Restart" state')
            return
        for vrf in to_restart:
            self.vrf_dispatcher.restart(vrf['idVRF'])

    def _vm_restart(self):
        """
        Check the API for VMs to restart, and asyncronously restart them
        """
        # Retrive the VMs from the API
        to_restart = utils.api_list(IAAS.vm, RESTART_FILTERS)
        if len(to_restart) == 0:
            self.logger.debug('No VMs found in the "Restart" state')
            return
        for vm in to_restart:
            self.vm_dispatcher.restart(vm['idVM'])

    # ############################################################## #
    #                              SCRUB                             #
    # Scrub methods are not run every loop, they are run at midnight #
    # ############################################################## #

    def vrf_scrub(self, timestamp: Optional[str]):
        """
        Check the API for VRFs to scrub, and asyncronously scrub them
        :param timestamp: The timestamp to use when listing VRFs to delete
        """
        # Add the timestamp to the filters
        if timestamp is not None:
            SCRUB_FILTERS['updated__lte'] = timestamp
        else:
            SCRUB_FILTERS.pop('updated__lte', None)

        # Retrive the VRFs from the API
        to_scrub = utils.api_list(IAAS.vrf, SCRUB_FILTERS)
        if len(to_scrub) == 0:
            self.logger.debug('No VRFs found in the "Scrub" state')
            return
        for vrf in to_scrub:
            self.vrf_dispatcher.scrub(vrf['idVRF'])

    def vm_scrub(self, timestamp: Optional[str]):
        """
        Check the API for VMs to scrub, and asyncronously scrub them
        :param timestamp: The timestamp to use when listing VRFs to delete
        """
        # Add the timestamp to the filters
        if timestamp is not None:
            SCRUB_FILTERS['updated__lte'] = timestamp
        else:
            SCRUB_FILTERS.pop('updated__lte', None)

        # Retrive the VMs from the API
        to_scrub = utils.api_list(IAAS.vm, SCRUB_FILTERS)
        if len(to_scrub) == 0:
            self.logger.debug('No VMs found in the "Scrub" state')
            return
        for vm in to_scrub:
            self.vm_dispatcher.scrub(vm['idVM'])

    # ############################################################## #
    #                             UPDATE                             #
    # ############################################################## #

    def _vrf_update(self):
        """
        Check the API for VRFs to update, and asyncronously update them
        """
        # Retrive the VRFs from the API
        to_update = utils.api_list(IAAS.vrf, UPDATE_FILTERS)
        if len(to_update) == 0:
            self.logger.debug('No VRFs found in the "Update" state')
            return
        for vrf in to_update:
            self.vrf_dispatcher.update(vrf['idVRF'])

    def _vm_update(self):
        """
        Check the API for VMs to update, and asyncronously update them
        """
        # Retrive the VMs from the API
        to_update = utils.api_list(IAAS.vm, UPDATE_FILTERS)
        if len(to_update) == 0:
            self.logger.debug('No VMs found in the "Update" state')
            return
        for vm in to_update:
            self.vm_dispatcher.update(vm['idVM'])
