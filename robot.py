"""
new robot that uses a class, methods and instance variables to clean up the code
"""
# stdlib
import logging
from typing import cast, Optional, Union
# lib
from cloudcix.api.iaas import IAAS
# local
import dispatchers
import settings
import utils
from state import (
    BUILD_FILTERS,
    QUIESCE_FILTERS,
    RESTART_FILTERS,
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
    # virtual_router dispatcher
    virtual_router_dispatcher: Union[dispatchers.PhantomVirtualRouter, dispatchers.VirtualRouter]
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
        if settings.VIRTUAL_ROUTERS_ENABLED:
            self.virtual_router_dispatcher = dispatchers.VirtualRouter(settings.NETWORK_PASSWORD)
        else:
            self.virtual_router_dispatcher = dispatchers.PhantomVirtualRouter()
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
        self.logger.info('Commencing loop.')
        # Handle loop events in separate functions

        # ############################################################## #
        #                              BUILD                             #
        # ############################################################## #
        self._virtual_router_build()
        self._vm_build()

        # ############################################################## #
        #                             QUIESCE                            #
        # ############################################################## #
        self._virtual_router_quiesce()
        self._vm_quiesce()

        # ############################################################## #
        #                             UPDATE                             #
        # ############################################################## #
        self._virtual_router_update()
        self._vm_update()

        # ############################################################## #
        #                             RESTART                            #
        # ############################################################## #
        self._virtual_router_restart()
        self._vm_restart()

        # Flush the loggers
        utils.flush_logstash()

    # ############################################################## #
    #                              BUILD                             #
    # ############################################################## #

    def _virtual_router_build(self):
        """
        Check the API for virtual_routers to build, and asynchronously build them
        """
        # Retrieve the virtual_routers from the API and run loop to dispatch.
        for virtual_router in utils.api_list(IAAS.virtual_router, BUILD_FILTERS):
            self.virtual_router_dispatcher.build(virtual_router['id'])

    def _vm_build(self):
        """
        Check the API for VMs to build, and asynchronously build them
        """
        # Retrieve the VMs from the API and run loop to dispatch.
        for vm in utils.api_list(IAAS.vm, BUILD_FILTERS):
            self.vm_dispatcher.build(vm['id'])

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    def _virtual_router_quiesce(self):
        """
        Check the API for virtual_routers to quiesce, and asynchronously quiesce them
        """
        # Retrieve the virtual_routers from the API and run loop to dispatch.
        to_quiesce = utils.api_list(IAAS.virtual_router, QUIESCE_FILTERS)
        for virtual_router in to_quiesce:
            self.virtual_router_dispatcher.quiesce(virtual_router['id'])

    def _vm_quiesce(self):
        """
        Check the API for VMs to quiesce, and asynchronously quiesce them
        """
        # Retrieve the VMs from the API and run loop to dispatch.
        for vm in utils.api_list(IAAS.vm, QUIESCE_FILTERS):
            self.vm_dispatcher.quiesce(vm['id'])

    # ############################################################## #
    #                             RESTART                            #
    # ############################################################## #

    def _virtual_router_restart(self):
        """
        Check the API for virtual_routers to restart, and asynchronously restart them
        """
        # Retrieve the virtual_routers from the API and run loop to dispatch.
        for virtual_router in utils.api_list(IAAS.virtual_router, RESTART_FILTERS):
            self.virtual_router_dispatcher.restart(virtual_router['id'])

    def _vm_restart(self):
        """
        Check the API for VMs to restart, and asynchronously restart them
        """
        # Retrieve the VMs from the API and run loop to dispatch.
        for vm in utils.api_list(IAAS.vm, RESTART_FILTERS):
            self.vm_dispatcher.restart(vm['id'])

    # ############################################################## #
    #                              SCRUB                             #
    # Scrub methods are not run every loop, they are run at midnight #
    # ############################################################## #

    def scrub(self, timestamp: Optional[int]):
        """
        Handle the scrub part of Robot by checking for infrastructure that needs to be scrubbed.
        This gets run once a day at midnight, once we're sure it works
        """
        self.logger.info(f'Commencing scrub checks with updated__lte={timestamp}')
        self._vm_scrub(timestamp)
        self._virtual_router_scrub(timestamp)
        # Flush the loggers
        utils.flush_logstash()

    def _virtual_router_scrub(self, timestamp: Optional[int]):
        """
        Check the API for virtual_routers to scrub, and asynchronously scrub them
        :param timestamp: The timestamp to use when listing virtual_routers to delete
        """
        params = {'search[state]': SCRUB_QUEUE}
        if timestamp is not None:
            params['search[updated__lte]'] = timestamp

        # Retrieve the virtual_routers from the API and run loop to dispatch.
        for virtual_router in utils.api_list(IAAS.virtual_router, params):
            self.virtual_router_dispatcher.scrub(virtual_router['id'])

    def _vm_scrub(self, timestamp: Optional[int]):
        """
        Check the API for VMs to scrub, and asynchronously scrub them
        :param timestamp: The timestamp to use when listing virtual_routers to delete
        """
        params = {'search[state]': SCRUB_QUEUE}
        if timestamp is not None:
            params['search[updated__lte]'] = timestamp

        # Retrieve the VMs from the API and run loop to dispatch.
        for vm in utils.api_list(IAAS.vm, params):
            self.vm_dispatcher.scrub(vm['id'])

    # ############################################################## #
    #                             UPDATE                             #
    # ############################################################## #

    def _virtual_router_update(self):
        """
        Check the API for virtual_routers to update, and asynchronously update them
        """
        # Retrieve the virtual_routers from the API and run loop to dispatch.
        for virtual_router in utils.api_list(IAAS.virtual_router, UPDATE_FILTERS):
            self.virtual_router_dispatcher.update(virtual_router['id'])

    def _vm_update(self):
        """
        Check the API for VMs to update, and asynchronously update them
        """
        # Retrieve the VMs from the API and run loop to dispatch.
        for vm in utils.api_list(IAAS.vm, UPDATE_FILTERS):
            self.vm_dispatcher.update(vm['id'])
