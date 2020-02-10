"""
builder class for vm vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
import os
import random
import string
from crypt import crypt, mksalt, METHOD_SHA512
from typing import Any, Dict, Optional, Tuple
# lib
import opentracing
from jaeger_client import Span
from netaddr import IPAddress, IPNetwork
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
    Class that handles the building of the specified VM
    When we get to this point, we can be sure that the VM is a linux VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.vm.linux')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before building
    template_keys = {
        # the admin password for the vm, unencrypted
        'admin_password',
        # the number of cpus in the vm
        'cpu',
        # the admin password for the vm, pre-crpyted
        'crypted_admin_password',
        # root password encrypted, needed for centos kickstart
        'crypted_root_password',
        # the dns servers for the vm
        'dns',
        # the subnet gateway
        'gateway',
        # the ip address of the host that the VM will be built on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # the answer_files file of the image used to build the VM
        'image_answer_file_name',
        # the filename of the image used to build the vm
        'image_filename',
        # the os variant of the image used to build the VM
        'image_os_variant',
        # the ip address of the vm in its subnet
        'ip_address',
        # the keyboard layout to use for the vm
        'keyboard',
        # the language of the vm
        'language',
        # the subnet mask in ip address form (255.255.255.0)
        'netmask',
        # the path on the host where the network drive is found
        'network_drive_path',
        # the amount of RAM in the VM
        'ram',
        # storage type (HDD/SSD)
        'storage_type'
        # storages of the vm
        'storages',
        # the timezone of the vm
        'timezone',
        # the vlan that the vm is a part of
        'vlan',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
        # path for vm's .img files located in host
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
        template_data = Linux._get_template_data(vm_data)
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
                f'Template Data Error, the following keys were missing from the VM build data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence building the VM
        host_ip = template_data.pop('host_ip')
        answer_file = template_data.pop('image_answer_file_name')

        # Write necessary files into the network drive
        child_span = opentracing.tracer.start_span('write_files_to_network_drive', child_of=span)
        file_write_success = Linux._generate_network_drive_files(vm_id, answer_file, template_data)
        child_span.finish()

        if not file_write_success:
            # The method will log which part failed, so we can just exit
            span.set_tag('failed_reason', 'network_drive_files_failed_to_write')
            return False

        # Generate the two commands that will be run on the host machine directly
        child_span = opentracing.tracer.start_span('generate_commands', child_of=span)
        bridge_build_cmd, vm_build_cmd = Linux._generate_host_commands(vm_id, template_data)
        child_span.finish()

        # Open a client and run the two necessary commands on the host
        built = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            # Try connecting to the host and running the necessary commands
            client.connect(hostname=host_ip, username='administrator')  # No need for password as it should have keys
            span.set_tag('host', host_ip)

            # Attempt to execute the bridge build commands
            Linux.logger.debug(f'Executing bridge build commands for VM #{vm_id}')

            child_span = opentracing.tracer.start_span('build_bridge', child_of=span)
            stdout, stderr = Linux.deploy(bridge_build_cmd, client, child_span)
            child_span.finish()

            if stdout:
                Linux.logger.debug(f'Bridge build commands for VM #{vm_id} generated stdout.\n{stdout}')
            if stderr:
                Linux.logger.warning(f'Bridge build commands for VM #{vm_id} generated stderr.\n{stderr}')

            # Now attempt to execute the vm build command
            Linux.logger.debug(f'Executing vm build command for VM #{vm_id}')

            child_span = opentracing.tracer.start_span('build_vm', child_of=span)
            stdout, stderr = Linux.deploy(vm_build_cmd, client, child_span)
            child_span.finish()

            if stdout:
                Linux.logger.debug(f'VM build command for VM #{vm_id} generated stdout.\n{stdout}')
            if stderr:
                Linux.logger.warning(f'VM build command for VM #{vm_id} generated stderr.\n{stderr}')
            built = 'Domain creation completed' in stdout

        except SSHException:
            Linux.logger.error(
                f'Exception occurred while building VM #{vm_id} in {host_ip}',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()

        # remove the generated files from the network drive
        child_span = opentracing.tracer.start_span('delete_files_from_network_drive', child_of=span)
        Linux._remove_network_drive_files(vm_id, template_data)
        child_span.finish()

        return built

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :returns: The data needed for the templates to build a Linux VM
        """
        vm_id = vm_data['id']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["project"]["id"]}_{vm_id}'
        data['image_filename'] = vm_data['image']['filename']
        data['image_answer_file_name'] = vm_data['image']['answer_file_name']
        data['image_os_variant'] = vm_data['image']['os_variant']
        # RAM is needed in MB for the builder but we take it in GB (1024, not 1000)
        data['ram'] = vm_data['ram'] * 1024
        data['cpu'] = vm_data['cpu']
        data['dns'] = vm_data['dns']

        # Generate encrypted passwords
        admin_password = Linux._password_generator(size=12)
        data['admin_password'] = admin_password
        # Also save the password back to the VM data dict
        vm_data['admin_password'] = admin_password
        data['crypted_admin_password'] = str(crypt(admin_password, mksalt(METHOD_SHA512)))
        root_password = Linux._password_generator(size=128)
        data['crypted_root_password'] = str(crypt(root_password, mksalt(METHOD_SHA512)))

        # Check for the primary storage
        primary: bool = False
        for storage in vm_data['storages']:
            if storage['primary']:
                primary = True
        if not primary:
            Linux.logger.error(
                f'No primary storage drive found. Expected one primary storage drive',
            )
            return None

        data['storages'] = vm_data['storages']
        data['storage_type'] = vm_data['storage_type']

        # Get the Networking details
        data['ip_address'] = vm_data['ip_address']['address']
        net = IPNetwork(vm_data['ip_address']['subnet']['address_range'])
        data['gateway'], data['netmask'] = str(net.ip), str(net.netmask)
        data['vlan'] = vm_data['ip_address']['subnet']['vlan']

        # Add locale data to the VM
        data['keyboard'] = 'ie'
        data['language'] = 'en_IE'
        data['timezone'] = 'Europe/Dublin'

        # Get the ip address of the host
        host_ip = None
        for interface in vm_data['server_data']['interfaces']:
            if interface['enabled'] is True and interface['ip_address'] is not None:
                if IPAddress(str(interface['ip_address'])).version == 6:
                    host_ip = interface['ip_address']
                    break
        if host_ip is None:
            Linux.logger.error(
                f'Host ip address not found for the server # {vm_data["server_id"]}',
            )
            return None
        data['host_ip'] = host_ip

        # Add the host information to the data
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD
        data['network_drive_path'] = settings.KVM_HOST_NETWORK_DRIVE_PATH
        data['vms_path'] = settings.KVM_VMS_PATH
        return data

    @staticmethod
    def _generate_network_drive_files(vm_id: int, answer_file_name: str, template_data: Dict[str, Any]) -> bool:
        """
        Generate and write files into the network drive so they are on the host for the build scripts to utilise.
        Writes the following files to the drive;
            - answer file
            - bridge definition file
        :param vm_id: The id of the VM being built. Used for log messages
        :param answer_file_name: The name of the image's answer_file_name file used to build the VM
        :param template_data: The retrieved template data for the kvm vm
        :returns: A flag stating whether or not the job was successful
        """
        network_drive_path = settings.KVM_ROBOT_NETWORK_DRIVE_PATH

        # Render and attempt to write the answer file
        template_name = f'vm/kvm/answer_files/{answer_file_name}.j2'
        answer_file_data = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Linux.logger.debug(f'Generated answer file for VM #{vm_id}\n{answer_file_data}')
        try:
            # Attempt to write
            answer_file_path = f'{network_drive_path}/answer_files/{template_data["vm_identifier"]}.cfg'
            with open(answer_file_path, 'w') as f:
                f.write(answer_file_data)
            Linux.logger.debug(f'Successfully wrote answer file for VM #{vm_id} to {answer_file_path}')
        except IOError:
            Linux.logger.error(
                f'Failed to write answer file for VM #{vm_id} to {answer_file_path}',
                exc_info=True,
            )
            return False

        # Render and attempt to write the bridge definition file
        template_name = 'vm/kvm/bridge/definition.j2'
        bridge_def = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Linux.logger.debug(f'Generated bridge definition file for VM #{vm_id}\n{bridge_def}')
        try:
            # Attempt to write
            bridge_def_filename = f'{network_drive_path}/bridge_xmls/br{template_data["vlan"]}.xml'
            with open(bridge_def_filename, 'w') as f:
                f.write(bridge_def)
            Linux.logger.debug(f'Successfully wrote bridge definition file for VM #{vm_id} to {bridge_def_filename}')
        except IOError:
            Linux.logger.error(
                f'Failed to write bridge definition file for VM #{vm_id} to {bridge_def_filename}',
                exc_info=True,
            )
            return False

        # Return True as all was successful
        return True

    @staticmethod
    def _generate_host_commands(vm_id: int, template_data: Dict[str, Any]) -> Tuple[str, str]:
        """
        Generate the commands that need to be run on the host machine to build the infrastructure
        Generates the following commands;
            - command to build the bridge interface
            - command to build the VM itself
        :param vm_id: The id of the VM being built. Used for log messages
        :param template_data: The retrieved template data for the vm
        :returns: A flag stating whether or not the job was successful
        """
        # Render the bridge build commands
        bridge_cmd = utils.JINJA_ENV.get_template('vm/kvm/bridge/build.j2').render(**template_data)
        Linux.logger.debug(f'Generated bridge build command for VM #{vm_id}\n{bridge_cmd}')

        # Render the VM build command
        vm_cmd = utils.JINJA_ENV.get_template('vm/kvm/commands/build.j2').render(**template_data)
        Linux.logger.debug(f'Generated vm build command for VM #{vm_id}\n{vm_cmd}')

        return bridge_cmd, vm_cmd

    @staticmethod
    def _remove_network_drive_files(vm_id: int, template_data: Dict[str, Any]):
        """
        Removes files from the network drive as they are not necessary after build and are not supposed to be left.
        Remove the following files from the drive;
            - answer file
            - bridge definition file
        :param vm_id: The id of the VM being built. Used for log messages
        :param template_data: The retrieved template data for the vm
        """
        network_drive_path = settings.KVM_ROBOT_NETWORK_DRIVE_PATH

        # Remove answer file
        file_path = f'answer_files/{template_data["vm_identifier"]}.cfg'
        answer_file_path = os.path.join(network_drive_path, file_path)
        if os.path.exists(answer_file_path):
            try:
                os.remove(answer_file_path)
                Linux.logger.debug(f'Successfully removed answer file {answer_file_path} of VM #{vm_id}')
            except IOError:
                Linux.logger.error(
                    f'Exception occurred while attempting to delete {file_path} from the network drive for VM #{vm_id}',
                    exc_info=True,
                )

        # Remove bridge xml file
        file_path = f'bridge_xmls/br{template_data["vlan"]}.xml'
        bridge_def_filename = os.path.join(network_drive_path, file_path)
        if os.path.exists(bridge_def_filename):
            try:
                os.remove(bridge_def_filename)
                Linux.logger.debug(f'Successfully removed bridge definition file {bridge_def_filename} of VM #{vm_id}')
            except IOError:
                Linux.logger.error(
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
