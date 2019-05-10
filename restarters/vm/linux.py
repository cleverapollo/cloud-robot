"""
restarter class for linux vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
from typing import Any, Dict, Optional
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
from opentracing import tracer
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
    Class that handles the restarting of the specified VM
    When we get to this point, we can be sure that the VM is a linux VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.restarters.vm.linux')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before restarting
    template_keys = {
        # the ip address of the host that the VM to restart is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def restart(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the restart of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param span: The tracing span for the restart task
        :return: A flag stating whether or not the restart was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        child_span = tracer.start_span('generate_template_data', child_of=span)
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
                f'Template Data Error, the following keys were missing from the VM restart data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence restarting the VM
        host_ip = template_data.pop('host_ip')

        # Generate the restart command using the template data
        child_span = tracer.start_span('generate_command', child_of=span)
        cmd = utils.JINJA_ENV.get_template('vm/linux/restart_cmd.j2').render(**template_data)
        child_span.finish()

        Linux.logger.debug(f'Generated VM restart command for VM #{vm_data["idVM"]}\n{cmd}')

        # Open a client and run the two necessary commands on the host
        restarted = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            # Try connecting to the host and running the necessary commands
            client.connect(hostname=host_ip, username='administrator')  # No need for password as it should have keys
            span.set_tag('host', host_ip)

            # Attempt to execute the restart command
            Linux.logger.debug(f'Executing restart command for VM #{vm_id}')

            child_span = tracer.start_span('restart_vm', child_of=span)
            stdout, stderr = Linux.deploy(cmd, client, child_span)
            child_span.finish()

            if stdout:
                Linux.logger.debug(f'VM restart command for VM #{vm_id} generated stdout.\n{stdout}')
                restarted = True
            if stderr:
                Linux.logger.warning(f'VM restart command for VM #{vm_id} generated stderr.\n{stderr}')
        except SSHException:
            Linux.logger.error(
                f'Exception occurred while restarting VM #{vm_id} in {host_ip}',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()
        return restarted

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the restart method and not here, this method is only concerned with fetching the
        data that it can.
        :param vm_data: The data of the VM read from the API
        :param span: The tracing span in use for this task. In this method, just pass it to API calls.
        :returns: The data needed for the templates to restart a Linux VM
        """
        vm_id = vm_data['idVM']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer'], span=span):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_ip'] = mac['ip']
                break

        return data
