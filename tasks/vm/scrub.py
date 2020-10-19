# stdlib
import logging
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
from scrubbers.vm import (
    Linux as LinuxVmScrubber,
    Windows as WindowsVmScrubber,
)

__all__ = [
    'scrub_vm',
]


@app.task
def scrub_vm(vm_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.scrub_vm')
    span.set_tag('vm_id', vm_id)
    _scrub_vm(vm_id, span)
    span.finish()
    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _scrub_vm(vm_id: int, span: Span):
    """
    Task to scrub the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.scrub')
    logger.info(f'Commencing scrub of VM #{vm_id}')

    # Read the VM
    # Don't use utils so we can check the response code
    child_span = opentracing.tracer.start_span('read_vm', child_of=span)
    response = IAAS.vm.read(
        token=Token.get_instance().token,
        pk=vm_id,
        span=child_span,
    )
    child_span.finish()

    if response.status_code == 404:
        logger.info(
            f'Received scrub task for VM #{vm_id} but it was already deleted from the API',
        )
        span.set_tag('return_reason', 'already_deleted')
        return
    elif response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch VM #{vm_id};\n'
            f'Response Text: {response.content.decode()}',
        )
        span.set_tag('return_reason', 'invalid_vm_id')
        return
    vm = response.json()['content']

    # Ensure that the state of the vm is still currently SCRUB_QUEUE
    if vm['state'] != state.SCRUB_QUEUE:
        logger.warning(
            f'Cancelling scrub of VM #{vm_id}. Expected state to be SCRUB_QUEUE, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for scrub tasks, just jump straight to doing the work
    vm['errors'] = []
    success: bool = False
    child_span = opentracing.tracer.start_span('scrub', child_of=span)
    server_type = vm['server_data']['type']['name']
    try:
        if server_type == 'HyperV':
            success = WindowsVmScrubber.scrub(vm, child_span)
            child_span.set_tag('server_type', 'windows')
        elif server_type == 'KVM':
            success = LinuxVmScrubber.scrub(vm, child_span)
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
        error = f'An unexpected error occurred when attempting to scrub VM #{vm_id}.'
        logger.error(error, exc_info=True)
        vm['errors'].append(f'{error} Error: {err}')
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully scrubbed VM #{vm_id} from hardware.')
        metrics.vm_scrub_success()
        # Do API deletions
        logger.debug(f'Deleting VM #{vm_id} from the IAAS')

        child_span = opentracing.tracer.start_span('delete_vm_from_api', child_of=span)
        response = IAAS.vm.delete(token=Token.get_instance().token, pk=vm_id, span=child_span)
        child_span.finish()

        if response.status_code != 200:
            logger.error(
                f'HTTP {response.status_code} error occurred when attempting to delete VM #{vm_id};\n'
                f'Response Text: {response.content.decode()}',
            )
            return
        logger.info(f'Successfully deleted VM #{vm_id} from the IAAS.')

    else:
        logger.error(f'Failed to scrub VM #{vm_id}')
        metrics.vm_scrub_failure()
        # Email the user
        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        try:
            EmailNotifier.vm_failure(vm, 'scrub')
        except Exception:
            logger.error(
                f'Failed to send failure email for VM #{vm_id}',
                exc_info=True,
            )
        child_span.finish()
        # There's no fail state here either
