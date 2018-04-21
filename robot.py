# python
import subprocess
import sys
import time

# libs
from inotify_simple import INotify, flags

# local
import state
import utils


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
        # First check to see if there have been any events
        if watcher.read(timeout=1000):
            robot_logger.info('Update detected. Spawning New Robot.')
            subprocess.Popen(['python3', 'robot.py'])
            # Wait a couple of seconds for the new robot to take over
            time.sleep(2)
            # Exit this process gracefully
            sys.exit(0)
        # Now handle the loop events
        id_vrf = state.vrf(1)
        if id_vrf is not None:
            robot_logger.info('Building VRF with ID %i.' % id_vrf)
            # TODO: Build the VRF
        else:
            robot_logger.info('No VRFs in "Requested" state.')
        id_vm = state.vm(1)
        if id_vm is not None:
            robot_logger.info('Building VM with ID %i' % id_vm)
            # TODO: Build the VM
        else:
            robot_logger.info('No VMs in "Requested" state.')

        while last > time.time() - 20:
            time.sleep(1)
        last = time.time()


if __name__ == '__main__':
    # When the script is run as the main
    robot_logger = utils.get_logger_for_name('robot')
    robot_logger.info(
        'Robot starting. Current Commit >> %s' % utils.get_current_git_sha())
    mainloop(watch_directory())
