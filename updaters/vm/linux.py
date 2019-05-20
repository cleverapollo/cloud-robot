"""
updater class for linux vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
from collections import deque
from typing import Any, Deque, Dict, Optional
# lib
import opentracing
from cloudcix.api import IAAS
from jaeger_client import Span
from paramiko import AutoAddPolicy, SSHClient, SSHException
# local
import settings
import utils
from mixins import LinuxMixin


__all__ = [
    'Linux',
]


class Linux(LinuxMixin):
    """
    Class that handles the updating of the specified VM
    When we get to this point, we can be sure that the VM is a linux VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.updaters.vm.linux')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before updating
    template_keys = {
        # the number of cpus in the vm
        'cpu',
        # the drives in the vm
        'drives',
        # the hdd primary drive of the VM 'id:size'
        'hdd',
        # the ip address of the host that the VM is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # the amount of RAM in the VM
        'ram',
        # the ssd primary drive of the VM 'id:size'
        'ssd',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def update(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the update of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param image_data: The data of the image for the VM
        :param span: The tracing span in use for this update task
        :return: A flag stating whether or not the update was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Linux._get_template_data(vm_data, child_span)
        child_span.finish()

        # Check that the data was successfully generated
        if template_data is None:
            Linux.logger.error(
                f'Failed to retrieve template data for VM #{vm_id}.',
            )
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Linux.template_keys):
            missing_keys = [
                f'"{key}"' for key in Linux.template_keys if template_data[key] is None
            ]
            Linux.logger.error(
                f'Template Data Error, the following keys were missing from the VM update data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence updating the VM
        host_ip = template_data.pop('host_ip')

        # Generate the update command using the template data
        child_span = opentracing.tracer.start_span('generate_command', child_of=span)
        cmd = utils.JINJA_ENV.get_template('vm/linux/update_cmd.j2').render(**template_data)
        child_span.finish()

        Linux.logger.debug(f'Generated VM update command for VM #{vm_data["idVM"]}\n{cmd}')

        # Open a client and run the two necessary commands on the host
        updated = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            # Try connecting to the host and running the necessary commands
            client.connect(hostname=host_ip, username='administrator')  # No need for password as it should have keys
            span.set_tag('host', host_ip)

            # Attempt to execute the update command
            Linux.logger.debug(f'Executing update command for VM #{vm_id}')

            child_span = opentracing.tracer.start_span('update_vm', child_of=span)
            stdout, stderr = Linux.deploy(cmd, client, child_span)
            child_span.finish()

            if stdout:
                Linux.logger.debug(f'VM update command for VM #{vm_id} generated stdout.\n{stdout}')
                updated = True
            if stderr:
                Linux.logger.warning(f'VM update command for VM #{vm_id} generated stderr.\n{stderr}')
        except SSHException:
            Linux.logger.error(
                f'Exception occurred while updating VM #{vm_id} in {host_ip}',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()
        return updated

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the update method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :param span: The tracing span in use for this task. In this method, just pass it to API calls.
        :returns: The data needed for the templates to update a Linux VM
        """
        vm_id = vm_data['idVM']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        # RAM is needed in MB for the updater but we take it in in GB (1024, not 1000)
        data['ram'] = vm_data['ram'] * 1024
        data['cpu'] = vm_data['cpu']

        # Fetch the drives for the VM and add them to the data
        # Update needs to use changes, not the drives that are attached to the VM by default
        Linux.logger.debug(f'Fetching drives for VM #{vm_id}')
        drives: Deque[Dict[str, str]] = deque()
        # List all the storages that are in use for the VM
        storage_ids = [storage_id for storage_id in vm_data['changes_this_month'][0]['details']['storages']]
        storages = {
            storage['idStorage']: storage
            for storage in utils.api_list(IAAS.storage, {'idStorage__in': storage_ids})
        }
        for storage_id, storage_changes in vm_data['changes_this_month'][0]['details']['storages'].items():
            # Read the storage from the API
            storage = storages.get(storage_id, None)
            if storage is None:
                Linux.logger.error(f'Error fetching Storage #{storage_id} for VM #{vm_id}')
                return None
            # Check if the storage is primary
            if storage['primary']:
                # Determine which field (hdd or ssd) to populate with this storage information
                if storage['storage_type'] == 'HDD':
                    data['hdd'] = (
                        f'{storage["idStorage"]}:{storage_changes["new_value"]}:{storage_changes["old_value"]}'
                    )
                    data['ssd'] = 0
                elif storage['storage_type'] == 'SSD':
                    data['hdd'] = 0
                    data['ssd'] = (
                        f'{storage["idStorage"]}:{storage_changes["new_value"]}:{storage_changes["old_value"]}'
                    )
                else:
                    Linux.logger.error(
                        f'Invalid primary drive storage type {storage["storage_type"]}. Expected either "HDD" or "SSD"',
                    )
                    return None
            else:
                # Append the drive to the deque
                drives.append({
                    'id': storage_id,
                    'type': storage['storage_type'],
                    'new_size': storage_changes['new_value'],
                    'old_size': storage_changes['old_value'],
                })
        data['drives'] = drives

        # Get the ip address of the host
        Linux.logger.debug(f'Fetching host address for VM #{vm_id}')
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer'], span=span):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_ip'] = mac['ip']
                break

        # Add the host information to the data
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD
        return data
