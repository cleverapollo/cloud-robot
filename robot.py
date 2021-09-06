"""
new robot that uses a class, methods and instance variables to clean up the code
"""
# stdlib
import logging
from typing import Optional, Union
# lib
from cloudcix.api.iaas import IAAS
# local
import dispatchers
import settings
import utils
from state import SCRUB_QUEUE


class Robot:
    """
    Regionally Oriented Builder of Things.
    This is the powerhouse of CloudCIX, the script that handles all of the building of infrastructure for projects.
    """
    # logger instance for logging information that happens during the main loop
    logger: logging.Logger
    # Keep track of whether or not the script has detected a SIGTERM signal
    sigterm_recv: bool = False
    # vm dispatcher
    vm_dispatcher: dispatchers.VM
    # virtual_router dispatcher
    virtual_router_dispatcher: Union[dispatchers.PhantomVirtualRouter, dispatchers.VirtualRouter]
    # virtual routers
    virtual_routers: list
    # vms
    vms: list

    def __init__(
            self,
            virtual_routers: list,
            vms: list,
    ):
        # Instantiate a logger instance
        self.logger = logging.getLogger('robot.mainloop')
        # Instantiate the dispatchers
        self.vm_dispatcher = dispatchers.VM(settings.NETWORK_PASSWORD)
        if settings.VIRTUAL_ROUTERS_ENABLED:
            self.virtual_router_dispatcher = dispatchers.VirtualRouter(settings.NETWORK_PASSWORD)
        else:
            self.virtual_router_dispatcher = dispatchers.PhantomVirtualRouter()
        # Instantiate virtual routers
        self.virtual_routers = virtual_routers
        # Instantiate vms
        self.vms = vms

    def __call__(self):
        """
        This is the main looping part of the robot.
        This method will loop until an exception occurs or a sigterm is received
        """
        self.logger.info('Commencing robot loop.')

        # sort out as per state
        self.virtual_routers_to_build = self.virtual_routers['build']
        self.virtual_routers_to_quiesce = self.virtual_routers['quiesce'] + self.virtual_routers['scrub']
        self.virtual_routers_to_update = self.virtual_routers['running_update']
        self.virtual_routers_to_update += self.virtual_routers['quiesced_update']
        self.virtual_routers_to_restart = self.virtual_routers['restart']

        self.vms_to_build = self.vms['build']
        self.vms_to_quiesce = self.vms['quiesce'] + self.vms['scrub']
        self.vms_to_update = self.vms['running_update']
        self.vms_to_update += self.vms['quiesced_update']
        self.vms_to_restart = self.vms['restart']

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
        Sends virtual_routers to build dispatcher, and asynchronously build them
        """
        for virtual_router_id in self.virtual_routers_to_build:
            self.virtual_router_dispatcher.build(virtual_router_id)

    def _vm_build(self):
        """
        Sends vms to build dispatcher, and asynchronously build them
        """
        for vm_id in self.vms_to_build:
            self.vm_dispatcher.build(vm_id)

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    def _virtual_router_quiesce(self):
        """
        Sends virtual_routers to quiesce dispatcher, and asynchronously quiesce them
        """
        for virtual_router_id in self.virtual_routers_to_quiesce:
            self.virtual_router_dispatcher.quiesce(virtual_router_id)

    def _vm_quiesce(self):
        """
        Sends vms to quiesce dispatcher, and asynchronously quiesce them
        """
        for vm_id in self.vms_to_quiesce:
            self.vm_dispatcher.quiesce(vm_id)

    # ############################################################## #
    #                             RESTART                            #
    # ############################################################## #

    def _virtual_router_restart(self):
        """
        Sends virtual_routers to restart dispatcher, and asynchronously restart them
        """
        for virtual_router_id in self.virtual_routers_to_restart:
            self.virtual_router_dispatcher.restart(virtual_router_id)

    def _vm_restart(self):
        """
        Sends vms to restart dispatcher, and asynchronously restart them
        """
        for vm_id in self.vms_to_restart:
            self.vm_dispatcher.restart(vm_id)

    # ############################################################## #
    #                             UPDATE                             #
    # ############################################################## #

    def _virtual_router_update(self):
        """
        Sends virtual_routers to update dispatcher, and asynchronously update them
        """
        for virtual_router_id in self.virtual_routers_to_update:
            self.virtual_router_dispatcher.update(virtual_router_id)

    def _vm_update(self):
        """
        Sends vms to update dispatcher, and asynchronously update them
        """
        # Retrieve the VMs from the API and run loop to dispatch.
        for vm_id in self.vms_to_update:
            self.vm_dispatcher.update(vm_id)

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
