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
    # vr dispatcher
    vr_dispatcher: Union[dispatchers.PhantomVr, dispatchers.Vr]
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
        if settings.VRS_ENABLED:
            self.vr_dispatcher = dispatchers.Vr(settings.NETWORK_PASSWORD)
        else:
            self.vr_dispatcher = dispatchers.PhantomVr()
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
        self._vr_build()
        self._vm_build()

        # ############################################################## #
        #                             QUIESCE                            #
        # ############################################################## #
        self._vr_quiesce()
        self._vm_quiesce()

        # ############################################################## #
        #                             UPDATE                             #
        # ############################################################## #
        self._vr_update()
        self._vm_update()

        # ############################################################## #
        #                             RESTART                            #
        # ############################################################## #
        self._vr_restart()
        self._vm_restart()

        # Flush the loggers
        utils.flush_logstash()

    # ############################################################## #
    #                              BUILD                             #
    # ############################################################## #

    def _vr_build(self):
        """
        Check the API for VRs to build, and asyncronously build them
        """
        # Retrive the VRs from the API
        to_build = utils.api_list(Compute.virtual_router, BUILD_FILTERS)
        if len(to_build) == 0:
            self.logger.debug('No VRs found in the "Requested" state')
            return
        for vr in to_build:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vr_dispatcher.build(vr['id'])
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
            vr_request_data = {'project_id': vm['project']['id']}
            vm_vr = utils.api_list(Compute.virtual_router, vr_request_data)[0]
            if vm_vr['state'] == 4:
                self.vm_dispatcher.build(vm['id'])

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    def _vr_quiesce(self):
        """
        Check the API for VRs to quiesce, and asyncronously quiesce them
        """
        # Retrive the VRs from the API
        to_quiesce = utils.api_list(Compute.virtual_router, QUIESCE_FILTERS)
        if len(to_quiesce) == 0:
            self.logger.debug('No VRs found in the "Quiesce" state')
            return
        for vr in to_quiesce:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vr_dispatcher.quiesce(vr['id'])
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

    def _vr_restart(self):
        """
        Check the API for VRs to restart, and asyncronously restart them
        """
        # Retrive the VRs from the API
        to_restart = utils.api_list(Compute.virtual_router, RESTART_FILTERS)
        if len(to_restart) == 0:
            self.logger.debug('No VRs found in the "Restart" state')
            return
        for vr in to_restart:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vr_dispatcher.restart(vr['id'])
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
        self._vr_scrub(timestamp)
        self._vm_scrub(timestamp)
        # Flush the loggers
        utils.flush_logstash()

    def _vr_scrub(self, timestamp: Optional[int]):
        """
        Check the API for VRs to scrub, and asyncronously scrub them
        :param timestamp: The timestamp to use when listing VRs to delete
        """
        params = {'state': SCRUB_QUEUE}
        if timestamp is not None:
            params['updated__lte'] = timestamp

        # Retrive the VRs from the API
        to_scrub = utils.api_list(Compute.virtual_router, params)
        if len(to_scrub) == 0:
            self.logger.debug('No VRs found in the "Scrub" state')
            return
        for vr in to_scrub:
            # since scrub runs only once, sending all requests.
            self.vr_dispatcher.scrub(vr['id'])

    def _vm_scrub(self, timestamp: Optional[int]):
        """
        Check the API for VMs to scrub, and asyncronously scrub them
        :param timestamp: The timestamp to use when listing VRs to delete
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

    def _vr_update(self):
        """
        Check the API for VRs to update, and asyncronously update them
        """
        # Retrive the VRs from the API
        to_update = utils.api_list(Compute.virtual_router, UPDATE_FILTERS)
        if len(to_update) == 0:
            self.logger.debug('No VRs found in the "Update" state')
            return
        for vr in to_update:
            # check if Router is busy.
            busy = utils.api_list(Compute.virtual_router, ROUTER_BUSY_FILTERS)
            if len(busy) == 0:
                self.vr_dispatcher.update(vr['id'])
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
