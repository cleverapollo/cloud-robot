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
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.update_vm')
    span.set_tag('vm_id', vm_id)
    _update_vm(vm_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _update_vm(vm_id: int, span: Span):
    """
    Task to update the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.update')
    logger.info(f'Commencing update of VM #{vm_id}')

    # Read the VM
    child_span = opentracing.tracer.start_span('read_vm', child_of=span)
    vm = utils.api_read(IAAS.vm, vm_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_update_failure()
        span.set_tag('return_reason', 'invalid_vm_id')
        return

    # Ensure that the state of the vm is still currently UPDATE
    if vm['state'] != state.UPDATE:
        logger.warn(
            f'Cancelling update of VM #{vm_id}. Expected state to be UPDATE, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # If all is well and good here, update the VM state to UPDATING and pass the data to the updater
    child_span = opentracing.tracer.start_span('update_to_updating', child_of=span)
    response = IAAS.vm.partial_update(
        token=Token.get_instance().token,
        pk=vm_id,
        data={'state': state.UPDATING},
        span=child_span,
    )
    child_span.finish()

    if response.status_code != 204:
        logger.error(
            f'Could not update VM #{vm_id} to state UPDATING. Response: {response.content.decode()}.',
        )
        metrics.vm_update_failure()
        span.set_tag('return_reason', 'could_not_update_state')
        return

    success: bool = False
    # Read the VM image to get the hypervisor id
    child_span = opentracing.tracer.start_span('read_vm_image', child_of=span)
    image = utils.api_read(IAAS.image, vm['idImage'], span=child_span)
    child_span.finish()

    if image is None:
        logger.error(
            f'Could not update VM #{vm_id} as its Image was not readable',
        )
        span.set_tag('return_reason', 'image_not_read')
        return

    hypervisor = image['idHypervisor']
    child_span = opentracing.tracer.start_span('update', child_of=span)
    try:
        if hypervisor == 1:  # HyperV -> Windows
            success = WindowsVmUpdater.update(vm, child_span)
            child_span.set_tag('hypervisor', 'windows')
        elif hypervisor == 2:  # KVM -> Linux
            success = LinuxVmUpdater.update(vm, child_span)
            child_span.set_tag('hypervisor', 'linux')
        else:
            logger.error(
                f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
            )
            child_span.set_tag('hypervisor', 'unsupported')
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to update VM #{vm_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully updated VM #{vm_id} from hardware.')
        # Update back to RUNNING
        child_span = opentracing.tracer.start_span('update_to_running', child_of=span)
        response = IAAS.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': state.RUNNING},
            span=child_span,
        )
        child_span.finish()

        if response.status_code != 204:
            logger.error(
                f'Could not update VM #{vm_id} to state RUNNING. Response: {response.content.decode()}.',
            )
            metrics.vm_update_failure()
            return
        metrics.vm_update_success()

        # Email the user
        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        EmailNotifier.update_success(vm)
        child_span.finish()
    else:
        logger.error(f'Failed to update VM #{vm_id}')
        metrics.vm_update_failure()

        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        EmailNotifier.update_failure(vm)
        child_span.finish()
        # There's no fail state here either
