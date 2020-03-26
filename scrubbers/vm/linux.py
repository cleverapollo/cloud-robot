"""
scrubber class for linux vms

- gathers template data
- connects to the vm's host and runs commands to delete the VM on it
"""
# stdlib
import logging
from typing import Any, Dict, Optional, Tuple
# lib
import opentracing
from cloudcix.api.compute import Compute
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
        # the ip address of the host that the VM to scrub is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # storage type (HDD/SSD)
        'storage_type'
        # storages of the vm
        'storages',
        # the vlan that the vm is a part of
        'vlan',
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
                f'Template Data Error, the following keys were missing from the VM scrub data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence scrubbing the VM
        host_ip = template_data.pop('host_ip')
        delete_bridge = template_data.pop('delete_bridge')

        # Generate the two commands that will be run on the host machine directly
        child_span = opentracing.tracer.start_span('generate_commands', child_of=span)
        bridge_scrub_cmd, vm_scrub_cmd = Linux._generate_host_commands(vm_id, template_data)
        child_span.finish()

        # Open a client and run the two necessary commands on the host
        scrubbed = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            # Try connecting to the host and running the necessary commands
            client.connect(hostname=host_ip, username='administrator')  # No need for password as it should have keys
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
                Linux.logger.warning(f'VM scrub command for VM #{vm_id} generated stderr.\n{stderr}')

            # Check if we also need to run the command to delete the bridge
            if delete_bridge:
                Linux.logger.debug(f'Deleting bridge for VM #{vm_id}')

                child_span = opentracing.tracer.start_span('scrub_bridge', child_of=span)
                stdout, stderr = Linux.deploy(bridge_scrub_cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'Bridge scrub command for VM #{vm_id} generated stdout\n{stdout}')
                if stderr:
                    Linux.logger.warning(f'Bridge scrub command for VM #{vm_id} generated stderr\n{stderr}')

        except SSHException:
            Linux.logger.error(
                f'Exception occurred while scrubbing VM #{vm_id} in {host_ip}',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()
        return scrubbed

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :param span: The tracing span in use for this task. In this method, just pass it to API calls.
        :returns: The data needed for the templates to build a Linux VM
        """
        vm_id = vm_data['id']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["project"]["id"]}_{vm_id}'
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD
        data['storages'] = vm_data['storages']
        data['storage_type'] = vm_data['storage_type']
        data['vlan'] = vm_data['ip_address']['subnet']['vlan']
        data['vms_path'] = settings.KVM_VMS_PATH

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

        child_span = opentracing.tracer.start_span('determine_bridge_deletion', child_of=span)
        data['delete_bridge'] = Linux._determine_bridge_deletion(vm_data, child_span)
        child_span.finish()
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
        bridge_cmd = utils.JINJA_ENV.get_template('vm/kvm/bridge/scrub.j2').render(**template_data)
        Linux.logger.debug(f'Generated bridge scrub command for VM #{vm_id}\n{bridge_cmd}')

        # Render the VM scrub command
        vm_cmd = utils.JINJA_ENV.get_template('vm/kvm/commands/scrub.j2').render(**template_data)
        Linux.logger.debug(f'Generated vm scrub command for VM #{vm_id}\n{vm_cmd}')

        return bridge_cmd, vm_cmd

    @staticmethod
    def _determine_bridge_deletion(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Given a VM, determine if we need to delete it's bridge.
        We need to delete the bridge if the VM is the last one left in the Subnet on the Server.

        Steps:
            - Get all other VMs in the same Server of this VM and of the same Project of this VM.
            - Filter out the VMs list with this VM's subnet id (we get the list of VMs in the vlan of this VM).
            - If the list is empty then the Bridge needs to be deleted, other wise not.
        """
        bridge: bool = False
        vm_id = vm_data['id']
        # Get the list of VMs with following params
        params = {
            'search[exclude__id]': vm_id,
            'search[project_id]': vm_data['project']['id'],
            'search[server_id]': vm_data['server_id'],
        }
        vms = utils.api_list(Compute.vm, params, span=span)

        subnet_vms_ids = [
            vm['id'] for vm in vms if vm['ip_address']['subnet']['id'] == vm_data['ip_address']['subnet']['id']
        ]

        if len(subnet_vms_ids) == 0:
            bridge = True

        return bridge
