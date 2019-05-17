# stdlib
import logging
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

    # Ensure that the state of the vm is still currently RESTARTING
    if vm['state'] != state.RESTARTING:
        logger.warn(
            f'Cancelling restart of VM #{vm_id}. Expected state to be RESTARTING, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for restart tasks, just jump straight to doing the work
    success: bool = False
    # Read the VM image to get the hypervisor id
    child_span = opentracing.tracer.start_span('read_vm_image', child_of=span)
    image = utils.api_read(IAAS.image, vm['idImage'], span=child_span)
    child_span.finish()

    if image is None:
        logger.error(
            f'Could not restart VM #{vm_id} as its Image was not readable',
        )
        span.set_tag('return_reason', 'image_not_read')
        return

    hypervisor = image['idHypervisor']
    child_span = opentracing.tracer.start_span('restart', child_of=span)
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

        # Email the user
        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        EmailNotifier.restart_success(vm)
        child_span.finish()
    else:
        logger.error(f'Failed to restart VM #{vm_id}')
        metrics.vm_restart_failure()

        # Email the user
        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        EmailNotifier.restart_failure(vm)
        child_span.finish()
        # There's no fail state here either
