"""
quiescer class for linux vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
from typing import Any, Dict, Optional
# lib
from cloudcix.api import IAAS
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
    Class that handles the quiescing of the specified VM
    When we get to this point, we can be sure that the VM is a linux VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('quiescers.vm.linux')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before quiescing
    template_keys = {
        # the ip address of the host that the VM to quiesce is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def quiesce(vm_data: Dict[str, Any]) -> bool:
        """
        Commence the quiesce of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :return: A flag stating whether or not the quiesce was successful
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
                f'Template Data Error, the following keys were missing from the VM quiesce data: '
                f'{", ".join(missing_keys)}',
            )
            return False

        # If everything is okay, commence quiescing the VM
        host_ip = template_data.pop('host_ip')

        # Generate the quiesce command using the template data
        cmd = utils.JINJA_ENV.get_template('vm/linux/quiesce_cmd.j2').render(**template_data)
        Linux.logger.debug(f'Generated VM quiesce command for VM #{vm_data["idVM"]}\n{cmd}')

        # Open a client and run the two necessary commands on the host
        quiesced = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            # Try connecting to the host and running the necessary commands
            client.connect(hostname=host_ip, username='administrator')  # No need for password as it should have keys

            # Attempt to execute the quiesce command
            Linux.logger.debug(f'Executing quiesce command for VM #{vm_id}')
            stdout, stderr = Linux.deploy(cmd, client)
            if stdout:
                Linux.logger.debug(f'VM quiesce command for VM #{vm_id} generated stdout.\n{stdout}')
                quiesced = True
            if stderr:
                Linux.logger.warning(f'VM quiesce command for VM #{vm_id} generated stderr.\n{stderr}')
        except SSHException:
            Linux.logger.error(
                f'Exception occurred while quiescing VM #{vm_id} in {host_ip}',
                exc_info=True,
            )
        finally:
            client.close()
        return quiesced

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the quiesce method and not here, this method is only concerned with fetching the
        data that it can.
        :param vm_data: The data of the VM read from the API
        :returns: The data needed for the templates to quiesce a Linux VM
        """
        vm_id = vm_data['idVM']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_ip'] = mac['ip']
                break

        return data
