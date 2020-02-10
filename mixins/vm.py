"""
mixin class containing methods that are needed by both vm task classes
methods included;
    - a method to generate the drive information for an update
"""
# stdlib
import logging
from collections import deque
from typing import Any, Deque, Dict, Optional
# local
from state import RUNNING

__all__ = [
    'VmUpdateMixin',
]


class VmUpdateMixin:
    logger: logging.Logger

    @classmethod
    def fetch_drive_updates(cls, vm_data: Dict[str, Any]) -> Deque[Dict[str, str]]:
        """
        Given a VM's data, generate the data for drives that need to be updated in this update request
        :param vm_data: The data of the VM being updated
        :returns: A Deque of drives for the update request
        """
        vm_id = vm_data['id']
        drives: Deque[Dict[str, str]] = deque()

        # If there has been a change, grab the storage changes and use them to update the values
        storage_changes = vm_data['changes_this_month'][0]['details'].get('storages', {})
        if len(storage_changes) == 0:
            # No storages were changed, return the defaults
            return drives

        # Read the updated storages to determine the changes that were made
        storages = {storage['id']: storage for storage in vm_data['storages']}
        for storage_id, storage_changes in storage_changes.items():
            storage = storages.get(storage_id, None)
            if storage is None:
                cls.logger.error(f'Error fetching Storage #{storage_id} for VM #{vm_id}')
                return drives

            # Append the drive to be updated to the deque
            drives.append({
                'id': storage_id,
                'new_size': storage_changes['new_value'],
                'old_size': storage_changes['old_value'],
            })

        # Finally, return the generated information
        return drives

    @classmethod
    def determine_should_restart(cls, vm_data: Dict[str, Any]) -> Optional[bool]:
        """
        Check through the VM changes to see if the VM should be turned back on after the update is finished
        """
        # Determine whether or not we should restart the VM by retrieving the previous state of the VM
        state_change = vm_data['changes_this_month'][0]['details'].get('state', {})
        if len(state_change) == 0:
            # This is also as bug
            return None
        # Update the vm_data to retain the state to go back to
        vm_data['return_state'] = state_change['old_value']
        # We restart the VM iff the VM was in state RUNNING before this update
        cls.logger.debug(f'VM #{vm_data["id"]} will be returned to state {state_change["old_value"]} after update')
        return state_change['old_value'] == RUNNING
