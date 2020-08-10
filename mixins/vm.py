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
        drives: Deque[Dict[str, Any]] = deque()

        # To be changed storages
        storage_updates = vm_data['history'][0]['storage_histories']
        # All storages of VM
        storages = vm_data['vm_storage']

        # compare storages and storage_updates
        for storage_update in storage_updates:
            # sort out the storage_update from all storages of VM
            # (contains changes such as add new or remove existing or increase existing)
            storage_id = storage_update['storage_id']
            storage = [i for i in storages if i['idStorage'] == storage_id]
            if len(storage) != 1:
                cls.logger.error(f'Error fetching Storage #{storage_id} for VM #{vm_id}')
                return hdd, ssd, drives
            # New and old values
            new_value = storage_update['gb_quantity']
            old_value: Optional[int] = 0

            # Find the storage's very previous change
            for i in range(len(vm_data['history'])):
                # Old value
                old_value = None
                # i=0 is already taken for new value
                for storage_history in vm_data['history'][i + 1]['storage_histories']:
                    if storage_history['storage_id'] == storage_id:
                        old_value = int(storage_history['gb_quantity'])
                        break
                if old_value is not None:
                    break

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
