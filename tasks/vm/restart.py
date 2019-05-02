# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from celery_app import app, tracer
from cloudcix_token import Token
from email_notifier import EmailNotifier
from restarters.vm import (
    Linux as LinuxVmRestarter,
    Windows as WindowsVmRestarter,
)

__all__ = [
    'restart_vm',
]


@app.task
def restart_vm(vm_id: int):
    """
    Task to restart the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.restart')
    logger.info(f'Commencing restart of VM #{vm_id}')

    # Read the VM
    vm = utils.api_read(IAAS.vm, vm_id)

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_restart_failure()
        return

    # Ensure that the state of the vm is still currently RESTARTING
    if vm['state'] != state.RESTARTING:
        logger.warn(
            f'Cancelling restart of VM #{vm_id}. Expected state to be RESTARTING, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # There's no in-between state for restart tasks, just jump straight to doing the work
    success: bool = False
    # Read the VM image to get the hypervisor id
    image = utils.api_read(IAAS.image, vm['idImage'])
    if image is None:
        logger.error(
            f'Could not restart VM #{vm_id} as its Image was not readable',
        )
        return

    hypervisor = image['idHypervisor']
    if hypervisor == 1:  # HyperV -> Windows
        success = WindowsVmRestarter.restart(vm)
    elif hypervisor == 2:  # KVM -> Linux
        success = LinuxVmRestarter.restart(vm)
    else:
        logger.error(
            f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
        )

    if success:
        logger.info(f'Successfully restarted VM #{vm_id}')
        metrics.vm_restart_success()
        # Update state back to RUNNING
        response = IAAS.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': state.RUNNING},
        )
        if response.status_code != 204:
            logger.error(
                f'Could not update VM #{vm_id} to state RUNNING. Response: {response.content.decode()}.',
            )

        # Email the user
        EmailNotifier.restart_success(vm)
    else:
        logger.error(f'Failed to restart VM #{vm_id}')
        metrics.vm_restart_failure()

        # Email the user
        EmailNotifier.restart_failure(vm)
        # There's no fail state here either

    # Flush the logs
    utils.flush_logstash()
