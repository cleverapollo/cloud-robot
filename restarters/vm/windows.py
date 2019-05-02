"""
restarter class for windows vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
from typing import Any, Dict, Optional
# lib
from cloudcix.api import IAAS
from winrm.exceptions import WinRMError
# local
import utils
from mixins import WindowsMixin


__all__ = [
    'Windows',
]


class Windows(WindowsMixin):
    """
    Class that handles the restarting of the specified VM
    When we get to this point, we can be sure that the VM is a windows VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.restarters.vm.windows')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before restarting
    template_keys = {
        # the DNS hostname for the host machine, as WinRM cannot use IPv6
        'host_name',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def restart(vm_data: Dict[str, Any]) -> bool:
        """
        Commence the restart of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :return: A flag stating whether or not the restart was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        template_data = Windows._get_template_data(vm_data)

        # Check that the data was successfully generated
        if template_data is None:
            Windows.logger.error(
                f'Failed to retrieve template data for VM #{vm_id}.',
            )
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Windows.template_keys):
            missing_keys = [
                f'"{key}"' for key in Windows.template_keys if template_data[key] is None
            ]
            Windows.logger.error(
                f'Template Data Error, the following keys were missing from the VM restart data: '
                f'{", ".join(missing_keys)}',
            )
            return False

        # If everything is okay, commence restarting the VM
        host_name = template_data.pop('host_name')

        # Render the restart command
        cmd = utils.JINJA_ENV.get_template('vm/windows/restart_cmd.j2').render(**template_data)

        # Open a client and run the two necessary commands on the host
        restarted = False
        try:
            response = Windows.deploy(cmd, host_name)
        except WinRMError:
            Windows.logger.error(
                f'Exception occurred while attempting to restart VM #{vm_id} on {host_name}',
                exc_info=True,
            )
        else:
            # Check the stdout and stderr for messages
            if response.std_out:
                msg = response.std_out.strip()
                Windows.logger.debug(f'VM restart command for VM #{vm_id} generated stdout\n{msg}')
                restarted = f'{template_data["vm_identifier"]} Successfully Rebooted' in msg
            if response.std_err:
                msg = response.std_err.strip()
                Windows.logger.warning(f'VM restart command for VM #{vm_id} generated stderr\n{msg}')
        finally:
            return restarted

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :returns: The data needed for the templates to build a Windows VM
        """
        vm_id = vm_data['idVM']
        Windows.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Windows.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_name'] = mac['dnsName']
                break

        return data
