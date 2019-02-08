# libs
import winrm
# local
import settings
import utils

DRIVE_PATH = '/mnt/images/HyperV'
FREENAS_URL = f'\\\\{settings.REGION_NAME}-freenas.cloudcix.com\\mnt\\volume\\{settings.REGION_NAME}'


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
        :param password: The password used to log in to the host to build the VM
        :return: A flag stating whether or not the quiesce was successful
        """
        quiesced = False
        # Attempt to connect to the host to begin quiescing the VM
        Windows.logger.info(f'Attempting to connect to host @ {vm["host_name"]} to quiesce VM #{vm["idVM"]}')
        try:
            # Generate the command that quiesces the VM
            cmd = utils.jinja_env.get_template('windows_vm_quiesce_cmd.j2').render(
                freenas_url=FREENAS_URL,
                **vm,
            )
            Windows.logger.debug(f'Generated quiesce command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to quiesce VM #{vm["idVM"]}')
            # Connecting HyperV host with session
            session = winrm.Session(vm['host_name'], auth=('administrator', password))
            shell_id = session.protocol.open_shell()
            command_id = session.protocol.run_command(shell_id=shell_id, command=cmd)
            std_out, std_err, status_code = session.protocol.get_command_output(
                shell_id=shell_id,
                command_id=command_id,
            )
            if std_out:
                msg = std_out.strip()
                Windows.logger.info(f'VM quiesce command for VM #{vm["idVM"]} generated stdout\n{msg}')
                quiesced = f'{vm["vm_identifier"]} Off' in msg.decode()
            if std_err:
                msg = std_err.strip()
                Windows.logger.warning(f'VM quiesce command for VM #{vm["idVM"]} generated stderr\n{msg}')
            session.protocol.cleanup_command(shell_id=shell_id, command_id=command_id)
            session.protocol.close_shell(shell_id=shell_id)
        except winrm.exceptions.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the quiesce of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return quiesced
