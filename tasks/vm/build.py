# stdlib
import logging
from typing import Any, Dict
# lib
from cloudcix.api import IAAS
# local
import metrics
import state
import utils
from builders.vm import (
    Linux as LinuxVmBuilder,
    Windows as WindowsVmBuilder,
)
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier

__all__ = [
    'build_vm',
]


def _unresource(vm: Dict[str, Any]):
    """
    unresource the specified vm because something went wrong
    """
    vm_id = vm['idVM']
    metrics.vm_build_failure()
    # Update state to UNRESOURCED in the API
    response = IAAS.vm.partial_update(
        token=Token.get_instance().token,
        pk=vm_id,
        data={'state': state.UNRESOURCED},
    )
    if response.status_code != 204:
        logging.getLogger('tasks.vm.build').error(
            f'Could not update VM #{vm_id} to state UNRESOURCED. Response: {response.content.decode()}.',
        )
    EmailNotifier.build_failure(vm)


@app.task
def build_vm(vm_id: int):
    """
    Task to build the specified vm
    """
    # TODO - Start a tracing span here
    logger = logging.getLogger('tasks.vm.build')
    logger.info(f'Commencing build of VM #{vm_id}')

    # Read the VM
    vm = utils.api_read(IAAS.vm, vm_id)

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_build_failure()
        return

    # Ensure that the state of the vm is still currently REQUESTED (it hasn't been picked up by another runner)
    if vm['state'] != state.REQUESTED:
        logger.warn(f'Cancelling build of VM #{vm_id}. Expected state to be {state.REQUESTED}, found {vm["state"]}.')
        # Return out of this function without doing anything as it was already handled
        return

    # Also ensure that the VRF is built for the VM
    vrf_request_data = {'project': vm['idProject']}
    vm_vrf = utils.api_list(IAAS.vrf, vrf_request_data)[0]
    if vm_vrf['state'] == 3:
        # If the VRF is UNRESOURCED, we cannot build the VM
        logger.error(
            f'VRF #{vm_vrf["idVRF"]} is UNRESOURCED so we cannot build VM #{vm_id}',
        )
        _unresource(vm)
        return
    elif vm_vrf['state'] != 4:
        logger.warn(
            f'VRF #{vm_vrf["idVRF"]} is not yet built, postponing build of VM #{vm_id}. '
            f'VRF is currently in state {vm_vrf["state"]}',
        )
        # Return without changing the state
        return

    # If all is well and good here, update the VM state to BUILDING and pass the data to the builder
    response = IAAS.vm.partial_update(token=Token.get_instance().token, pk=vm_id, data={'state': state.BUILDING})
    if response.status_code != 204:
        logger.error(
            f'Could not update VM #{vm_id} to state BUILDING. Response: {response.content.decode()}.',
        )
        metrics.vm_build_failure()
        return

    # Call the appropriate builder
    success: bool = False
    # Read the VM image to get the hypervisor id
    image = utils.api_read(IAAS.image, vm['idImage'])
    if image is not None:
        hypervisor = image['idHypervisor']
        if hypervisor == 1:  # HyperV -> Windows
            success = WindowsVmBuilder.build(vm, image)
        elif hypervisor == 2:  # KVM -> Linux
            success = LinuxVmBuilder.build(vm, image)
        else:
            logger.error(
                f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
            )

    if success:
        logger.info(f'Successfully built VM #{vm_id}')
        metrics.vm_build_success()
        # Update state to RUNNING in the API
        response = IAAS.vm.partial_update(token=Token.get_instance().token, pk=vm_id, data={'state': state.RUNNING})
        if response.status_code != 204:
            logger.error(
                f'Could not update VM #{vm_id} to state RUNNING. Response: {response.content.decode()}.',
            )
        EmailNotifier.build_success(vm)
    else:
        logger.error(f'Failed to build VM #{vm_id}')
        _unresource(vm)

    # Flush the loggers
    utils.flush_logstash()
