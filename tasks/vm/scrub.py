# stdlib
import logging
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from celery_app import app
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
    Task to scrub the specified vm
    """
    logger = logging.getLogger('robot.tasks.vm.scrub')
    logger.info(f'Commencing scrub of VM #{vm_id}')

    # Read the VM
    # Don't use utils so we can check the response code
    response = IAAS.vrf.read(
        token=Token.get_instance().token,
        pk=vm_id,
    )

    if response.status_code == 404:
        logger.info(
            f'Received scrub task for VM #{vm_id} but it was already deleted from the API',
        )
        return
    elif response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch VM #{vm_id};\n'
            f'Response Text: {response.content.decode()}',
        )
        return
    vm = response.json()['content']

    # Ensure that the state of the vm is still currently DELETED
    if vm['state'] != state.DELETED:
        logger.warn(
            f'Cancelling scrub of VM #{vm_id}. Expected state to be DELETED, found {vm["state"]}.',
        )
        # Return out of this function without doing anything
        return

    # There's no in-between state for scrub tasks, just jump straight to doing the work
    success: bool = False

    # Read the VM image to get the hypervisor id
    image = utils.api_read(IAAS.image, vm['idImage'])
    if image is None:
        logger.error(
            f'Could not scrub VM #{vm_id} as its Image was not readable',
        )
        return

    hypervisor = image['idHypervisor']
    if hypervisor == 1:  # HyperV -> Windows
        success = WindowsVmScrubber.scrub(vm)
    elif hypervisor == 2:  # KVM -> Linux
        success = LinuxVmScrubber.scrub(vm)
    else:
        logger.error(
            f'Unsupported Hypervisor ID #{hypervisor} for VM #{vm_id}',
        )

    if success:
        logger.info(f'Successfully scrubbed VM #{vm_id} from hardware.')
        metrics.vm_scrub_success()
        # Do API deletions
        logger.debug(f'Deleting VM #{vm_id} from the CMDB')

        response = IAAS.vm.delete(token=Token.get_instance().token, pk=vm_id)
        if response.status_code != 204:
            logger.error(
                f'HTTP {response.status_code} error occurred when attempting to delete VM #{vm_id};\n'
                f'Response Text: {response.content.decode()}',
            )
            return
        logger.info(f'Successfully deleted VM #{vm_id} from the CMDB.')
        utils.project_delete(vm['idProject'])
    else:
        logger.error(f'Failed to scrub VM #{vm_id}')
        metrics.vm_scrub_failure()
        # There's no fail state here either

    # Flush the logs
    utils.flush_logstash()
