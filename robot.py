# python
import os
import subprocess
import sys
import time

# lib
from inotify_simple import INotify, flags

# local
import dispatcher
import metrics
import ro
import settings
import utils


robot_logger = utils.get_logger_for_name('robot.mainloop')


def watch_directory() -> INotify:
    """
    Watches the robot directory for changes.
    If a change is deteced, spawn a new Robot instance and kill this one
    :returns: An Inotify instance that can be used to tell if the directory
              has changed
    """
    inotify = INotify()
    # Create flags for the usual things a deployment will change
    watch_flags = flags.CREATE | flags.DELETE | flags.MODIFY
    inotify.add_watch('.', watch_flags)
    return inotify


def mainloop(watcher: INotify):
    """
    The main loop of the Robot program
    """
    last = time.time()
    while True:
        metrics.heartbeat()
        # First check to see if there have been any events
        if watcher.read(timeout=1000):
            robot_logger.info('Update detected. Spawning New Robot.')
            # Wait until all the deployment is finished
            time.sleep(10)
            # Spawn a new robot process in the background
            subprocess.Popen(
                ['python3', 'robot.py'],
                env=os.environ
            )
            # Wait a couple of seconds for the new robot to take over
            time.sleep(2)
            # Exit this process gracefully
            sys.exit(0)
        # Now handle the loop events
        # #################  VRF BUILD ######################################
        vrfs = ro.service_entity_list('iaas', 'vrf', params={'state': 1})
        if len(vrfs) > 0:
            for vrf in vrfs:
                robot_logger.info(f'Building VRF with ID {vrf["idVRF"]}.')
                dispatcher.dispatch_vrf(vrf, settings.NETWORK_PASSWORD)
        else:
            robot_logger.info('No VRFs in "Requested" state.')
        # ######################## VM BUILD  ################################
        vms = ro.service_entity_list('iaas', 'vm', params={'state': 1})
        if len(vms) > 0:
            for vm in vms:
                robot_logger.info(f'Building VM with ID {vm["idVM"]}')
                dispatcher.dispatch_vm(vm, settings.NETWORK_PASSWORD)
        else:
            robot_logger.info('No VMs in "Requested" state.')

        while last > time.time() - 20:
            time.sleep(1)
        last = time.time()


if __name__ == '__main__':
    # When the script is run as the main
    current_commit = utils.get_current_git_sha()
    # Log the current commit to both the file and InfluxDB
    robot_logger.info(
        f'Robot starting. Current Commit >> {current_commit}. '
        f'ROBOT_ENV={settings.ROBOT_ENV}'
    )
    if settings.ROBOT_ENV != 'dev':
        metrics.current_commit(current_commit)
    try:
        mainloop(watch_directory())
    except Exception:
        robot_logger.error(
            'Exception thrown in robot. Exiting.',
            exc_info=True
        )
        metrics.heartbeat(0)
        sys.exit(1)
    except KeyboardInterrupt:
        # Going down safely
        metrics.heartbeat(0)
        sys.exit(0)
