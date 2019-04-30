"""
new robot that uses a class, methods and instance variables to clean up the code
"""
# stdlib
import logging
import signal
import sys
import time
from typing import Union
# lib
# local
import dispatchers
import metrics
import ro
import settings
import utils

# Define the filters for different states
BUILD_FILTERS = {'state': 1}
QUIESCE_FILTERS = {'state__in': [5, 8]}
RESTART_FILTERS = {'state': 7}
SCRUB_FILTERS = {'state': 9}
UPDATE_FILTERS = {'state': 10}


class Robot:
    """
    Regionally Oriented Builder of Things.
    This is the powerhouse of CloudCIX, the script that handles all of the building of infrastructure for projects
    """
    # logger instance for logging information that happens during the main loop
    logger: logging.Logger
    # Keep track of whether or not the script has detected a SIGTERM signal
    sigterm_recv: bool = False
    # vm dispatcher
    vm_dispatcher: dispatchers.Vm
    # vrf dispatcher
    vrf_dispatcher: Union[dispatchers.DummyVrf, dispatchers.Vrf]

    def __init__(self):
        # Instantiate a logger instance
        self.logger = logging.getLogger('mainloop')
        # Instantiate the dispatchers
        self.vm_dispatcher = dispatchers.Vm(settings.NETWORK_PASSWORD)
        if settings.VRFS_ENABLED:
            self.vrf_dispatcher = dispatchers.Vrf(settings.NETWORK_PASSWORD)
        else:
            self.vrf_dispatcher = dispatchers.DummyVrf()

    def __call__(self):
        """
        This is the main looping part of the robot.
        This method will loop until an exception occurs or a sigterm is received
        """
        # Send a log message regarding startup
        self.logger.info(f'Robot {settings.ROBOT_ENV} starting at {utils.get_current_git_sha()}')
        # Record the loop start time
        last = time.time()
        while not self.sigterm_recv:
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
            self._vrf_queisce()
            self._vm_queisce()

            # ############################################################## #
            #                              SCRUB                             #
            # ############################################################## #
            # Update the timestamp in the scrub filters
            """
            TODO - Move scrub to a celery beat call that happens once per day
            # Add the Scrub timestamp when the region isn't Alpha
            if settings.REGION_NAME != 'alpha':
                # This needs to be calculated at every loop
                SCRUB_FILTERS['updated__lte'] = (datetime.now() - timedelta(days=30)).isoformat()
            """
            self._vrf_scrub()
            self._vm_scrub()

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

            # Wait 20 seconds (TODO - Move to celery beat?)
            while last > time.time() - 20:
                time.sleep(1)
            last = time.time()

    def handle_sigterm(self, *args):
        """
        Method called when a SIGTERM is received.
        Switches the sigterm_recv flag in the instance to stop the loop
        """
        self.sigterm_recv = True
        self.logger.info('SIGTERM received. Commencing graceful shutdown of Robot.')

    def handle_exception(self):
        """
        If an exception is thrown in the main loop of the system, log it appropriately
        """
        self.logger.error('Exception detected in robot mainloop. Exiting.', exc_info=True)

    # ############################################################## #
    #                              BUILD                             #
    # ############################################################## #

    def _vrf_build(self):
        """
        Check the API for VRFs to build, and asyncronously build them
        """
        # Retrive the VRFs from the API
        to_build = ro.service_entity_list('IAAS', 'vrf', params=BUILD_FILTERS)
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
        to_build = ro.service_entity_list('IAAS', 'vm', params=BUILD_FILTERS)
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
        to_quiesce = ro.service_entity_list('IAAS', 'vrf', params=QUIESCE_FILTERS)
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
        to_quiesce = ro.service_entity_list('IAAS', 'vm', params=QUIESCE_FILTERS)
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
        to_restart = ro.service_entity_list('IAAS', 'vrf', params=RESTART_FILTERS)
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
        to_restart = ro.service_entity_list('IAAS', 'vm', params=RESTART_FILTERS)
        if len(to_restart) == 0:
            self.logger.debug('No VMs found in the "Restart" state')
            return
        for vm in to_restart:
            self.vm_dispatcher.restart(vm['idVM'])

    # ############################################################## #
    #                              SCRUB                             #
    # ############################################################## #

    def _vrf_scrub(self):
        """
        Check the API for VRFs to scrub, and asyncronously scrub them
        """
        # Retrive the VRFs from the API
        to_scrub = ro.service_entity_list('IAAS', 'vrf', params=SCRUB_FILTERS)
        if len(to_scrub) == 0:
            self.logger.debug('No VRFs found in the "Scrub" state')
            return
        for vrf in to_scrub:
            self.vrf_dispatcher.scrub(vrf['idVRF'])

    def _vm_scrub(self):
        """
        Check the API for VMs to scrub, and asyncronously scrub them
        """
        # Retrive the VMs from the API
        to_scrub = ro.service_entity_list('IAAS', 'vm', params=SCRUB_FILTERS)
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
        to_update = ro.service_entity_list('IAAS', 'vrf', params=UPDATE_FILTERS)
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
        to_update = ro.service_entity_list('IAAS', 'vm', params=UPDATE_FILTERS)
        if len(to_update) == 0:
            self.logger.debug('No VMs found in the "Update" state')
            return
        for vm in to_update:
            self.vm_dispatcher.update(vm['idVM'])


if __name__ == '__main__':
    # set up the root logger
    utils.setup_root_logger()
    if settings.ROBOT_ENV != 'dev':
        metrics.current_commit()
    # Create the robot instance
    robot = Robot()

    # Set up a sigterm listener to handle graceful shutdown of the system
    signal.signal(signal.SIGTERM, robot.handle_sigterm)

    # Run the main robot loop
    exit_code = 0
    try:
        robot()
    except Exception:
        # Have robot report the error and then exit with error code 1
        robot.handle_exception()
        exit_code = 1
    finally:
        # Send a heartbeat metric to tell influx that the robot has gone down
        metrics.heartbeat(0)
        sys.exit(exit_code)
