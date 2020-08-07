"""
builder class for windows vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
import os
import random
import shutil
import string
from collections import deque
from typing import Any, Deque, Dict, Optional
# lib
import opentracing
from cloudcix.api import IAAS
from jaeger_client import Span
from netaddr import IPAddress
from winrm.exceptions import WinRMError
# local
import settings
import utils
from mixins import WindowsMixin


__all__ = [
    'Windows',
]


class Windows(WindowsMixin):
    """
    Class that handles the building of the specified VM
    When we get to this point, we can be sure that the VM is a windows VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.vm.windows')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before building
    template_keys = {
        # the admin password for the vm, unencrypted
        'admin_password',
        # the number of cpus in the vm
        'cpu',
        # the default subnet gateway
        'default_gateway',
        # default ip address of the VM
        'default_ip',
        # the default subnet mask in integer form (/24)
        'default_netmask_int',
        # the default vlan that the vm is a part of
        'default_vlan',
        # the dns servers for the vm (in list form, not string form)
        'dns',
        # the drives in the vm
        'drives',
        # the freenas url for the region
        'freenas_url',
        # the hdd primary drive of the VM 'id:size'
        'hdd',
        # the DNS hostname for the host machine, as WinRM cannot use IPv6
        'host_name',
        # the name of the image used to build the vm
        'image_name',
        # the id of the image used to build the VM
        'image_id',
        # the non default ip addresses of the vm
        'ip_addresses',
        # the language of the vm
        'language',
        # the amount of RAM in the VM
        'ram',
        # the ssd primary drive of the VM 'id:size'
        'ssd',
        # the timezone of the vm
        'timezone',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def build(vm_data: Dict[str, Any], image_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the build of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param image_data: The data of the image for the VM
        :param span: The tracing span in use for this build task
        :return: A flag stating whether or not the build was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Windows._get_template_data(vm_data, image_data, child_span)
        child_span.finish()

        # Check that the data was successfully generated
        if template_data is None:
            Windows.logger.error(
                f'Failed to retrieve template data for VM #{vm_id}.',
            )
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Windows.template_keys):
            missing_keys = [
                f'"{key}"' for key in Windows.template_keys if template_data[key] is None
            ]
            Windows.logger.error(
                f'Template Data Error, the following keys were missing from the VM build data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence building the VM
        host_name = template_data.pop('host_name')

        # Write necessary files into the network drive
        network_drive_path = settings.HYPERV_ROBOT_NETWORK_DRIVE_PATH
        path = f'{network_drive_path}/VMs/{vm_data["idProject"]}_{vm_data["idVM"]}'
        child_span = opentracing.tracer.start_span('write_files_to_network_drive', child_of=span)
        file_write_success = Windows._generate_network_drive_files(vm_id, path, template_data)
        child_span.finish()

        if not file_write_success:
            # The method will log which part failed, so we can just exit
            span.set_tag('failed_reason', 'network_drive_files_failed_to_write')
            return False

        # Render the build command
        child_span = opentracing.tracer.start_span('generate_command', child_of=span)
        cmd = utils.JINJA_ENV.get_template('vm/windows/build_cmd.j2').render(**template_data)
        child_span.finish()

        # Open a client and run the two necessary commands on the host
        built = False
        try:
            child_span = opentracing.tracer.start_span('build_vm', child_of=span)
            response = Windows.deploy(cmd, host_name, child_span)
            child_span.finish()
            span.set_tag('host', host_name)
        except WinRMError:
            Windows.logger.error(
                f'Exception occurred while attempting to build VM #{vm_id} on {host_name}',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'winrm_error')
        else:
            # Check the stdout and stderr for messages
            if response.std_out:
                msg = response.std_out.strip()
                Windows.logger.debug(f'VM build command for VM #{vm_id} generated stdout\n{msg}')
                built = 'VM Successfully Created' in msg
            # Check if the error was parsed to ensure we're not logging invalid std_err output
            if response.std_err and '#< CLIXML\r\n' not in response.std_err:
                msg = response.std_err.strip()
                Windows.logger.warning(f'VM build command for VM #{vm_id} generated stderr\n{msg}')

        # remove all the files created in network drive
        try:
            shutil.rmtree(path)
        except OSError:
            Windows.logger.warning(f'Failed to remove network drive files for VM #{vm_id}')

        return built

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], image_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :param image_data: The data of the Image for the VM
        :param span: The tracing span in use for this task. In this method, just pass it to API calls.
        :returns: The data needed for the templates to build a Windows VM
        """
        vm_id = vm_data['idVM']
        Windows.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Windows.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        data['image_name'] = image_data['name']
        # RAM is needed in MB for the builder but we take it in in GB (1024, not 1000)
        data['ram'] = vm_data['ram'] * 1024
        data['cpu'] = vm_data['cpu']
        data['dns'] = vm_data['dns']

        # Generate encrypted passwords
        data['admin_password'] = Windows._password_generator(size=8)
        # Also save the password back to the VM data dict
        vm_data['admin_password'] = data['admin_password']

        # Fetch the drives for the VM and add them to the data
        drives: Deque[Dict[str, Any]] = deque()
        for storage in utils.api_list(IAAS.storage, {}, vm_id=vm_id, span=span):
            # Check if the storage is primary
            if storage['primary']:
                data['drive_id'] = storage['idStorage']
                # Determine which field (hdd or ssd) to populate with this storage information
                if storage['storage_type'] == 'HDD':
                    data['drive_format'] = 'HDD'
                    data['hdd'] = storage['gb']
                    data['ssd'] = 0
                elif storage['storage_type'] == 'SSD':
                    data['drive_format'] = 'SSD'
                    data['hdd'] = 0
                    data['ssd'] = storage['gb']
                else:
                    Windows.logger.error(
                        f'Invalid primary drive storage type {storage["storage_type"]}. Expected either "HDD" or "SSD"',
                    )
                    return None
            else:
                # Just append to the drives deque
                drives.append(
                    {
                        'drive_id': storage['idStorage'],
                        'drive_size': storage['gb'],
                    },
                )
        if len(drives) > 0:
            data['drives'] = drives
        else:
            data['drives'] = 0

        # Get the Networking details
        data['vlans'] = []
        data['ip_addresses'] = []
        for ip_address in vm_data['ip_addresses']:
            # The private IPs for the VM will be the one we need to pass to the template
            if not IPAddress(ip_address['address']).is_private():
                continue
            ip = ip_address['address']

            # Read the subnet for the IPAddress to fetch information like the gateway and subnet mask
            subnet = utils.api_read(IAAS.subnet, ip_address['idSubnet'], span=span)
            if subnet is None:
                return None
            gateway, netmask_int = subnet['addressRange'].split('/')
            vlan = str(subnet['vLAN'])

            # Pick the default ip
            if ip_address['idSubnet'] == vm_data['gateway_subnet']['idSubnet']:
                data['default_ip'] = ip
                data['default_gateway'] = gateway
                data['default_netmask_int'] = netmask_int
                data['default_vlan'] = vlan
                continue
            data['ip_addresses'].append(
                {
                    'ip': ip,
                    'gateway': gateway,
                    'netmask_int': netmask_int,
                    'vlan': vlan,
                },
            )

        # Add locale data to the VM
        data['language'] = 'en_IE'
        data['timezone'] = 'GMT Standard Time'

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer'], span=span):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_name'] = mac['dnsName']
                break

        # Add the host information to the data
        data['freenas_url'] = settings.FREENAS_URL
        return data

    @staticmethod
    def _generate_network_drive_files(vm_id: int, path: str, template_data: Dict[str, Any]) -> bool:
        """
        Generate and write files into the network drive so they are on the host for the build scripts to utilise.
        Writes the following files to the drive;
            - unattend.xml
            - network.xml
            - build.psm1
        :param vm_id: The id of the VM being built. Used for log messages
        :param path: Network drive location to create above files for VM build
        :param template_data: The retrieved template data for the vm
        :returns: A flag stating whether or not the job was successful
        """
        # Create a folder by vm_identifier name at network_drive_path/VMs/
        try:
            os.mkdir(path)
        except OSError:
            Windows.logger.error(
                f'Failed to create directory for VM #{vm_id} at {path}',
                exc_info=True,
            )
            return False
        # Render and attempt to write the unattend file
        template_name = f'vm/windows/unattend.j2'
        unattend = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Windows.logger.debug(f'Generated unattend file for VM #{vm_id}\n{unattend}')
        try:
            # Attempt to write
            unattend_file = f'{path}/unattend.xml'
            with open(unattend_file, 'w') as f:
                f.write(unattend)
            Windows.logger.debug(f'Successfully wrote unattend file for VM #{vm_id} to {unattend_file}')
        except IOError:
            Windows.logger.error(
                f'Failed to write unattend file for VM #{vm_id} to {unattend_file}',
                exc_info=True,
            )
            return False

        # Render and attempt to write the network file
        template_name = f'vm/windows/network.j2'
        network = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Windows.logger.debug(f'Generated network file for VM #{vm_id}\n{network}')
        try:
            # Attempt to write
            network_file = f'{path}/network.xml'
            with open(network_file, 'w') as f:
                f.write(network)
            Windows.logger.debug(f'Successfully wrote network file for VM #{vm_id} to {network_file}')
        except IOError:
            Windows.logger.error(
                f'Failed to write network file for VM #{vm_id} to {network_file}',
                exc_info=True,
            )
            return False

        # Render and attempt to write the build script file
        template_name = f'vm/windows/build_script.j2'
        builder = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Windows.logger.debug(f'Generated build script file for VM #{vm_id}\n{builder}')
        try:
            # Attempt to write
            script_file = f'{path}/builder.psm1'
            with open(script_file, 'w') as f:
                f.write(builder)
            Windows.logger.debug(f'Successfully wrote build script file for VM #{vm_id} to {script_file}')
        except IOError:
            Windows.logger.error(
                f'Failed to write build script file for VM #{vm_id} to {script_file}',
                exc_info=True,
            )
            return False

        # Return True as all was successful
        return True

    @staticmethod
    def _password_generator(size: int = 8, chars: Optional[str] = None) -> str:
        """
        Returns a string of random characters, useful in generating temporary
        passwords for automated password resets.

        :param size: default=8; override to provide smaller/larger passwords
        :param chars: default=A-Za-z0-9; override to provide more/less diversity
        :return: A password of length 'size' generated randomly from 'chars'
        """
        if chars is None:
            chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(size))
