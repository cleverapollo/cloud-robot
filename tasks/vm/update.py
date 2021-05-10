# stdlib
import logging
from typing import Any, Dict
# lib
import opentracing
from cloudcix.api.iaas import IAAS
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


def _unresource(vm: Dict[str, Any], span: Span):
    """
    unresource the specified vm because something went wrong
    """
    logger = logging.getLogger('robot.tasks.vm.update')
    vm_id = vm['id']
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

    if response.status_code != 200:
        logger.error(
            f'Could not update VM #{vm_id} to state UNRESOURCED. Response: {response.content.decode()}.',
        )

    child_span = opentracing.tracer.start_span('send_email', child_of=span)
    try:
        EmailNotifier.vm_failure(vm, 'update')
    except Exception:
        logger.error(
            f'Failed to send failure email for VM #{vm_id}',
            exc_info=True,
        )
    child_span.finish()


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

    # Ensure it is not empty
    if not bool(vm):
        # Rely on the utils method for logging
        metrics.vm_update_failure()
        span.set_tag('return_reason', 'invalid_vm_id')
        return

    # Ensure that the state of the vm is still currently UPDATE
    if vm['state'] != state.UPDATE:
        logger.warning(
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

    if response.status_code != 200:
        logger.error(
            f'Could not update VM #{vm_id} to state UPDATING. Response: {response.content.decode()}.',
        )
        metrics.vm_update_failure()
        span.set_tag('return_reason', 'could_not_update_state')
        return

    success: bool = False
    changes: bool = False
    # check if any changes in any of cpu, ram, storages otherwise ignore
    # the first change in changes_this_month list is the one we need to update about vm
    updates = vm['history'][0]
    for item in updates.keys():
        if item in ['cpu_quantity', 'ram_quantity'] and updates[item] is not None:
            changes = True
            break
        if item in ['storage_histories'] and len(updates[item]) != 0:
            changes = True
            break

    if changes:
        # Read the VM server to get the server type
        child_span = opentracing.tracer.start_span('read_vm_server', child_of=span)
        server = utils.api_read(IAAS.server, vm['server_id'], span=child_span)
        child_span.finish()
        if not bool(server):
            logger.error(
                f'Could not build VM #{vm_id} as its Server was not readable',
            )
            span.set_tag('return_reason', 'server_not_read')
            return
        server_type = server['type']['name']
        # add server details to vm
        vm['server_data'] = server
        vm['errors'] = []
        child_span = opentracing.tracer.start_span('update', child_of=span)
        try:
            if server_type == 'HyperV':
                success = WindowsVmUpdater.update(vm, child_span)
                child_span.set_tag('server_type', 'windows')
            elif server_type == 'KVM':
                success = LinuxVmUpdater.update(vm, child_span)
                child_span.set_tag('server_type', 'linux')
            elif server_type == 'Phantom':
                success = True
                child_span.set_tag('server_type', 'phantom')
            else:
                error = f'Unsupported server type #{server_type} for VM #{vm_id}.'
                logger.error(error)
                vm['errors'].append(error)
                child_span.set_tag('server_type', 'unsupported')
        except Exception as err:
            error = f'An unexpected error occurred when attempting to update VM #{vm_id}.'
            logger.error(error, exc_info=True)
            vm['errors'].append(f'{error} Error: {err}')
        child_span.finish()

        span.set_tag('return_reason', f'success: {success}')

    else:
        # change the state back to previous as
        success = True

    if success:
        logger.info(f'Successfully updated VM #{vm_id}.')
        # Update back to RUNNING
        child_span = opentracing.tracer.start_span('update_to_prev_state', child_of=span)
        return_state = vm.get('return_state', state.RUNNING)
        response = IAAS.vm.partial_update(
            token=Token.get_instance().token,
            pk=vm_id,
            data={'state': return_state},
            span=child_span,
        )
        child_span.finish()

        if response.status_code != 200:
            logger.error(
                f'Could not update VM #{vm_id} to state {return_state}. Response: {response.content.decode()}.',
            )
            metrics.vm_update_failure()
            return
        metrics.vm_update_success()
    else:
        logger.error(f'Failed to update VM #{vm_id}')
        vm.pop('server_data')
        _unresource(vm, span)
