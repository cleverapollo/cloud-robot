# stdlib
import logging
from datetime import datetime
from typing import Any, Dict
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from builders.vm import (
    Linux as LinuxVmBuilder,
    Windows as WindowsVmBuilder,
)
from celery_app import app, tracer
from cloudcix_token import Token
from email_notifier import EmailNotifier

__all__ = [
    'build_vm',
]


def _unresource(vm: Dict[str, Any], span: Span):
    """
    unresource the specified vm because something went wrong
    """
    with tracer.start_span('unresource_vm', child_of=span) as child_span:
        vm_id = vm['idVM']
        metrics.vm_build_failure()
        # Update state to UNRESOURCED in the API
        response = IAAS.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': state.UNRESOURCED},
            span=child_span,
        )
        if response.status_code != 204:
            logging.getLogger('robot.tasks.vm.build').error(
                f'Could not update VM #{vm_id} to state UNRESOURCED. Response: {response.content.decode()}.',
            )
    with tracer.start_span('send_email', child_of=span):
        EmailNotifier.build_failure(vm)


@app.task
def build_vm(vm_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    with tracer.start_span('build_vm') as span:
        _build_vm(vm_id, span)
    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _build_vm(vm_id: int, span: Span):
    """
    Task to build the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.build')
    logger.info(f'Commencing build of VM #{vm_id}')

    # Read the VM
    with tracer.start_span('read_vm', child_of=span) as child_span:
        vm = utils.api_read(IAAS.vm, vm_id, span=child_span)

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_build_failure()
        span.set_tag('return_reason', 'invalid_vm_id')
        return

    # Ensure that the state of the vm is still currently REQUESTED (it hasn't been picked up by another runner)
    if vm['state'] != state.REQUESTED:
        logger.warn(f'Cancelling build of VM #{vm_id}. Expected state to be {state.REQUESTED}, found {vm["state"]}.')
        # Return out of this function without doing anything as it was already handled
        span.set_tag('return_reason', 'not_in_correct_state')
        return

    # Also ensure that the VRF is built for the VM
    with tracer.start_span('read_project_vrf', child_of=span) as child_span:
        vrf_request_data = {'project': vm['idProject']}
        vm_vrf = utils.api_list(IAAS.vrf, vrf_request_data, span=child_span)[0]
    if vm_vrf['state'] == 3:
        # If the VRF is UNRESOURCED, we cannot build the VM
        logger.error(
            f'VRF #{vm_vrf["idVRF"]} is UNRESOURCED so we cannot build VM #{vm_id}',
        )
        _unresource(vm, span)
        span.set_tag('return_reason', 'vrf_unresourced')
        return
    elif vm_vrf['state'] != 4:
        logger.warn(
            f'VRF #{vm_vrf["idVRF"]} is not yet built, postponing build of VM #{vm_id}. '
            f'VRF is currently in state {vm_vrf["state"]}',
        )
        # Return without changing the state
        span.set_tag('return_reason', 'vrf_not_read')
        return

    # If all is well and good here, update the VM state to BUILDING and pass the data to the builder
    with tracer.start_span('update_to_building', child_of=span) as child_span:
        response = IAAS.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': state.BUILDING},
            span=child_span,
        )
    if response.status_code != 204:
        logger.error(
            f'Could not update VM #{vm_id} to state BUILDING. Response: {response.content.decode()}.',
        )
        metrics.vm_build_failure()
        span.set_tag('return_reason', 'could_not_update_state')
        return

    # Call the appropriate builder
    success: bool = False
    # Read the VM image to get the hypervisor id
    with tracer.start_span('read_vm_image', child_of=span) as child_span:
        image = utils.api_read(IAAS.image, vm['idImage'], span=child_span)
    if image is None:
        logger.error(
            f'Could not build VM #{vm_id} as its Image was not readable',
        )
        _unresource(vm, span)
        span.set_tag('return_reason', 'image_not_read')
        return

    hypervisor = image['idHypervisor']
    with tracer.start_span('build', child_of=span) as child_span:
        if hypervisor == 1:  # HyperV -> Windows
            success = WindowsVmBuilder.build(vm, image, child_span)
            child_span.set_tag('hypervisor', 'windows')
        elif hypervisor == 2:  # KVM -> Linux
            success = LinuxVmBuilder.build(vm, image, child_span)
            child_span.set_tag('hypervisor', 'linux')
        else:
            logger.error(
                f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
            )
            child_span.set_tag('hypervisor', 'unsupported')

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully built VM #{vm_id}')
        # Update state to RUNNING in the API
        with tracer.start_span('update_to_running', child_of=span) as child_span:
            response = IAAS.vm.partial_update(
                token=Token.get_instance().token,
                pk=vm_id,
                data={'state': state.RUNNING},
                span=child_span,
            )
        if response.status_code != 204:
            logger.error(
                f'Could not update VM #{vm_id} to state RUNNING. Response: {response.content.decode()}.',
            )
        with tracer.start_span('send_email', child_of=span):
            EmailNotifier.build_success(vm)

        # Calculate the total time it took to build the VM entirely
        # uctnow - vm created time
        total_time = datetime.utcnow() - datetime.strptime(vm['created'], '%Y-%m-%dT%H:%M:%S.%fZ')
        metrics.vm_build_success(total_time.seconds)
    else:
        logger.error(f'Failed to build VM #{vm_id}')
        _unresource(vm, span)
