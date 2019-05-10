"""
quiescer class for windows vms

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
from winrm.exceptions import WinRMError
# local
import utils
from mixins import WindowsMixin


__all__ = [
    'Windows',
]


class Windows(WindowsMixin):
    """
    Class that handles the quiescing of the specified VM
    When we get to this point, we can be sure that the VM is a windows VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.quiescers.vm.windows')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before quiescing
    template_keys = {
        # the DNS hostname for the host machine, as WinRM cannot use IPv6
        'host_name',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def quiesce(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the quiesce of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param span: The tracing span in use for this quiesce task
        :return: A flag stating whether or not the quiesce was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        child_span = tracer.start_span('generate_template_data', child_of=span)
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
                f'Template Data Error, the following keys were missing from the VM quiesce data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence quiescing the VM
        host_name = template_data.pop('host_name')

        # Render the quiesce command
        child_span = tracer.start_span('generate_command', child_of=span)
        cmd = utils.JINJA_ENV.get_template('vm/windows/quiesce_cmd.j2').render(**template_data)
        child_span.finish()

        # Open a client and run the two necessary commands on the host
        quiesced = False
        try:
            child_span = tracer.start_span('quiesce_vm', child_of=span)
            response = Windows.deploy(cmd, host_name, child_span)
            span.set_tag('host', host_name)
            child_span.finish()
        except WinRMError:
            Windows.logger.error(
                f'Exception occurred while attempting to quiesce VM #{vm_id} on {host_name}',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'winrm_error')
        else:
            # Check the stdout and stderr for messages
            if response.std_out:
                msg = response.std_out.strip()
                Windows.logger.debug(f'VM quiesce command for VM #{vm_id} generated stdout\n{msg}')
                quiesced = f'{template_data["vm_identifier"]} Successfully Quiesced.' in msg
            # Check if the error was parsed to ensure we're not logging invalid std_err output
            if response.std_err and '#< CLIXML\r\n' not in response.std_err:
                msg = response.std_err.strip()
                Windows.logger.warning(f'VM quiesce command for VM #{vm_id} generated stderr\n{msg}')
        finally:
            return quiesced

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :param span: The tracing span in use for this task. In this method, just pass it to API calls
        :returns: The data needed for the templates to build a Windows VM
        """
        vm_id = vm_data['idVM']
        Windows.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Windows.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer'], span=span):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_name'] = mac['dnsName']
                break

        return data
