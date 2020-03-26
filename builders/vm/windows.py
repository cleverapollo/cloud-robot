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
import string
from typing import Any, Dict, Optional
# lib
import opentracing
from jaeger_client import Span
from netaddr import IPAddress, IPNetwork
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
        # the dns servers for the vm (in list form, not string form)
        'dns',
        # the subnet gateway
        'gateway',
        # the DNS hostname for the host machine, as WinRM cannot use IPv6
        'host_name',
        # the answer_files file of the image used to build the VM
        'image_answer_file_name',
        # the name of the image used to build the vm
        'image_name',
        # the ip address of the vm in its subnet
        'ip_address',
        # the language of the vm
        'language',
        # the subnet mask in integer form (/24)
        'netmask_int',
        # the nas drive url for the region
        'network_drive_url',
        # the amount of RAM in the VM
        'ram',
        # storage type (HDD/SSD)
        'storage_type',
        # storages of the vm
        'storages',
        # the timezone of the vm
        'timezone',
        # the vlan that the vm is a part of
        'vlan',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
        # path for vm's folders files located in host
        'vms_path',
    }

    @staticmethod
    def build(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the build of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param span: The tracing span in use for this build task
        :return: A flag stating whether or not the build was successful
        """
        vm_id = vm_data['id']

        # Generate the necessary template data
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Windows._get_template_data(vm_data)
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
        child_span = opentracing.tracer.start_span('write_files_to_network_drive', child_of=span)
        file_write_success = Windows._generate_network_drive_files(vm_id, template_data)
        child_span.finish()

        if not file_write_success:
            # The method will log which part failed, so we can just exit
            span.set_tag('failed_reason', 'network_drive_files_failed_to_write')
            return False

        # Render the build command
        child_span = opentracing.tracer.start_span('generate_command', child_of=span)
        cmd = utils.JINJA_ENV.get_template('vm/hyperv/commands/build.j2').render(**template_data)
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
        # Remove the answer file from network drive
        child_span = opentracing.tracer.start_span('delete_files_from_network_drive', child_of=span)
        Windows._remove_network_drive_files(vm_id, template_data)
        child_span.finish()

        return built

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :returns: The data needed for the templates to build a Windows VM
        """
        vm_id = vm_data['id']
        Windows.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Windows.template_keys}

        data['vm_identifier'] = f'{vm_data["project"]["id"]}_{vm_id}'
        data['image_answer_file_name'] = vm_data['image']['answer_file_name']
        data['image_name'] = vm_data['image']['display_name']
        # RAM is needed in MB for the builder but we take it in in GB (1024, not 1000)
        data['ram'] = vm_data['ram'] * 1024
        data['cpu'] = vm_data['cpu']
        data['dns'] = [server.strip() for server in vm_data['dns'].split(',')]

        # Generate encrypted passwords
        data['admin_password'] = Windows._password_generator(size=12)
        # Also save the password back to the VM data dict
        vm_data['admin_password'] = data['admin_password']

        # Check for the primary storage
        primary: bool = False
        for storage in vm_data['storages']:
            if storage['primary']:
                primary = True
        if not primary:
            Windows.logger.error(
                f'No primary storage drive found. Expected one primary storage drive',
            )
            return None

        data['storages'] = vm_data['storages']
        data['storage_type'] = vm_data['storage_type']

        # Get the Networking details
        data['ip_address'] = vm_data['ip_address']['address']
        net = IPNetwork(vm_data['ip_address']['subnet']['address_range'])
        data['gateway'], data['netmask_int'] = str(net.ip), str(net.prefixlen)
        data['vlan'] = vm_data['ip_address']['subnet']['vlan']

        # Add locale data to the VM
        data['language'] = 'en_IE'
        data['timezone'] = 'GMT Standard Time'

        # Get the host name of the server
        host_name = None
        for interface in vm_data['server_data']['interfaces']:
            if interface['enabled'] is True and interface['ip_address'] is not None:
                if IPAddress(str(interface['ip_address'])).version == 6:
                    host_name = interface['hostname']
                    break
        if host_name is None:
            Windows.logger.error(
                f'Host name is not found for the server # {vm_data["server_id"]}',
            )
            return None

        # Add the host information to the data
        data['host_name'] = host_name
        data['network_drive_url'] = settings.NETWORK_DRIVE_URL
        data['vms_path'] = settings.HYPERV_VMS_PATH
        return data

    @staticmethod
    def _generate_network_drive_files(vm_id: int, template_data: Dict[str, Any]) -> bool:
        """
        Generate and write files into the network drive so they are on the host for the build scripts to utilise.
        Writes the following files to the drive;
            - unattend file
        :param vm_id: The id of the VM being built. Used for log messages
        :param template_data: The retrieved template data for the vm
        :returns: A flag stating whether or not the job was successful
        """
        network_drive_path = settings.HYPERV_ROBOT_NETWORK_DRIVE_PATH

        # Render and attempt to write the answer file
        template_name = f'vm/hyperv/answer_files/windows.j2'
        answer_file_data = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Windows.logger.debug(f'Generated answer file for VM #{vm_id}\n{answer_file_data}')
        try:
            # Attempt to write
            answer_file_path = f'{network_drive_path}/answer_files/{template_data["vm_identifier"]}.xml'
            with open(answer_file_path, 'w') as f:
                f.write(answer_file_data)
            Windows.logger.debug(f'Successfully wrote answer file for VM #{vm_id} to {answer_file_data}')
        except IOError:
            Windows.logger.error(
                f'Failed to write answer file for VM #{vm_id} to {answer_file_path}',
                exc_info=True,
            )
            return False

        # Return True as all was successful
        return True

    @staticmethod
    def _remove_network_drive_files(vm_id: int, template_data: Dict[str, Any]):
        """
        Removes files from the network drive as they are not necessary after build and are not supposed to be left.
        Remove the following files from the drive;
            - answer file
        :param vm_id: The id of the VM being built. Used for log messages
        :param template_data: The retrieved template data for the vm
        """
        network_drive_path = settings.HYPERV_ROBOT_NETWORK_DRIVE_PATH

        # Remove answer file
        file_path = f'answer_files/{template_data["vm_identifier"]}.cfg'
        answer_file_path = os.path.join(network_drive_path, file_path)
        if os.path.exists(answer_file_path):
            try:
                os.remove(answer_file_path)
                Windows.logger.debug(f'Successfully removed answer file {answer_file_path} of VM #{vm_id}')
            except IOError:
                Windows.logger.error(
                    f'Exception occurred while attempting to delete {file_path} from the network drive for VM #{vm_id}',
                    exc_info=True,
                )

    @staticmethod
    def _password_generator(size: int = 12, chars: Optional[str] = None) -> str:
        """
        Returns a string of random characters, useful in generating temporary
        passwords for automated password resets.

        :param size: default=12; override to provide smaller/larger passwords
        :param chars: default=A-Za-z0-9; override to provide more/less diversity
        :return: A password of length 'size' generated randomly from 'chars'
        """
        if chars is None:
            chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(size))
