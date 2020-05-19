"""
updater class for linux vms

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
from paramiko import AutoAddPolicy, SSHClient, SSHException
# local
import settings
import utils
from mixins import LinuxMixin, VmUpdateMixin


__all__ = [
    'Linux',
]


class Linux(LinuxMixin, VmUpdateMixin):
    """
    Class that handles the updating of the specified VM
    When we get to this point, we can be sure that the VM is a linux VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.updaters.vm.linux')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before updating
    template_keys = {
        # the ip address of the host that the VM is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # a flag stating whether or not the VM should be turned back on after updating it
        'restart',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
        # changes for updates
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

            if template_data['restart']:
                # Also render and deploy the restart_cmd template
                restart_cmd = utils.JINJA_ENV.get_template('vm/linux/restart_cmd.j2').render(**template_data)

                # Attempt to execute the restart command
                Linux.logger.debug(f'Executing restart command for VM #{vm_id}')
                child_span = opentracing.tracer.start_span('restart_vm', child_of=span)
                stdout, stderr = Linux.deploy(restart_cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM restart command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.warning(f'VM restart command for VM #{vm_id} generated stderr.\n{stderr}')
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
        # changes
        changes: Dict[str, Any] = {
            'ram': False,
            'cpu': False,
            'storages': False,
        }
        changes_this_month = vm_data['changes_this_month'][0]
        try:
            if changes_this_month['ram_quantity']:
                # RAM is needed in MB for the updater but we take it in in GB (1024, not 1000)
                changes['ram'] = vm_data['ram'] * 1024
        except KeyError:
            pass
        try:
            if changes_this_month['cpu_quantity']:
                changes['cpu'] = vm_data['cpu']
        except KeyError:
            pass
        # Fetch the drive information for the update
        try:
            if len(changes_this_month['storage_histories']) != 0:
                Linux.logger.debug(f'Fetching drives for VM #{vm_id}')
                hdd, ssd, drives = Linux.fetch_drive_updates(vm_data, span)
                changes['storages'] = {
                    'hdd': hdd,
                    'ssd': ssd,
                    'drives': drives,
                }
        except KeyError:
            pass
        # Add changes to data
        data['changes'] = changes

        # Get the ip address of the host
        Linux.logger.debug(f'Fetching host address for VM #{vm_id}')
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer'], span=span):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_ip'] = mac['ip']
                break

        # Add the host information to the data
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD

        # Determine whether or not we should turn the VM back on after the update finishes
        Linux.logger.debug(f'Determining if VM #{vm_id} should be powered on after update')
        data['restart'] = Linux.determine_should_restart(vm_data, span=span)
        return data
