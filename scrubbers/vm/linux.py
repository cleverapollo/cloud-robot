"""
scrubber class for linux vms

- gathers template data
- connects to the vm's host and runs commands to delete the VM on it
"""
# stdlib
import logging
import os
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
from netaddr import IPAddress
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
    Class that handles the scrubbing of the specified VM
    When we get to this point, we can be sure that the VM is a linux VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.scrubbers.vm.linux')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before scrubbing
    template_keys = {
        # a flag stating whether or not we need to delete the bridge as well (only if there are no more VMs)
        'delete_bridge',
        # the drives in the vm
        'drives',
        # the hdd primary drive of the VM 'id:size'
        'hdd',
        # the ip address of the host that the VM to scrub is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # the ssd primary drive of the VM 'id:size'
        'ssd',
        # the vlan that the vm is a part of
        'vlan',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def scrub(vm_data: Dict[str, Any]) -> bool:
        """
        Commence the scrub of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :return: A flag stating whether or not the scrub was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        template_data = Linux._get_template_data(vm_data)

        # Check that the data was successfully generated
        if template_data is None:
            Linux.logger.error(
                f'Failed to retrieve template data for VM #{vm_id}.',
            )
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Linux.template_keys):
            missing_keys = [
                f'"{key}"' for key in Linux.template_keys if template_data[key] is None
            ]
            Linux.logger.error(
                f'Template Data Error, the following keys were missing from the VM scrub data: '
                f'{", ".join(missing_keys)}',
            )
            return False

        # If everything is okay, commence scrubbing the VM
        host_ip = template_data.pop('host_ip')
        delete_bridge = template_data.pop('delete_bridge')

        # Generate the two commands that will be run on the host machine directly
        bridge_scrub_cmd, vm_scrub_cmd = Linux._generate_host_commands(vm_id, template_data)

        # Open a client and run the two necessary commands on the host
        scrubbed = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            # Try connecting to the host and running the necessary commands
            client.connect(hostname=host_ip, username='administrator')  # No need for password as it should have keys

            # Now attempt to execute the vm scrub command
            Linux.logger.debug(f'Executing vm scrub command for VM #{vm_id}')
            stdout, stderr = Linux.deploy(vm_scrub_cmd, client)
            if stdout:
                Linux.logger.debug(f'VM scrub command for VM #{vm_id} generated stdout.\n{stdout}')
                scrubbed = True
                # Attempt to delete the config file from the network drive
                Linux._delete_network_file(vm_id, f'kickstarts/{template_data["vm_identifier"]}.cfg')
            if stderr:
                Linux.logger.warning(f'VM scrub command for VM #{vm_id} generated stderr.\n{stderr}')

            # Check if we also need to run the command to delete the bridge
            if delete_bridge:
                Linux.logger.debug(f'Deleting bridge for VM #{vm_id}')
                stdout, stderr = Linux.deploy(bridge_scrub_cmd, client)
                if stdout:
                    Linux.logger.debug(f'Bridge scrub command for VM #{vm_id} generated stdout\n{stdout}')
                if stderr:
                    Linux.logger.warning(f'Bridge scrub command for VM #{vm_id} generated stderr\n{stderr}')
                # Attempt to delete the bridge definition file from the network drive
                Linux._delete_network_file(vm_id, f'bridge_xmls/br{template_data["vlan"]}.xml')
        except SSHException:
            Linux.logger.error(
                f'Exception occurred while scrubbing VM #{vm_id} in {host_ip}',
                exc_info=True,
            )
        finally:
            client.close()
        return scrubbed

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :returns: The data needed for the templates to build a Linux VM
        """
        vm_id = vm_data['idVM']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD

        # Fetch the drives for the VM and add them to the data
        drives: Deque[Dict[str, str]] = deque()
        for storage in utils.api_list(IAAS.storage, {}, vm_id=vm_id):
            # Check if the storage is primary
            if storage['primary']:
                # Determine which field (hdd or ssd) to populate with this storage information
                if storage['storage_type'] == 'HDD':
                    data['hdd'] = f'{storage["idStorage"]}:{storage["gb"]}'
                    data['ssd'] = 0
                elif storage['storage_type'] == 'SSD':
                    data['hdd'] = 0
                    data['ssd'] = f'{storage["idStorage"]}:{storage["gb"]}'
                else:
                    Linux.logger.error(
                        f'Invalid primary drive storage type {storage["storage_type"]}. Expected either "HDD" or "SSD"',
                    )
                    return None
            else:
                # Just append to the drives deque
                drives.append({
                    'id': storage['idStorage'],
                    'type': storage['storage_type'],
                    'size': storage['gb'],
                })
        data['drives'] = drives

        # Get the Networking details
        for ip_address in utils.api_list(IAAS.ipaddress, {'vm': vm_id}):
            # The private IP for the VM will be the one we need to pass to the template
            if not IPAddress(ip_address['address']).is_private():
                continue
            data['ip_address'] = ip_address['address']
            # Read the subnet for the IPAddress to fetch information like the gateway and subnet mask
            subnet = utils.api_read(IAAS.subnet, ip_address['idSubnet'])
            if subnet is None:
                return None
            data['vlan'] = subnet['vLAN']

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_ip'] = mac['ip']
                break

        data['delete_bridge'] = Linux._determine_bridge_deletion(vm_data)
        return data

    @staticmethod
    def _generate_host_commands(vm_id: int, template_data: Dict[str, Any]) -> Tuple[str, str]:
        """
        Generate the commands that need to be run on the host machine to scrub the infrastructure
        Generates the following commands;
            - command to scrub the bridge interface
            - command to scrub the VM itself
        :param vm_id: The id of the VM being built. Used for log messages
        :param template_data: The retrieved template data for the vm
        :returns: (bridge_scrub_command, vm_scrub_command)
        """
        # Render the bridge scrub command
        bridge_cmd = utils.JINJA_ENV.get_template('kvm/bridge_scrub_cmd.j2').render(**template_data)
        Linux.logger.debug(f'Generated bridge scrub command for VM #{vm_id}\n{bridge_cmd}')

        # Render the VM scrub command
        vm_cmd = utils.JINJA_ENV.get_template('vm/linux/scrub_cmd.j2').render(**template_data)
        Linux.logger.debug(f'Generated vm scrub command for VM #{vm_id}\n{vm_cmd}')

        return bridge_cmd, vm_cmd

    @staticmethod
    def _delete_network_file(vm_id: int, path: str):
        """
        Given a path to a file, attempt to delete it from the network drive
        """
        abspath = os.path.join(settings.KVM_ROBOT_NETWORK_DRIVE_PATH, path)
        if not os.path.exists(abspath):
            return
        try:
            os.remove(abspath)
            Linux.logger.debug(f'Deleted {path} from the network drive')
        except IOError:
            Linux.logger.error(
                f'Exception occurred while attempting to delete {path} from the network drive for VM #{vm_id}',
                exc_info=True,
            )

    @staticmethod
    def _determine_bridge_deletion(vm_data: Dict[str, Any]) -> bool:
        """
        Given a VM, determine if we need to delete it's bridge.
        We need to delete the bridge if the VM is the last Linux VM left in the Subnet

        Steps:
            - Get the private IP Address of the VM being deleted
            - Read the other private IP Addresses (fip_id__isnull=False) in the same Subnet (excluding this VM's id)
            - List all the VMs pointed to by the idVM fields of the returned (if any)
            - For each VM, check if it is Windows or Linux
            - If we find a Linux one, return False
            - If we make it through the entire loop, return True
        """
        vm_id = vm_data['idVM']
        # Get the id of the VM's private IP Address
        priv_ip = utils.api_list(IAAS.ipaddress, {'vm': vm_id, 'fip_id__isnull': False})[0]

        # Find the other private ip addresses in the subnet
        params = {
            'fip_id__isnull': False,
            'exclude__idIPAddress': priv_ip['idIPAddress'],
            'subnet__idSubnet': priv_ip['idSubnet'],
        }
        subnet_ips = utils.api_list(IAAS.ipaddress, params)

        # List the other VMs in the subnet
        subnet_vm_ids = list(map(lambda ip: ip['idVM'], subnet_ips))
        subnet_vms = utils.api_list(IAAS.vm, {'idVM__in': subnet_vm_ids})

        # Get the images from the VMs and check for linux hypervisors
        image_ids = list(set(map(lambda vm: vm['idImage'], subnet_vms)))
        images = utils.api_list(IAAS.image, {'idImage__in': image_ids})

        # Check the list of images for any linux hypervisor
        # any returns True if any item in the iterable is True
        # make an iterable that checks if the image's idHypervisor is 2
        return any(image['idHypervisor'] == 2 for image in images)
