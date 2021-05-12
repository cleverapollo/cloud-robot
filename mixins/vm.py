"""
mixin class containing methods that are needed by both vm task classes
methods included;
    - a method to generate the drive information for an update
"""
# stdlib
import logging
import os
from collections import deque
from typing import Any, Deque, Dict, Optional
from urllib.error import HTTPError
from urllib.request import urlretrieve
# lib
from cloudcix.api.iaas import IAAS
from jaeger_client import Span
# local
import utils
from state import RUNNING, QUIESCED, SCRUB_QUEUE

__all__ = [
    'VmImageMixin',
    'VmUpdateMixin',
]


class VmImageMixin:
    logger: logging.Logger

    @classmethod
    def check_image(cls, filename: str, path: str) -> Optional[bool]:
        """
        Checks if file exists at path
        :param filename: name of the file to search
        :param path: file location
        :return: boolean True for file exists and False for not
        """
        file_found = False
        for file in os.listdir(path):
            if file == filename:
                cls.logger.debug(f'File {filename} is available.')
                file_found = True
        return file_found

    @classmethod
    def download_image(cls, filename: str, path: str) -> Optional[bool]:
        """
        This function downloads file_name form downloads.cloudcix.com/robot/ into concerned path at /mnt/images/
        :param filename: name of the file to be downloaded
        :param path: file destination location
        :return: boolean: True for Success and False for Failure
        """
        downloaded = False
        cls.logger.debug(f'File {filename} not available at {path} so downloading.')
        url = f'https://downloads.cloudcix.com/robot/{filename}'
        try:
            urlretrieve(url, f'{path}{filename}')
            downloaded = True
            cls.logger.debug(f'File {filename} downloaded successfully into {path}{filename}.')
        except HTTPError:
            cls.logger.error(f'File {filename} not found at {url}')
        return downloaded


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
    def determine_should_restart(cls, vm_data: Dict[str, Any], span: Span) -> Optional[bool]:
        """
        Check through the VM changes to see if the VM should be turned back on after the update is finished
        """
        vm_id = vm_data['id']
        params = {
            'order': '-created',
            'limit': 1,
            'state__in': (RUNNING, QUIESCED, SCRUB_QUEUE),
            'vm_id': vm_id,
        }
        # Get the last historiy where state was in a stable state of Running, Quiesced or Scrub Queue
        state_changes = utils.api_list(IAAS.vm_history, params, span=span)

        # Update the vm_data to retain the state to go back to
        vm_data['return_state'] = state_changes[0]['state']

        # We restart the VM if the VM was in state 4 before this update
        cls.logger.debug(f'VM #{vm_id} will be returned to state {vm_data["return_state"]} after update')
        return vm_data['return_state'] == RUNNING
