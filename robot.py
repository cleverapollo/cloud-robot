# python
import multiprocessing as mp
import signal
import sys
import time
from datetime import datetime, timedelta
# local
import dispatchers
import metrics
import ro
import settings
import utils

sigterm_recv = False
robot_logger = utils.get_logger_for_name('robot.mainloop')

BUILD_FILTER = {'state': 1}
QUIESCE_FILTER = {'state__in': [5, 8]}
RESTART_FILTER = {'state': 7}
SCRUB_FILTER = {'state': 9}
UPDATE_FILTER = {'state': 10}


def mainloop(process_pool: mp.Pool):
    """
    The main loop of the Robot program
    """
    global sigterm_recv
    last = time.time()
    # Create the dispatcher instances
    if settings.VRFS_ENABLED:
        vrf_dispatch = dispatchers.Vrf(settings.NETWORK_PASSWORD)
    else:
        vrf_dispatch = dispatchers.DummyVrf()
    vm_dispatch = dispatchers.Vm(settings.NETWORK_PASSWORD)

    while not sigterm_recv:
        metrics.heartbeat()
        # Now handle the loop events
        # #################  VRF BUILD ######################################
        vrfs = ro.service_entity_list('IAAS', 'vrf', params=BUILD_FILTER)
        if len(vrfs) > 0:
            for vrf in vrfs:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VRF #{vrf["idVRF"]} for "Build".')
                vrf_dispatch.build(vrf)
        else:
            robot_logger.info('No VRFs found in "Requested" state.')
        # ######################## VM BUILD  ################################
        vms = ro.service_entity_list('IAAS', 'vm', params=BUILD_FILTER)
        if len(vms) > 0:
            for vm in vms:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VM #{vm["idVM"]} for "Build".')
                # Call the dispatcher asynchronously
                try:
                    vm_dispatch.build(vm)
                    # process_pool.apply_async(func=vm_dispatch.build, kwds={'vm': vm})
                except mp.ProcessError:
                    robot_logger.error(f'Error when building VM #{vm["idVM"]}', exc_info=True)
        else:
            robot_logger.info('No VMs found in "Requested" state.')

        # ######################## VRF QUIESCE  ################################
        vrfs = ro.service_entity_list('IAAS', 'vrf', params=QUIESCE_FILTER)
        if len(vrfs) > 0:
            for vrf in vrfs:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VRF #{vrf["idVRF"]} for "Quiesce".')
                vrf_dispatch.quiesce(vrf)
        else:
            robot_logger.info('No VRFs found in "Quiesce" state.')

        # ######################## VM QUIESCE  ################################
        vms = ro.service_entity_list('IAAS', 'vm', params=QUIESCE_FILTER)
        if len(vms) > 0:
            for vm in vms:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VM #{vm["idVM"]} for "Quiesce".')
                # Call the dispatcher asynchronously
                try:
                    vm_dispatch.quiesce(vm)
                    # process_pool.apply_async(func=vm_dispatch.quiesce, kwds={'vm': vm})
                except mp.ProcessError:
                    robot_logger.error(f'Error when quiescing VM #{vm["idVM"]}', exc_info=True)
        else:
            robot_logger.info('No VMs found in "Quiesce" state.')

        # ######################## VRF SCRUB  ################################
        # Add the Scrub timestamp when the region isn't Alpha
        if settings.REGION_NAME != 'alpha':
            # This needs to be calculated at every loop
            SCRUB_FILTER['updated__lte'] = (datetime.now() - timedelta(days=30)).isoformat()

        vrfs = ro.service_entity_list('IAAS', 'vrf', params=SCRUB_FILTER)
        if len(vrfs) > 0:
            for vrf in vrfs:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VRF #{vrf["idVRF"]} for "Scrub"')
                vrf_dispatch.scrub(vrf)
        else:
            robot_logger.info('No VRFs found in "Scrub" state.')

        # ######################## VM SCRUB  ################################
        vms = ro.service_entity_list('IAAS', 'vm', params=SCRUB_FILTER)
        if len(vms) > 0:
            for vm in vms:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VM #{vm["idVM"]} for "Scrub".')
                # Call the dispatcher asynchronously
                try:
                    vm_dispatch.scrub(vm)
                    # process_pool.apply_async(func=vm_dispatch.scrub, kwds={'vm': vm})
                except mp.ProcessError:
                    robot_logger.error(f'Error when scrubbing VM #{vm["idVM"]}', exc_info=True)
        else:
            robot_logger.info('No VMs found in "Scrub" state.')

        # ######################## VRF UPDATE  ################################
        vrfs = ro.service_entity_list('IAAS', 'vrf', params=UPDATE_FILTER)
        if len(vrfs) > 0:
            for vrf in vrfs:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VRF #{vrf["idVRF"]} for "Update".')
                vrf_dispatch.update(vrf)
        else:
            robot_logger.info('No VRFs found in "Update" state.')

        # ######################## VM UPDATE  ################################
        vms = ro.service_entity_list('IAAS', 'vm', params=UPDATE_FILTER)
        if len(vms) > 0:
            for vm in vms:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VM #{vm["idVM"]} for "Update".')
                # Call the dispatcher asynchronously
                try:
                    vm_dispatch.update(vm)
                    # process_pool.apply_async(func=vm_dispatch.update, kwds={'vm': vm})
                except mp.ProcessError:
                    robot_logger.error(f'Error when updating VM #{vm["idVM"]}', exc_info=True)
        else:
            robot_logger.info('No VMs found in "Update" state.')

        # ######################## VRF RESTART  ################################
        vrfs = ro.service_entity_list('IAAS', 'vrf', params=RESTART_FILTER)
        if len(vrfs) > 0:
            for vrf in vrfs:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VRF #{vrf["idVRF"]} for "Restart"')
                vrf_dispatch.restart(vrf)
        else:
            robot_logger.info('No VRFs found in  "Restart" state.')

        # ######################## VM RESTART  ################################
        vms = ro.service_entity_list('IAAS', 'vm', params=RESTART_FILTER)
        if len(vms) > 0:
            for vm in vms:
                # Stop looping if we receive a sigterm
                if sigterm_recv:
                    break
                robot_logger.info(f'Dispatching VM #{vm["idVM"]} for "Restart"')
                # Call the dispatcher asynchronously
                try:
                    vm_dispatch.restart(vm)
                    # process_pool.apply_async(func=vm_dispatch.restart, kwds={'vm': vm})
                except mp.ProcessError:
                    robot_logger.error(f'Error when Restarting VM #{vm["idVM"]}', exc_info=True)
        else:
            robot_logger.info('No VMs found in "Restart" state.')
        # #############################################################################

        while last > time.time() - 20:
            time.sleep(1)
        last = time.time()

    # When we leave the loop, join the process pool
    process_pool.join()


