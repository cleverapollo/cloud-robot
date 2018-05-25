# python
import subprocess
import sys
import time


# local
from dispatcher import dispatch_vrf, dispatch_vm
from utils import get_logger_for_name, get_current_git_sha, \
    watch_directory, INotify
from ro import service_entity_list
import settings

robot_logger = get_logger_for_name('robot_logger')


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
        # #################  VRF BUILD ######################################
        vrfs = service_entity_list('iaas', 'vrf', params={'state': 1})
        if len(vrfs) > 0:
            for vrf in vrfs:
                robot_logger.info(f"Building VRF with ID {vrf['idVRF']}.")
                dispatch_vrf(vrf, settings.NETWORK_PASSWORD)
        else:
            robot_logger.info('No VRFs in "Requested" state.')
        # ######################## VM BUILD  ################################
        vms = service_entity_list('iaas', 'vm', params={'state': 1})
        if len(vms) > 0:
            for vm in vms:
                robot_logger.info(f"Building VM with ID {vm['idVM']}")
                dispatch_vm(vm, settings.NETWORK_PASSWORD)
        else:
            robot_logger.info('No VMs in "Requested" state.')

        while last > time.time() - 20:
            time.sleep(1)
        last = time.time()


if __name__ == '__main__':
    # When the script is run as the main
    robot_logger.info(
        f'Robot starting. Current Commit >> {get_current_git_sha()}'
    )
    mainloop(watch_directory())
