# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from celery_app import app, tracer
from cloudcix_token import Token
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
    span = tracer.start_span('scrub_vm')
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
    child_span = tracer.start_span('read_vm', child_of=span)
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

    # Ensure that the state of the vm is still currently DELETED
    if vm['state'] != state.DELETED:
        logger.warn(
            f'Cancelling scrub of VM #{vm_id}. Expected state to be DELETED, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for scrub tasks, just jump straight to doing the work
    success: bool = False

    # Read the VM image to get the hypervisor id
    child_span = tracer.start_span('read_vm_image', child_of=span)
    image = utils.api_read(IAAS.image, vm['idImage'], span=child_span)
    child_span.finish()

    if image is None:
        logger.error(
            f'Could not scrub VM #{vm_id} as its Image was not readable',
        )
        span.set_tag('return_reason', 'image_not_read')
        return

    hypervisor = image['idHypervisor']
    child_span = tracer.start_span('scrub', child_of=span)
    if hypervisor == 1:  # HyperV -> Windows
        success = WindowsVmScrubber.scrub(vm, child_span)
        child_span.set_tag('hypervisor', 'windows')
    elif hypervisor == 2:  # KVM -> Linux
        success = LinuxVmScrubber.scrub(vm, child_span)
        child_span.set_tag('hypervisor', 'linux')
    else:
        logger.error(
            f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
        )
        child_span.set_tag('hypervisor', 'linux')
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully scrubbed VM #{vm_id} from hardware.')
        metrics.vm_scrub_success()
        # Do API deletions
        logger.debug(f'Deleting VM #{vm_id} from the CMDB')

        child_span = tracer.start_span('delete_vm_from_api', child_of=span)
        response = IAAS.vm.delete(token=Token.get_instance().token, pk=vm_id, span=child_span)
        child_span.finish()

        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when attempting to delete VM #{vm_id};\n'
                f'Response Text: {response.content.decode()}',
            )
            return
        logger.info(f'Successfully deleted VM #{vm_id} from the CMDB.')

        child_span = tracer.start_span('delete_project_from_api', child_of=span)
        utils.project_delete(vm['idProject'], child_span)
        child_span.finish()
    else:
        logger.error(f'Failed to scrub VM #{vm_id}')
        metrics.vm_scrub_failure()
        # There's no fail state here either
