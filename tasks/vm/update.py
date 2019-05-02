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
from updaters.vm import (
    Linux as LinuxVmUpdater,
    Windows as WindowsVmUpdater,
)

__all__ = [
    'update_vm',
]


@app.task
def update_vm(vm_id: int):
    """
    Task to update the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.update')
    logger.info(f'Commencing update of VM #{vm_id}')

    # Read the VM
    vm = utils.api_read(IAAS.vm, vm_id)

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_update_failure()
        return

    # Ensure that the state of the vm is still currently UPDATE
    if vm['state'] != state.UPDATE:
        logger.warn(
            f'Cancelling update of VM #{vm_id}. Expected state to be UPDATE, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # If all is well and good here, update the VM state to UPDATING and pass the data to the updater
    response = IAAS.vm.partial_update(
        token=Token.get_instance().token,
        pk=vm_id,
        data={'state': state.UPDATING},
    )

    if response.status_code != 204:
        logger.error(
            f'Could not update VM #{vm_id} to state UPDATING. Response: {response.content.decode()}.',
        )
        metrics.vm_update_failure()
        return

    success: bool = False
    # Read the VM image to get the hypervisor id
    image = utils.api_read(IAAS.image, vm['idImage'])

    if image is None:
        logger.error(
            f'Could not update VM #{vm_id} as its Image was not readable',
        )
        return

    hypervisor = image['idHypervisor']
    if hypervisor == 1:  # HyperV -> Windows
        success = WindowsVmUpdater.update(vm)
    elif hypervisor == 2:  # KVM -> Linux
        success = LinuxVmUpdater.update(vm)
    else:
        logger.error(
            f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
        )

    if success:
        logger.info(f'Successfully updated VM #{vm_id} from hardware.')
        # Update back to RUNNING
        response = IAAS.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': state.RUNNING},
        )

        if response.status_code != 204:
            logger.error(
                f'Could not update VM #{vm_id} to state RUNNING. Response: {response.content.decode()}.',
            )
            metrics.vm_update_failure()
            return
        metrics.vm_update_success()

        # Email the user
        EmailNotifier.update_success(vm)
    else:
        logger.error(f'Failed to update VM #{vm_id}')
        metrics.vm_update_failure()
        EmailNotifier.update_failure(vm)
        # There's no fail state here either

    # Flush the logs
    utils.flush_logstash()
