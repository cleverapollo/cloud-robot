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
    def fetch_drive_updates(cls, vm_data: Dict[str, Any], span: Span) -> Tuple[str, str, Deque[Dict[str, str]]]:
        """
        Given a VM's data, generate the data for drives that need to be updated in this update request
        :param vm_data: The data of the VM being updated
        :param span: The tracing span in use for the current task
        :returns: A tuple of three values, the hdd, ssd, and other drives for the update request
        """
        vm_id = vm_data['idVM']
        hdd = ''
        ssd = ''
        drives: Deque[Dict[str, str]] = deque()

        # Check through the VM's latest batch of changes and determine if any drives have been changed
        if len(vm_data['changes_this_month']) == 0:
            # Unusual to be here, just return
            return hdd, ssd, drives

        # If there has been a change, grab the storage changes and use them to update the values
        storage_changes = vm_data['changes_this_month'][0]['details'].get('storages', {})
        if len(storage_changes) == 0:
            # No storages were changed, return the defaults
            return hdd, ssd, drives

        # Read the updated storages to determine the changes that were made
        storage_ids = [storage_id for storage_id in storage_changes]
        storages = {
            storage['idStorage']: storage
            for storage in utils.api_list(IAAS.storage, {'idStorage__in': storage_ids}, vm_id=vm_id, span=span)
        }
        for storage_id, storage_changes in storage_changes.items():
            # Read the storage from the API
            storage = storages.get(storage_id, None)
            if storage is None:
                cls.logger.error(f'Error fetching Storage #{storage_id} for VM #{vm_id}')
                return hdd, ssd, drives
            # Check if the storage is primary
            if storage['primary']:
                # Determine which field (hdd or ssd) to populate with this storage information
                if storage['storage_type'] == 'HDD':
                    hdd = f'{storage["idStorage"]}:{storage_changes["new_value"]}:{storage_changes["old_value"]}'
                elif storage['storage_type'] == 'SSD':
                    ssd = f'{storage["idStorage"]}:{storage_changes["new_value"]}:{storage_changes["old_value"]}'
                else:
                    cls.logger.error(
                        f'Invalid primary drive storage type {storage["storage_type"]} for VM #{vm_id}. '
                        'Expected either "HDD" or "SSD"',
                    )
                    return hdd, ssd, drives
            else:
                # Append the drive to the deque
                drives.append({
                    'id': storage_id,
                    'type': storage['storage_type'],
                    'new_size': storage_changes['new_value'],
                    'old_size': storage_changes['old_value'],
                })

        # Finally, return the generated information
        return hdd, ssd, drives

    @classmethod
    def determine_should_restart(cls, vm_data: Dict[str, Any]) -> Optional[bool]:
        """
        Check through the VM changes to see if the VM should be turned back on after the update is finished
        """
        # Determine whether or not we should restart the VM by retrieving the previous state of the VM
        if len(vm_data['changes_this_month']) == 0:
            # This is wrong, state update should always be there regardless
            return None
        state_change = vm_data['changes_this_month'][0]['details'].get('state', {})
        if len(state_change) == 0:
            # This is also as bug
            return None
        # Update the vm_data to retain the state to go back to
        vm_data['return_state'] = state_change['old_value']
        # We restart the VM iff the VM was in state 4 before this update
        cls.logger.debug(f'VM #{vm_data["idVM"]} will be returned to state {state_change["old_value"]} after update')
        return state_change['old_value'] == 4
