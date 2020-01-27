"""
new robot that uses a class, methods and instance variables to clean up the code
"""
# stdlib
import logging
from typing import cast, Optional, Union
# lib
from cloudcix.api.compute import Compute
# local
import dispatchers
import metrics
import settings
import utils
from state import (
    BUILD_FILTERS,
    QUIESCE_FILTERS,
    RESTART_FILTERS,
    ROUTER_BUSY_FILTERS,
    SCRUB_QUEUE,
    UPDATE_FILTERS,
)


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
    vrf_dispatcher: Union[dispatchers.PhantomVrf, dispatchers.Vrf]
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
            self.vrf_dispatcher = dispatchers.PhantomVrf()
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
        to_build = utils.api_list(Compute.virtual_router, BUILD_FILTERS)
        if len(to_build) == 0:
            self.logger.debug('No VRFs found in the "Requested" state')
            return
        for vrf in to_build:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vrf_dispatcher.build(vrf['id'])
            else:
                break

    def _vm_build(self):
        """
        Check the API for VMs to build, and asyncronously build them
        """
        # Retrive the VMs from the API
        to_build = utils.api_list(Compute.vm, BUILD_FILTERS)
        if len(to_build) == 0:
            self.logger.debug('No VMs found in the "Requested" state')
            return
        for vm in to_build:
            # check if vr is ready.
            vrf_request_data = {'project_id': vm['project']['id']}
            vm_vrf = utils.api_list(Compute.virtual_router, vrf_request_data)[0]
            if vm_vrf['state'] == 4:
                self.vm_dispatcher.build(vm['id'])

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    def _vrf_quiesce(self):
        """
        Check the API for VRFs to quiesce, and asyncronously quiesce them
        """
        # Retrive the VRFs from the API
        to_quiesce = utils.api_list(Compute.virtual_router, QUIESCE_FILTERS)
        if len(to_quiesce) == 0:
            self.logger.debug('No VRFs found in the "Quiesce" state')
            return
        for vrf in to_quiesce:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vrf_dispatcher.quiesce(vrf['id'])
            else:
                break

    def _vm_quiesce(self):
        """
        Check the API for VMs to quiesce, and asyncronously quiesce them
        """
        # Retrive the VMs from the API
        to_quiesce = utils.api_list(Compute.vm, QUIESCE_FILTERS)
        if len(to_quiesce) == 0:
            self.logger.debug('No VMs found in the "Quiesce" state')
            return
        for vm in to_quiesce:
            self.vm_dispatcher.quiesce(vm['id'])

    # ############################################################## #
    #                             RESTART                            #
    # ############################################################## #

    def _vrf_restart(self):
        """
        Check the API for VRFs to restart, and asyncronously restart them
        """
        # Retrive the VRFs from the API
        to_restart = utils.api_list(Compute.virtual_router, RESTART_FILTERS)
        if len(to_restart) == 0:
            self.logger.debug('No VRFs found in the "Restart" state')
            return
        for vrf in to_restart:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vrf_dispatcher.restart(vrf['id'])
            else:
                break

    def _vm_restart(self):
        """
        Check the API for VMs to restart, and asyncronously restart them
        """
        # Retrive the VMs from the API
        to_restart = utils.api_list(Compute.vm, RESTART_FILTERS)
        if len(to_restart) == 0:
            self.logger.debug('No VMs found in the "Restart" state')
            return
        for vm in to_restart:
            self.vm_dispatcher.restart(vm['id'])

    # ############################################################## #
    #                              SCRUB                             #
    # Scrub methods are not run every loop, they are run at midnight #
    # ############################################################## #

    def scrub(self, timestamp: Optional[str]):
        """
        Handle the scrub part of Robot by checking for infrastructure that needs to be scrubbed.
        This gets run once a day at midnight, once we're sure it works
        """
        self.logger.info(f'Commencing scrub checks with updated__lte={timestamp}')
        self._vrf_scrub(timestamp)
        self._vm_scrub(timestamp)
        # Flush the loggers
        utils.flush_logstash()

    def _vrf_scrub(self, timestamp: Optional[str]):
        """
        Check the API for VRFs to scrub, and asyncronously scrub them
        :param timestamp: The timestamp to use when listing VRFs to delete
        """
        params = {'state': SCRUB_QUEUE}
        if timestamp is not None:
            params['updated__lte'] = timestamp

        # Retrive the VRFs from the API
        to_scrub = utils.api_list(Compute.virtual_router, params)
        if len(to_scrub) == 0:
            self.logger.debug('No VRFs found in the "Scrub" state')
            return
        for vrf in to_scrub:
            # since scrub runs only once, sending all requests.
            self.vrf_dispatcher.scrub(vrf['id'])

    def _vm_scrub(self, timestamp: Optional[str]):
        """
        Check the API for VMs to scrub, and asyncronously scrub them
        :param timestamp: The timestamp to use when listing VRFs to delete
        """
        params = {'state': SCRUB_QUEUE}
        if timestamp is not None:
            params['updated__lte'] = timestamp

        # Retrive the VMs from the API
        to_scrub = utils.api_list(Compute.vm, params)
        if len(to_scrub) == 0:
            self.logger.debug('No VMs found in the "Scrub" state')
            return
        for vm in to_scrub:
            self.vm_dispatcher.scrub(vm['id'])

    # ############################################################## #
    #                             UPDATE                             #
    # ############################################################## #

    def _vrf_update(self):
        """
        Check the API for VRFs to update, and asyncronously update them
        """
        # Retrive the VRFs from the API
        to_update = utils.api_list(Compute.virtual_router, UPDATE_FILTERS)
        if len(to_update) == 0:
            self.logger.debug('No VRFs found in the "Update" state')
            return
        for vrf in to_update:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vrf_dispatcher.update(vrf['id'])
            else:
                break

    def _vm_update(self):
        """
        Check the API for VMs to update, and asyncronously update them
        """
        # Retrive the VMs from the API
        to_update = utils.api_list(Compute.vm, UPDATE_FILTERS)
        if len(to_update) == 0:
            self.logger.debug('No VMs found in the "Update" state')
            return
        for vm in to_update:
            self.vm_dispatcher.update(vm['id'])