def handle_sigterm(*args):
    """
    Handles the receive of a SIGTERM and gracefully stops the mainloop after
    it finishes it's current iteration. This is to allow a safe restart
    without the chances of interrupting anything
    """
    global sigterm_recv
    robot_logger.info('SIGTERM received. Gracefully shutting down after current loop.')
    sigterm_recv = True


if __name__ == '__main__':
    # Setup the root logger
    utils.setup_root_logger()
    # When the script is run as the main
    current_commit = utils.get_current_git_sha()
    # Log the current commit to both the file and InfluxDB
    robot_logger.info(f'Robot starting. Current Commit >> {current_commit}. ROBOT_ENV={settings.ROBOT_ENV}')
    if settings.ROBOT_ENV != 'dev':
        metrics.current_commit(current_commit)
    # Create a pool of workers equal in size to the number of cpu cores on the
    # server
    try:
        mp.set_start_method('fork')
    except RuntimeError:
        # Runtime errors thrown when this line is run more than once
        pass
    pool = mp.Pool(processes=None, maxtasksperchild=1)
    rc = 0
    # Set up a SIGTERM listener
    signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        mainloop(pool)
    except KeyboardInterrupt:
        # Going down safely
        pass
    except Exception:
        robot_logger.error(
            'Exception thrown in robot. Exiting.',
            exc_info=True,
        )
        rc = 1
    finally:
        metrics.heartbeat(0)
        pool.close()
        pool.join()
        sys.exit(rc)
