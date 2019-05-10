# stdlib
import logging
from datetime import datetime, timedelta
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
from opentracing import tracer
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
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = tracer.start_span('tasks.quiesce_vm')
    span.set_tag('vm_id', vm_id)
    _quiesce_vm(vm_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _quiesce_vm(vm_id: int, span: Span):
    """
    Task to quiesce the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.quiesce')
    logger.info(f'Commencing quiesce of VM #{vm_id}')

    # Read the VM
    child_span = tracer.start_span('read_vm', child_of=span)
    vm = utils.api_read(IAAS.vm, vm_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_quiesce_failure()
        span.set_tag('return_reason', 'invalid_vm_id')
        return

    # Ensure that the state of the vm is still currently SCRUBBING or QUIESCING
    valid_states = [state.QUIESCING, state.SCRUBBING]
    if vm['state'] not in valid_states:
        logger.warn(
            f'Cancelling quiesce of VM #{vm_id}. Expected state to be one of {valid_states}, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for Quiesce tasks, just jump straight to doing the work
    success: bool = False

    # Read the VM image to get the hypervisor id
    child_span = tracer.start_span('read_vm_image', child_of=span)
    image = utils.api_read(IAAS.image, vm['idImage'], span=child_span)
    child_span.finish()

    if image is None:
        logger.error(
            f'Could not quiesce VM #{vm_id} as its Image was not readable',
        )
        span.set_tag('return_reason', 'image_not_read')
        return

    hypervisor = image['idHypervisor']
    child_span = tracer.start_span('quiesce', child_of=span)
    if hypervisor == 1:  # HyperV -> Windows
        success = WindowsVmQuiescer.quiesce(vm, child_span)
        child_span.set_tag('hypervisor', 'windows')
    elif hypervisor == 2:  # KVM -> Linux
        success = LinuxVmQuiescer.quiesce(vm, child_span)
        child_span.set_tag('hypervisor', 'linux')
    else:
        logger.error(
            f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
        )
        child_span.set_tag('hypervisor', 'unsupported')
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully quiesced VM #{vm_id}')
        metrics.vm_quiesce_success()
        # Update state, depending on what state the VM is currently in (QUIESCING -> QUIESCED, SCRUBBING -> DELETED)
        if vm['state'] == 5:
            # Update state to QUIESCED in the API
            child_span = tracer.start_span('update_to_quiesced', child_of=span)
            response = IAAS.vm.partial_update(
                token=Token.get_instance().token,
                pk=vm_id,
                data={'state': state.QUIESCED},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != 204:
                logger.error(
                    f'Could not update VM #{vm_id} to state QUIESCED. Response: {response.content.decode()}.',
                )
            # Email the user
            child_span = tracer.start_span('send_email', child_of=span)
            EmailNotifier.quiesce_success(vm)
            child_span.finish()

        elif vm['state'] == 8:
            # Update state to DELETED in the API
            child_span = tracer.start_span('update_to_deleted', child_of=span)
            response = IAAS.vm.partial_update(
                token=Token.get_instance().token,
                pk=vm_id,
                data={'state': state.DELETED},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != 204:
                logger.error(
                    f'Could not update VM #{vm_id} to state DELETED. Response: {response.content.decode()}.',
                )
            # Add a deletion date in the format 'Monday September 30, 2013'
            vm['deletion_date'] = (datetime.now().date() + timedelta(days=30)).strftime('%A %B %d, %Y')

            # Email the user
            child_span = tracer.start_span('send_email', child_of=span)
            EmailNotifier.delete_schedule_success(vm)
            child_span.finish()
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
