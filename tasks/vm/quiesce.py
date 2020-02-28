# stdlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict
# lib
import opentracing
from cloudcix.api.compute import Compute
from jaeger_client import Span
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


def _unresource(vm: Dict[str, Any], span: Span):
    """
    unresource the specified vm because something went wrong
    """
    logger = logging.getLogger('robot.tasks.vm.quiesce')
    vm_id = vm['id']
    # Send failure metric
    metrics.vm_quiesce_failure()

    # Update state to UNRESOURCED in the API
    child_span = opentracing.tracer.start_span('update_to_unresourced', child_of=span)
    response = Compute.vm.partial_update(
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
        EmailNotifier.vm_failure(vm, 'quiesce')
    except Exception:
        logger.error(
            f'Failed to send failure email for VM #{vm_id}',
            exc_info=True,
        )
    child_span.finish()


@app.task
def quiesce_vm(vm_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.quiesce_vm')
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
    child_span = opentracing.tracer.start_span('read_vm', child_of=span)
    vm = utils.api_read(Compute.vm, vm_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vm is None:
        # Rely on the utils method for logging
        metrics.vm_quiesce_failure()
        span.set_tag('return_reason', 'invalid_vm_id')
        return

    # Ensure that the state of the vm is still currently SCRUB or QUIESCE
    valid_states = [state.QUIESCE, state.SCRUB]
    if vm['state'] not in valid_states:
        logger.warning(
            f'Cancelling quiesce of VM #{vm_id}. Expected state to be one of {valid_states}, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    if vm['state'] == state.QUIESCE:
        # Update the state to QUIESCING (12)
        child_span = opentracing.tracer.start_span('update_to_quiescing', child_of=span)
        response = Compute.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': state.QUIESCING},
            span=child_span,
        )
        child_span.finish()

        # Ensure the update was successful
        if response.status_code != 204:
            logger.error(
                f'Could not update VM #{vm_id} to QUIESCING. Response: {response.content.decode()}.',
            )
            span.set_tag('return_reason', 'could_not_update_state')
            metrics.vm_quiesce_failure()
            return
    else:
        # Update the state to SCRUB_PREP (14)
        child_span = opentracing.tracer.start_span('update_to_scrub_prep', child_of=span)
        response = Compute.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': state.SCRUB_PREP},
            span=child_span,
        )
        child_span.finish()
        # Ensure the update was successful
        if response.status_code != 204:
            logger.error(
                f'Could not update VM #{vm_id} to SCRUB_PREP. Response: {response.content.decode()}.',
            )
            span.set_tag('return_reason', 'could_not_update_state')
            metrics.vm_quiesce_failure()
            return

    # Read the VM server to get the server type
    child_span = opentracing.tracer.start_span('read_vm_server', child_of=span)
    server = utils.api_read(Compute.server, vm['server_id'], span=child_span)
    child_span.finish()
    if server is None:
        logger.error(
            f'Could not quiesce VM #{vm_id} as its Server was not readable',
        )
        _unresource(vm, span)
        span.set_tag('return_reason', 'server_not_read')
        return
    server_type = server['type']['name']
    # add server details to vm
    vm['server_data'] = server

    # Call the appropriate quiescing
    success: bool = False
    send_email = True
    child_span = opentracing.tracer.start_span('quiesce', child_of=span)
    try:
        if server_type == 'HyperV':
            success = WindowsVmQuiescer.quiesce(vm, child_span)
            child_span.set_tag('server_type', 'windows')
        elif server_type == 'KVM':
            success = LinuxVmQuiescer.quiesce(vm, child_span)
            child_span.set_tag('server_type', 'linux')
        elif server_type == 'Phantom':
            success = True
            send_email = False
            child_span.set_tag('server_type', 'phantom')
        else:
            logger.error(
                f'Unsupported server type ({server_type}) for VM #{vm_id}',
            )
            child_span.set_tag('server_type', 'unsupported')
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to quiesce VM #{vm_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully quiesced VM #{vm_id}')
        metrics.vm_quiesce_success()

        # Update state, depending on what state the VM is currently in (QUIESCE -> QUIESCED, SCRUB -> SCRUB_QUEUE)
        # Note: Will still be the original state as our data hasn't been logged
        if vm['state'] == state.QUIESCE:
            # Update state to QUIESCED in the API
            child_span = opentracing.tracer.start_span('update_to_quiesced', child_of=span)
            response = Compute.vm.partial_update(
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

        elif vm['state'] == state.SCRUB:
            # Update state to SCRUB_QUEUE in the API
            child_span = opentracing.tracer.start_span('update_to_deleted', child_of=span)
            response = Compute.vm.partial_update(
                token=Token.get_instance().token,
                pk=vm_id,
                data={'state': state.SCRUB_QUEUE},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != 204:
                logger.error(
                    f'Could not update VM #{vm_id} to state SCRUB_QUEUE. Response: {response.content.decode()}.',
                )
            # Add a deletion date in the format 'Monday September 30, 2013'
            vm['deletion_date'] = (datetime.now().date() + timedelta(days=7)).strftime('%A %B %d, %Y')

            # Email the user
            if send_email:
                child_span = opentracing.tracer.start_span('send_email', child_of=span)
                try:
                    EmailNotifier.delete_schedule_success(vm)
                except Exception:
                    logger.error(
                        f'Failed to send delete schedule success email for VM #{vm_id}',
                        exc_info=True,
                    )
                child_span.finish()
        else:
            logger.error(
                f'VM #{vm_id} has been quiesced despite not being in a valid state. '
                f'Valid states: {valid_states}, VM was in state {vm["state"]}',
            )
    else:
        logger.error(f'Failed to quiesce VM #{vm_id}')
        _unresource(vm, span)
