"""
updater class for windows vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
from typing import Any, Dict, Optional
# lib
import opentracing
from cloudcix.api import IAAS
from jaeger_client import Span
from netaddr import IPAddress, IPNetwork
from winrm.exceptions import WinRMError
# local
import utils
from mixins import VmUpdateMixin, WindowsMixin


__all__ = [
    'Windows',
]


class Windows(WindowsMixin, VmUpdateMixin):
    """
    Class that handles the updating of the specified VM
    When we get to this point, we can be sure that the VM is a windows VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.updaters.vm.windows')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before updating
    template_keys = {
        # # the admin password for the vm, unencrypted
        # 'admin_password',
        # the default subnet gateway
        'default_gateway',
        # default ip address of the VM
        'default_ip',
        # the default subnet mask in integer form (/24)
        'default_netmask_int',
        # the default vlan that the vm is a part of
        'default_vlan',
        # the dns servers for the vm
        'dns',
        # the non default ip addresses of the vm
        'ip_addresses',
        # a flag stating whether or not the VM should be turned back on after updating it
        'restart',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
        # changes of vm
        'changes',
    }

    @staticmethod
    def update(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the update of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param span: The tracing span in use for this update task
        :return: A flag stating whether or not the update was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Windows._get_template_data(vm_data, child_span)
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
                f'Template Data Error, the following keys were missing from the VM update data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence updating the VM
        host_name = template_data.pop('host_name')

        # Render the update command
        child_span = opentracing.tracer.start_span('generate_command', child_of=span)
        cmd = utils.JINJA_ENV.get_template('vm/windows/update_cmd.j2').render(**template_data)
        child_span.finish()

        # Open a client and run the two necessary commands on the host
        updated = False
        try:
            child_span = opentracing.tracer.start_span('update_vm', child_of=span)
            response = Windows.deploy(cmd, host_name, child_span)
            span.set_tag('host', host_name)
            child_span.finish()
        except WinRMError:
            Windows.logger.error(
                f'Exception occurred while attempting to update VM #{vm_id} on {host_name}',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'winrm_error')
        else:
            # Check the stdout and stderr for messages
            if response.std_out:
                msg = response.std_out.strip()
                Windows.logger.debug(f'VM update command for VM #{vm_id} generated stdout\n{msg}')
                updated = 'VM Successfully Updated' in msg
            # Check if the error was parsed to ensure we're not logging invalid std_err output
            if response.std_err and '#< CLIXML\r\n' not in response.std_err:
                msg = response.std_err.strip()
                Windows.logger.warning(f'VM update command for VM #{vm_id} generated stderr\n{msg}')

            # Check if we need to restart the VM as well
            if template_data['restart']:
                # Also render and deploy the restart_cmd template
                restart_cmd = utils.JINJA_ENV.get_template('vm/windows/restart_cmd.j2').render(**template_data)

                # Attempt to execute the restart command
                Windows.logger.debug(f'Executing restart command for VM #{vm_id}')
                child_span = opentracing.tracer.start_span('restart_vm', child_of=span)
                response = Windows.deploy(restart_cmd, host_name, child_span)
                child_span.finish()

                if response.std_out:
                    msg = response.std_out.strip()
                    Windows.logger.debug(f'VM restart command for VM #{vm_id} generated stdout\n{msg}')
                # Check if the error was parsed to ensure we're not logging invalid std_err output
                if response.std_err and '#< CLIXML\r\n' not in response.std_err:
                    msg = response.std_err.strip()
                    Windows.logger.warning(f'VM restart command for VM #{vm_id} generated stderr\n{msg}')
        return updated

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the update method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :param span: The tracing span in use for this task. In this method just pass it to API calls
        :returns: The data needed for the templates to update a Windows VM
        """
        vm_id = vm_data['idVM']
        Windows.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Windows.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        data['dns'] = vm_data['dns'].replace(',', '", "')

        # changes
        changes: Dict[str, Any] = {
            'ram': False,
            'cpu': False,
            'storages': False,
        }
        updates = vm_data['history'][0]
        try:
            if updates['ram_quantity'] is not None:
                # RAM is needed in MB for the updater but we take it in in GB (1024, not 1000)
                changes['ram'] = vm_data['ram'] * 1024
        except KeyError:
            pass
        try:
            if updates['cpu_quantity'] is not None:
                changes['cpu'] = vm_data['cpu']
        except KeyError:
            pass

        # Fetch the drive information for the update
        try:
            if len(updates['storage_histories']) != 0:
                Windows.logger.debug(f'Fetching drives for VM #{vm_id}')
                hdd, ssd, drives = Windows.fetch_drive_updates(vm_data, span)
                changes['storages'] = {
                    'hdd': hdd,
                    'ssd': ssd,
                    'drives': drives,
                }
        except KeyError:
            pass
        # Add changes to data
        data['changes'] = changes

        # Get the Networking details
        # TODO will update with multiple IPs stuff
        Windows.logger.debug(f'Fetching networking information for VM #{vm_id}')
        for ip_address in utils.api_list(IAAS.ipaddress, {'vm': vm_id}, span=span):
            # The private IP for the VM will be the one we need to pass to the template
            if not IPAddress(ip_address['address']).is_private():
                continue
            data['ip_address'] = ip_address['address']
            # Read the subnet for the IPAddress to fetch information like the gateway and subnet mask
            subnet = utils.api_read(IAAS.subnet, ip_address['idSubnet'], span=span)
            if subnet is None:
                return None
            data['gateway'], _ = subnet['addressRange'].split('/')
            data['netmask'] = IPNetwork(subnet['addressRange']).netmask
            data['vlan'] = subnet['vLAN']

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer'], span=span):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_name'] = mac['dnsName']
                break

        # Determine whether or not we should turn the VM back on after the update finishes
        Windows.logger.debug(f'Determining if VM #{vm_id} should be powered on after update')
        data['restart'] = Windows.determine_should_restart(vm_data, span=span)
        return data
