# python
import multiprocessing as mp
import signal
import sys
import time

# local
import dispatchers
import metrics
import ro
import settings
import utils

sigterm_recv = False
robot_logger = utils.get_logger_for_name('robot.mainloop')


def mainloop(process_pool: mp.Pool):
    """
    The main loop of the Robot program
    """
    global sigterm_recv
    last = time.time()
    # Create the dispatcher instances
    vrf_dispatch = dispatchers.Vrf(settings.NETWORK_PASSWORD)
    vm_dispatch = dispatchers.Vm(settings.NETWORK_PASSWORD)
    while not sigterm_recv:
        metrics.heartbeat()
        # Now handle the loop events
        # #################  VRF BUILD ######################################
        vrfs = ro.service_entity_list('IAAS', 'vrf', params={'state': 1})
        if len(vrfs) > 0:
            for vrf in vrfs:
                robot_logger.info(f'Dispatching VRF #{vrf["idVRF"]} for build')
                vrf_dispatch.build(vrf)
        else:
            robot_logger.info('No VRFs in "Requested" state.')
        # ######################## VM BUILD  ################################
        vms = ro.service_entity_list('IAAS', 'vm', params={'state': 1})
        if len(vms) > 0:
            for vm in vms:
                robot_logger.info(f'Dispatching VM #{vm["idVM"]} for build')
                # Call the dispatcher asynchronously
                try:
                    vm_dispatch.build(vm)
                    #process_pool.apply_async(func=vm_dispatch.build, kwds={'vm': vm})
                except mp.ProcessError:
                    robot_logger.error(f'Error when building VM #{vm["idVM"]}', exc_info=True)
        else:
            robot_logger.info('No VMs in "Requested" state.')

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
