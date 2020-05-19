"""
mixin class containing methods that are needed by both vm task classes
methods included;
    - a method to generate the drive information for an update
"""
# stdlib
import logging
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import utils

__all__ = [
    'VmUpdateMixin',
]


class VmUpdateMixin:
    logger: logging.Logger

    @classmethod
    def fetch_drive_updates(cls, vm_data: Dict[str, Any], span: Span) -> Tuple[str, str, Deque[Dict[str, int]]]:
        """
        Given a VM's data, generate the data for drives that need to be updated in this update request
        :param vm_data: The data of the VM being updated
        :param span: The tracing span in use for the current task
        :returns: A tuple of three values, the hdd, ssd, and other drives for the update request
        """
        vm_id = vm_data['idVM']
        hdd = ''
        ssd = ''
        drives: Deque[Dict[str, int]] = deque()

        # Check through the VM's latest batch of changes and determine if any drives have been changed
        if len(vm_data['changes_this_month']) == 0:
            # Unusual to be here, just return
            return hdd, ssd, drives

        # Check if the latest change had any drives changed
        if len(vm_data['changes_this_month'][0]['storage_histories']) == 0:
            return hdd, ssd, drives

        storages = vm_data['vm_storage']

        for history in vm_data['changes_this_month'][0]['storage_histories']:
            # List vm_histories by storage_id to calcualate the change
            storage_id = history['storage_id']
            params = {
                'order': '-created',
                'limit': 2,
                'storage_histories__storage_id': storage_id,
                'vm_id': vm_id,
            }
            storage_changes = utils.api_list(IAAS.vm_history, params, span=span)

            # Get storage details from vm_data
            storage = [i for i in storages if i['idStorage'] == storage_id]

            if len(storage) == 0:
                cls.logger.error(f'Error fetching Storage #{storage_id} for VM #{vm_id}')
                return hdd, ssd, drives

            new_value = storage_changes[0]['gb_quantity']
            old_value = 0
            if len(storage_changes) > 1:
                old_value = storage_changes[1]['gb_quantity']

            # Check if the storage is primary
            if storage[0]['primary']:
                # Determine which field (hdd or ssd) to populate with this storage information
                if storage[0]['storage_type'] == 'HDD':
                    hdd = f'{storage_id}:{new_value}:{old_value}'
                elif storage[0]['storage_type'] == 'SSD':
                    ssd = f'{storage_id}:{new_value}:{old_value}'
                else:
                    cls.logger.error(
                        f'Invalid primary drive storage type {storage[0]["storage_type"]} for VM #{vm_id}. '
                        'Expected either "HDD" or "SSD"',
                    )
                    return hdd, ssd, drives
            else:
                # Append the drive to the deque
                drives.append({
                    'id': storage_id,
                    'type': storage[0]['storage_type'],
                    'new_size': new_value,
                    'old_size': old_value,
                })

        # Finally, return the generated information
        return hdd, ssd, drives

    @classmethod
    def determine_should_restart(cls, vm_data: Dict[str, Any], span) -> Optional[bool]:
        """
        Check through the VM changes to see if the VM should be turned back on after the update is finished
        """
        # Determine whether or not we should restart the VM by retrieving the previous state of the VM
        if len(vm_data['changes_this_month']) == 0:
            # This is wrong, state update should always be there regardless
            return None
        params = {
            'order': '-created',
            'limit': 1,
            'state__in': (4, 6, 9),
            'vm_id': vm_data['idVM'],
        }
        # Get the last two histories where state was changed, the first item returned will be the current request for
        # change and the second item will be the current status of the VM
        state_changes = utils.api_list(IAAS.vm_history, params, span=span)

        # Update the vm_data to retain the state to go back to
        vm_data['return_state'] = state_changes[0]['state']

        # We restart the VM if the VM was in state 4 before this update
        cls.logger.debug(f'VM #{vm_data["idVM"]} will be returned to state {vm_data["return_state"]} after update')
        return vm_data['return_state'] == 4
