"""
scrubber class for linux vms

- gathers template data
- connects to the vm's host and runs commands to delete the VM on it
"""
# stdlib
import logging
import socket
from typing import Any, Dict, List, Optional

# lib
import opentracing
from cloudcix.api.iaas import IAAS
from cloudcix.lock import ResourceLock
from jaeger_client import Span
from netaddr import IPAddress
from paramiko import AutoAddPolicy, RSAKey, SSHClient, SSHException
# local
import settings
import state
from mixins import LinuxMixin
from utils import api_list, JINJA_ENV, Targets


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
        # the ip address of the host that the VM to scrub is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # storage type (HDD/SSD)
        'storage_type',
        # storages of the vm
        'storages',
        # the vlans that the vm is a part of
        'vlans',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
        # path for vm's .img files located in host
        'vms_path',
    }

    @staticmethod
    def scrub(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the scrub of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param span: The tracing span for the scrub task
        :return: A flag stating whether or not the scrub was successful
        """
        vm_id = vm_data['id']

        # Generate the necessary template data
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Linux._get_template_data(vm_data)
        child_span.finish()

        # Check that the data was successfully generated
        if template_data is None:
            error = f'Failed to retrieve template data for VM #{vm_id}.'
            Linux.logger.error(error)
            vm_data['errors'].append(error)
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Linux.template_keys):
            missing_keys = [f'"{key}"' for key in Linux.template_keys if template_data[key] is None]
            error_msg = f'Template Data Error, the following keys were missing from the VM scrub data: ' \
                        f'{", ".join(missing_keys)}.'
            Linux.logger.error(error_msg)
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # Generate the commands that will be run on the host machine directly
        child_span = opentracing.tracer.start_span('generate_commands', child_of=span)
        vm_scrub_cmd = Linux._generate_host_commands(vm_id, template_data)
        child_span.finish()

        # If everything is okay, commence scrubbing the VM
        host_ip = template_data.pop('host_ip')

        # Open a client and run the two necessary commands on the host
        scrubbed = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        key = RSAKey.from_private_key_file('/root/.ssh/id_rsa')
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            # Try connecting to the host and running the necessary commands
            sock.connect((host_ip, 22))
            client.connect(
                hostname=host_ip,
                username='administrator',
                pkey=key,
                timeout=30,
                sock=sock,
            )  # No need for password as it should have keys
            span.set_tag('host', host_ip)

            # Now attempt to execute the vm scrub command
            Linux.logger.debug(f'Executing vm scrub command for VM #{vm_id}')
            child_span = opentracing.tracer.start_span('scrub_vm', child_of=span)
            stdout, stderr = Linux.deploy(vm_scrub_cmd, client, child_span)
            child_span.finish()

            if stdout:
                Linux.logger.debug(f'VM scrub command for VM #{vm_id} generated stdout.\n{stdout}')
                scrubbed = True
            if stderr:
                Linux.logger.error(f'VM scrub command for VM #{vm_id} generated stderr.\n{stderr}')

        except (OSError, SSHException, TimeoutError) as err:
            error = f'Exception occurred while scrubbing VM #{vm_id} in {host_ip}.'
            Linux.logger.error(error, exc_info=True)
            vm_data['errors'].append(f'{error} Error: {err}')
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()
        return scrubbed

    @staticmethod
    def get_host_ip(vm_data):
        host_ip = None
        for interface in vm_data['server_data']['interfaces']:
            if interface['enabled'] is True and interface['ip_address'] is not None:
                if IPAddress(str(interface['ip_address'])).version == 6:
                    host_ip = interface['ip_address']
                    break
        return host_ip

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
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD
        data['storages'] = vm_data['storages']
        data['storage_type'] = vm_data['storage_type']
        data['vms_path'] = settings.KVM_VMS_PATH

        # Get the Networking details
        vlans = [ip['subnet']['vlan'] for ip in vm_data['ip_addresses']]
        data['vlans'] = set(vlans)

        # Get the ip address of the host
        host_ip = Linux.get_host_ip(vm_data)
        if host_ip is None:
            error = f'Host ip address not found for the server # {vm_data["server_id"]}.'
            Linux.logger.error(error)
            vm_data['errors'].append(error)
            return None
        data['host_ip'] = host_ip

        return data

    @staticmethod
    def _generate_host_commands(vm_id: int, template_data: Dict[str, Any]) -> str:
        """
        Generate the commands that need to be run on the host machine to scrub the infrastructure
        Generates the command to scrub the VM itself
        :param vm_id: The id of the VM being built. Used for log messages
        :param template_data: The retrieved template data for the vm
        :returns: vm_scrub_command
        """
        # Render the VM scrub command
        vm_cmd = JINJA_ENV.get_template('vm/kvm/commands/scrub.j2').render(**template_data)
        Linux.logger.debug(f'Generated vm scrub command for VM #{vm_id}\n{vm_cmd}')

        return vm_cmd

    @staticmethod
    def _determine_bridge_deletion(vm_data: Dict[str, Any], span: Span) -> List[str]:
        """
        Given a VM, determine vlan bridges to delete.
        We need to delete the bridges if the VM is the last Linux VM left in the Subnet

        Steps:
            1. Get all other VMs on this VM's server in the same project.
            2. Find all the subnets(vlans) of the VM being deleted
            3. Find all the subnets(vlans) of all other VMs from the first step
            4. Compare vlans from step 2 and step 3 and find out the vlans on this VM to be deleted
               that are not in the list of other VMs vlans
        """
        vm_id = vm_data['id']
        server_id = vm_data['server_id']
        project_id = vm_data['project']['id']

        # Get all other VMs that are on the same Server of the same project.
        params = {
            'exclude[state]': state.CLOSED,
            'search[server_id]': server_id,
            'search[project_id]': project_id,
        }
        # Critical section
        requestor = f'Scrub Bridge for Scrub Linux VM #{vm_id}'
        region_id = vm_data['project']['region_id']
        endpoint = f'VMs List for Project#{project_id} Server#{server_id}'
        target = Targets.API.generate_id(
            region_id=region_id,
            endpoint=endpoint,
        )
        child_span = opentracing.tracer.start_span('api_list_other_vms', child_of=span)
        with ResourceLock(target, requestor, child_span):
            other_vms_on_server = api_list(IAAS.vm, params, span=span)
        child_span.finish()

        # Get all subnet vlans of the VM
        subnet_vlans = []
        for ip in vm_data['ip_addresses']:
            subnet_vlans.append(ip['subnet']['vlan'])

        # For each vm in other_vms_on_server, get a list of their subnet vlans
        other_vms_subnet_vlans = []
        for vm in other_vms_on_server:
            for ip in vm['ip_addresses']:
                other_vms_subnet_vlans.append(ip['subnet']['vlan'])

        # if a vlan is not in other_vms_subnet_vlans,
        # add to remove list as it is not in use by another vm on VM's server
        vlans_to_be_removed = set()
        for vlan in subnet_vlans:
            if vlan not in other_vms_subnet_vlans:
                vlans_to_be_removed.add(str(vlan))

        return list(vlans_to_be_removed)

    @staticmethod
    def remove_bridges(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        1. Determines vlan bridges to be removed.
        2. Generates bridge scrub commands for a list of vlans to be removed
        3. Runs the bridge scrub commands on the VM's host
        """
        child_span = opentracing.tracer.start_span('determine_bridge_deletion', child_of=span)
        vlans_to_be_removed = Linux._determine_bridge_deletion(vm_data, child_span)
        child_span.finish()

        if not len(vlans_to_be_removed) > 0:
            return True

        vm_id = vm_data['id']
        # Get the ip address of the host
        host_ip = Linux.get_host_ip(vm_data)
        if host_ip is None:
            error = f'Host ip address not found for the server # {vm_data["server_id"]}.'
            Linux.logger.error(error)
            vm_data['errors'].append(error)
            return False

        # Render the bridge scrub command if bridges to delete are present
        bridge_scrub_cmd = JINJA_ENV.get_template('vm/kvm/bridge/scrub.j2').render(
            host_sudo_passwd=settings.NETWORK_PASSWORD,
            vlans_to_be_removed=vlans_to_be_removed,
        )
        Linux.logger.debug(f'Generated bridge scrub command for VM #{vm_id}\n{bridge_scrub_cmd}')

        removed = False
        # Open a client and run the necessary commands on the host
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        key = RSAKey.from_private_key_file('/root/.ssh/id_rsa')
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            # Try connecting to the host and running the necessary commands
            sock.connect((host_ip, 22))
            client.connect(
                hostname=host_ip,
                username='administrator',
                pkey=key,
                timeout=30,
                sock=sock,
            )  # No need for password as it should have keys
            span.set_tag('host', host_ip)

            Linux.logger.debug(f'Deleting bridges # {", ".join(vlans_to_be_removed)} for VM #{vm_id}')

            child_span = opentracing.tracer.start_span('scrub_bridge', child_of=span)
            # Critical section
            requestor = f'Scrub Bridge for Scrub Linux VM #{vm_id}'
            region_id = vm_data['project']['region_id']
            server = vm_data['server_data']['type']['name']
            target = Targets.HOST.generate_id(
                region_id=region_id,
                server_type_name=server,
                server_id=vm_data['server_id'],
            )
            with ResourceLock(target, requestor, child_span):
                stdout, stderr = Linux.deploy(bridge_scrub_cmd, client, child_span)
            child_span.finish()
            # In this case it is observed that for a successful deletion of bridge, stdout and stderr are None
            # so considering this as success
            removed = True
            if stdout:
                Linux.logger.debug(f'Bridge scrub command for VM #{vm_id} generated stdout\n{stdout}')
            if stderr:
                Linux.logger.error(f'Bridge scrub command for VM #{vm_id} generated stderr\n{stderr}')
                removed = False

        except (OSError, SSHException, TimeoutError) as err:
            error = f'Exception occurred while removing bridges for VM #{vm_id} in {host_ip}.'
            Linux.logger.error(error, exc_info=True)
            vm_data['errors'].append(f'{error} Error: {err}')
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()
        return removed
