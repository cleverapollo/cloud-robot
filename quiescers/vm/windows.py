# libs
import winrm
# local
import utils
from ro import fix_run_ps


class Windows:
    """
    Quiescer class for quiescing Windows VMs
    Quiesce: Shutdowns the VM
    """
    logger = utils.get_logger_for_name('quiescers.vm.windows')

    @staticmethod
    def quiesce(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Windows VM to be shutdown in the specified HyperV host and
        return a flag indicating whether or not the quiesce was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to quiesce the VM
        :return: A flag stating whether or not the quiesce was successful
        """
        quiesced = False
        # Attempt to connect to the host to begin quiescing the VM
        Windows.logger.info(f'Attempting to connect to host @ {vm["host_name"]} to quiesce VM #{vm["idVM"]}')
        try:
            # Generate the command that quiesces the VM
            cmd = utils.jinja_env.get_template('windows_vm_quiesce_cmd.j2').render(**vm)
            Windows.logger.debug(f'Generated quiesce command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to quiesce VM #{vm["idVM"]}')
            # Connecting HyperV host with session
            session = winrm.Session(vm['host_name'], auth=('administrator', password))
            response = fix_run_ps(session, cmd)
            if response.status_code == 0:
                msg = response.std_out.strip().decode()
                Windows.logger.info(f'VM quiesce command for VM #{vm["idVM"]} generated stdout\n{msg}')
                scrubbed = f'{vm["vm_identifier"]} Successfully Quiesced.' in msg
            else:
                msg = response.std_err.strip().decode()
                Windows.logger.warning(f'VM quiesce command for VM #{vm["idVM"]} generated stderr\n{msg}')
        except winrm.exceptions.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the quiesce of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return quiesced
