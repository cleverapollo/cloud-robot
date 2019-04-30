# stdlib
import logging
# lib
from cloudcix.api import IAAS
# local
import metrics
import state
import utils
from celery_app import app
from cloudcix_token import Token
from scrubbers.vm import (
    Linux as LinuxVmScrubber,
    Windows as WindowsVmScrubber,
)

__all__ = [
    'scrub_vm',
]


@app.task
def scrub_vm(vm_id: int):
    """
    Task to scrub the specified vm
    """
    # TODO - Start a tracing span here
    logger = logging.getLogger('tasks.vm.scrub')
    logger.info(f'Commencing scrub of VM #{vm_id}')

    # Read the VM
    vm = utils.api_read(IAAS.vm, vm_id)

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_scrub_failure()
        return

    # Ensure that the state of the vm is still currently DELETED
    if vm['state'] != state.DELETED:
        logger.warn(
            f'Cancelling scrub of VM #{vm_id}. Expected state to be DELETED, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # There's no in-between state for scrub tasks, just jump straight to doing the work
    success: bool = False
    # Read the VM image to get the hypervisor id
    image = utils.api_read(IAAS.image, vm['idImage'])
    if image is not None:
        hypervisor = image['idHypervisor']
        if hypervisor == 1:  # HyperV -> Windows
            success = WindowsVmScrubber.scrub(vm)
        elif hypervisor == 2:  # KVM -> Linux
            success = LinuxVmScrubber.scrub(vm)
        else:
            logger.error(
                f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
            )

    if success:
        logger.info(f'Successfully scrubbed VM #{vm_id} from hardware.')
        metrics.vm_scrub_success()
        # Do API deletions
        logger.debug(f'Deleting VM #{vm_id} from the CMDB')
        if IAAS.vm.delete(token=Token.get_instance().token, pk=vm_id).status_code != 204:
            logger.error(f'VM #{vm_id} API deletion failed. Check log for details')
            return
        logger.info(f'Successfully deleted VM #{vm_id} from the CMDB.')
        utils.project_delete(vm['idProject'])
    else:
        logger.error(f'Failed to scrub VM #{vm_id}')
        metrics.vm_scrub_failure()
        # There's no fail state here either

    # Flush the loggers
    utils.flush_logstash()
