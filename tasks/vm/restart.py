# stdlib
import logging
from typing import Any, Dict
# lib
import opentracing
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier
from restarters.vm import (
    Linux as LinuxVmRestarter,
    Windows as WindowsVmRestarter,
)

__all__ = [
    'restart_vm',
]


def _unresource(vm: Dict[str, Any], span: Span):
    """
    unresource the specified vm because something went wrong
    """
    logger = logging.getLogger('robot.tasks.vm.restart')
    vm_id = vm['idVM']
    # Send failure metric
    metrics.vm_restart_failure()

    # Update state to UNRESOURCED in the API
    child_span = opentracing.tracer.start_span('update_to_unresourced', child_of=span)
    response = IAAS.vm.partial_update(
        token=Token.get_instance().token,
        pk=vm_id,
        data={'state': state.UNRESOURCED},
        span=child_span,
    )
    child_span.finish()

    if response.status_code != 204:
        logger.error(
            f'Could not update VM #{vm_id} to state UNRESOURCED. Response: {response.content.decode()}.',
        )

    child_span = opentracing.tracer.start_span('send_email', child_of=span)
    try:
        EmailNotifier.failure(vm, 'restart')
    except Exception:
        logger.error(
            f'Failed to send failure email for VM #{vm["idVM"]}',
            exc_info=True,
        )
    child_span.finish()


@app.task
def restart_vm(vm_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.restart_vm')
    span.set_tag('vm_id', vm_id)
    _restart_vm(vm_id, span)
    span.finish()
    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _restart_vm(vm_id: int, span: Span):
    """
    Task to restart the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.restart')
    logger.info(f'Commencing restart of VM #{vm_id}')

    # Read the VM
    child_span = opentracing.tracer.start_span('read_vm', child_of=span)
    vm = utils.api_read(IAAS.vm, vm_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_restart_failure()
        span.set_tag('return_reason', 'invalid_vm_id')
        return

    # Ensure that the state of the vm is still currently RESTART
    if vm['state'] != state.RESTART:
        logger.warn(
            f'Cancelling restart of VM #{vm_id}. Expected state to be RESTART, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # Update to intermediate state here (RESTARTING - 13)
    child_span = opentracing.tracer.start_span('update_to_restarting', child_of=span)
    response = IAAS.vm.partial_update(
        token=Token.get_instance().token,
        pk=vm_id,
        data={'state': state.RESTARTING},
        span=child_span,
    )
    child_span.finish()

    # Ensure the update was successful
    if response.status_code != 204:
        logger.error(
            f'Could not update VM #{vm_id} to RESTARTING. Response: {response.content.decode()}.',
        )
        span.set_tag('return_reason', 'could_not_update_state')
        metrics.vm_restart_failure()
        # Update to Unresourced?
        return

    # Read the VM image to get the hypervisor id
    child_span = opentracing.tracer.start_span('read_vm_image', child_of=span)
    image = utils.api_read(IAAS.image, vm['idImage'], span=child_span)
    child_span.finish()

    if image is None:
        logger.error(
            f'Could not restart VM #{vm_id} as its Image was not readable',
        )
        span.set_tag('return_reason', 'image_not_read')
        _unresource(vm, span)
        return

    hypervisor = image['idHypervisor']

    # Do the actual restarting
    success: bool = False
    child_span = opentracing.tracer.start_span('restart', child_of=span)
    try:
        if hypervisor == 1:  # HyperV -> Windows
            success = WindowsVmRestarter.restart(vm, child_span)
            child_span.set_tag('hypervisor', 'windows')
        elif hypervisor == 2:  # KVM -> Linux
            success = LinuxVmRestarter.restart(vm, child_span)
            child_span.set_tag('hypervisor', 'linux')
        else:
            logger.error(
                f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
            )
            child_span.set_tag('hypervisor', 'unsupported')
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to restart VM #{vm_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully restarted VM #{vm_id}')
        metrics.vm_restart_success()
        # Update state back to RUNNING
        child_span = opentracing.tracer.start_span('update_to_running', child_of=span)
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
    else:
        logger.error(f'Failed to restart VM #{vm_id}')
        _unresource(vm, span)
