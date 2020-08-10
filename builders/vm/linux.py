"""
builder class for linux vms

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
from crypt import crypt, mksalt, METHOD_SHA512
from typing import Any, Deque, Dict, Optional, Tuple
# lib
import opentracing
from cloudcix.api import IAAS
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

# Map that maps image ids to the name of the kickstart file that will be used for the VM
KICKSTART_TEMPLATE_MAP = settings.OS_TEMPLATE_MAP['Linux']


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
        # the admin password for the vm, pre-crpyted
        'crypted_admin_password',
        # root password encrypted, needed for centos kickstart
        'crypted_root_password',
        # the number of cpus in the vm
        'cpu',
        # the default subnet gateway
        'default_gateway',
        # default ip address of the VM
        'default_ip',
        # the default subnet mask in ip address form (255.255.255.0)
        'default_netmask',
        # the default vlan that the vm is a part of
        'default_vlan',
        # the dns servers for the vm
        'dns',
        # the drives in the vm
        'drives',
        # the hdd primary drive of the VM 'id:size'
        'hdd',
        # the ip address of the host that the VM will be built on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # the filename of the image used to build the vm
        'image_filename',
        # the non default ip addresses of the vm
        'ip_addresses',
        # the keyboard layout to use for the vm
        'keyboard',
        # the language of the vm
        'language',
        # the path on the host where the network drive is found
        'network_drive_path',
        # os name to differentiate between centos and ubuntu
        'osname',
        # the amount of RAM in the VM
        'ram',
        # the ssd primary drive of the VM 'id:size'
        'ssd',
        # the timezone of the vm
        'timezone',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
        # all subnet vlans numbers list for bridges
        'vlans',
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
        template_data = Linux._get_template_data(vm_data, image_data, child_span)
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

        # Write necessary files into the network drive
        network_drive_path = settings.KVM_ROBOT_NETWORK_DRIVE_PATH
        path = f'{network_drive_path}/VMs/{vm_data["idProject"]}_{vm_data["idVM"]}'
        child_span = opentracing.tracer.start_span('write_files_to_network_drive', child_of=span)
        file_write_success = Linux._generate_network_drive_files(vm_id, template_data, path)
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

            # Attempt to execute the bridge build command
            Linux.logger.debug(f'Executing bridge build command for VM #{vm_id}')

            child_span = opentracing.tracer.start_span('build_bridge', child_of=span)
            stdout, stderr = Linux.deploy(bridge_build_cmd, client, child_span)
            child_span.finish()

            if stdout:
                Linux.logger.debug(f'Bridge build command for VM #{vm_id} generated stdout.\n{stdout}')
            if stderr:
                Linux.logger.warning(f'Bridge build command for VM #{vm_id} generated stderr.\n{stderr}')

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

        # remove all the files created in network drive
        try:
            shutil.rmtree(path)
        except OSError:
            Linux.logger.warning(f'Failed to remove network drive files for VM #{vm_id}')

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
        :returns: The data needed for the templates to build a Linux VM
        """
        vm_id = vm_data['idVM']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        data['image_filename'] = image_data['filename']
        # RAM is needed in MB for the builder but we take it in in GB (1024, not 1000)
        data['ram'] = vm_data['ram'] * 1024
        data['cpu'] = vm_data['cpu']
        data['dns'] = vm_data['dns']

        # Generate encrypted passwords
        admin_password = Linux._password_generator(size=8)
        data['admin_password'] = admin_password
        # Also save the password back to the VM data dict
        vm_data['admin_password'] = admin_password
        data['crypted_admin_password'] = str(crypt(admin_password, mksalt(METHOD_SHA512)))
        root_password = Linux._password_generator(size=128)
        data['crypted_root_password'] = str(crypt(root_password, mksalt(METHOD_SHA512)))

        # Fetch the drives for the VM and add them to the data
        drives: Deque[Dict[str, str]] = deque()
        for storage in utils.api_list(IAAS.storage, {}, vm_id=vm_id, span=span):
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
            net = IPNetwork(subnet['addressRange'])
            gateway, netmask = str(net.ip), str(net.netmask)
            vlan = str(subnet['vLAN'])
            data['vlans'].append(vlan)

            # Pick the default ip
            if subnet['idSubnet'] == vm_data['gateway_subnet']['idSubnet']:
                data['default_ip'] = ip
                data['default_gateway'] = gateway
                data['default_netmask'] = netmask
                data['default_vlan'] = vlan
                continue
            data['ip_addresses'].append(
                {
                    'ip': ip,
                    'gateway': gateway,
                    'netmask': netmask,
                    'vlan': vlan,
                },
            )

        # Add locale data to the VM
        data['keyboard'] = 'ie'
        data['language'] = 'en_IE'
        data['timezone'] = 'Europe/Dublin'

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer'], span=span):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_ip'] = mac['ip']
                break

        # Add the host information to the data
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD
        data['network_drive_path'] = settings.KVM_HOST_NETWORK_DRIVE_PATH

        # Determine the kickstart template to use for the VM
        os_name = KICKSTART_TEMPLATE_MAP.get(image_data['idImage'], None)
        if os_name is None:
            valid_ids = ', '.join(f'`{map_id}`' for map_id in KICKSTART_TEMPLATE_MAP.keys())
            Linux.logger.error(
                f'Invalid Linux Image ID for VM #{vm_id}. '
                f'Received {image_data["idImage"]}, valid choices are {valid_ids}.',
            )
            return None
        data['osname'] = os_name

        return data

    @staticmethod
    def _generate_network_drive_files(vm_id: int, template_data: Dict[str, Any], path: str) -> bool:
        """
        Generate and write files into the network drive so they are on the host for the build scripts to utilise.
        Writes the following files to the drive;
            - kickstart file
            - bridge definition file
        :param vm_id: The id of the VM being built. Used for log messages
        :param template_data: The retrieved template data for the vm
        :param path: Network drive location to create above files for VM build
        :returns: A flag stating whether or not the job was successful
        """
        # Create a folder by vm_identifier name at network_drive_path/VMs/
        try:
            os.mkdir(path)
        except OSError:
            Linux.logger.error(
                f'Failed to create directory for VM #{vm_id} at {path}',
                exc_info=True,
            )
            return False

        # Render and attempt to write the kickstart file
        template_name = f'vm/linux/kickstarts/{template_data["osname"]}.j2'
        kickstart = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Linux.logger.debug(f'Generated kickstart file for VM #{vm_id}\n{kickstart}')
        try:
            # Attempt to write
            kickstart_filename = f'{path}/{template_data["vm_identifier"]}.cfg'
            with open(kickstart_filename, 'w') as f:
                f.write(kickstart)
            Linux.logger.debug(f'Successfully wrote kickstart file for VM #{vm_id} to {kickstart_filename}')
        except IOError:
            Linux.logger.error(
                f'Failed to write kickstart file for VM #{vm_id} to {kickstart_filename}',
                exc_info=True,
            )
            return False

        # Render and attempt to write the bridge definition file
        for vlan in template_data['vlans']:
            template_name = 'kvm/bridge_definition.j2'
            bridge_def = utils.JINJA_ENV.get_template(template_name).render(vlan=vlan)
            Linux.logger.debug(f'Generated bridge definition file for VM #{vm_id}\n{bridge_def}')
            try:
                # Attempt to write
                bridge_def_filename = f'{path}/br{vlan}.xml'
                with open(bridge_def_filename, 'w') as f:
                    f.write(bridge_def)
                Linux.logger.debug(
                    f'Successfully wrote bridge definition file for VM #{vm_id} to {bridge_def_filename}',
                )
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
        # Render the bridge build command
        bridge_cmd = utils.JINJA_ENV.get_template('kvm/bridge_build_cmd.j2').render(**template_data)
        Linux.logger.debug(f'Generated bridge build command for VM #{vm_id}\n{bridge_cmd}')

        # Render the VM build command
        vm_cmd = utils.JINJA_ENV.get_template('vm/linux/build_cmd.j2').render(**template_data)
        Linux.logger.debug(f'Generated vm build command for VM #{vm_id}\n{vm_cmd}')

        return bridge_cmd, vm_cmd

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
