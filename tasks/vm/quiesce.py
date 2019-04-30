# stdlib
import logging
from datetime import datetime, timedelta
# lib
from cloudcix.api import IAAS
# local
import metrics
import state
import utils
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier
from quiescers.vm import (
    Linux as LinuxVmQuiescer,
    Windows as WindowsVmQuiescer,
)

__all__ = [
    'quiesce_vm',
]


@app.task
def quiesce_vm(vm_id: int):
    """
    Task to quiesce the specified vm
    """
    # TODO - Start a tracing span here
    logger = logging.getLogger('tasks.vm.quiesce')
    logger.info(f'Commencing quiesce of VM #{vm_id}')

    # Read the VM
    vm = utils.api_read(IAAS.vm, vm_id)

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_quiesce_failure()
        return

    # Ensure that the state of the vm is still currently SCRUBBING or QUIESCING
    valid_states = [state.QUIESCING, state.SCRUBBING]
    if vm['state'] not in valid_states:
        logger.warn(
            f'Cancelling quiesce of VM #{vm_id}. Expected state to be one of {valid_states}, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # There's no in-between state for Quiesce tasks, just jump straight to doing the work
    success: bool = False
    # Read the VM image to get the hypervisor id
    image = utils.api_read(IAAS.image, vm['idImage'])
    if image is not None:
        hypervisor = image['idHypervisor']
        if hypervisor == 1:  # HyperV -> Windows
            success = WindowsVmQuiescer.quiesce(vm)
        elif hypervisor == 2:  # KVM -> Linux
            success = LinuxVmQuiescer.quiesce(vm)
        else:
            logger.error(
                f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
            )

    if success:
        logger.info(f'Successfully quiesced VM #{vm_id}')
        metrics.vm_quiesce_success()
        # Update state, depending on what state the VM is currently in (QUIESCING -> QUIESCED, SCRUBBING -> DELETED)
        if vm['state'] == 5:
            # Update state to QUIESCED in the API
            response = IAAS.vm.partial_update(
                token=Token.get_instance().token,
                pk=vm_id,
                data={'state': state.QUIESCED},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update VM #{vm_id} to state QUIESCED. Response: {response.content.decode()}.',
                )
            # Email the user
            EmailNotifier.quiesce_success(vm)
        elif vm['state'] == 8:
            # Update state to DELETED in the API
            response = IAAS.vm.partial_update(
                token=Token.get_instance().token,
                pk=vm_id,
                data={'state': state.DELETED},
            )
            if response.status_code != 204:
                logger.error(
                    f'Could not update VM #{vm_id} to state DELETED. Response: {response.content.decode()}.',
                )
            # Add a deletion date in the format 'Monday September 30, 2013'
            vm['deletion_date'] = (datetime.now().date() + timedelta(days=30)).strftime('%A %B %d, %Y')
            # Email the user
            EmailNotifier.delete_schedule_success(vm)
        else:
            logger.error(
                f'VM #{vm_id} has been quiesced despite not being in a valid state. '
                f'Valid states: {valid_states}, VM is in state {vm["state"]}',
            )
    else:
        logger.error(f'Failed to quiesce VM #{vm_id}')
        metrics.vm_quiesce_failure()
        # There's no fail state here either
        # Should we add an email here? I didn't see one in the previous version

    # Flush the loggers
    utils.flush_logstash()
