# libs
import winrm
# local
import utils
from ro import fix_run_ps


class Windows:
    """
    Restarter class for restarting Windows VMs
    Restarter: Restarts the VM
    """
    logger = utils.get_logger_for_name('restarters.windows')

    @staticmethod
    def restart(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Windows VM to be restarted in the specified HyperV host and
        return a flag indicating whether or not the restart was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to restart the VM
        :return: A flag stating whether or not the restart was successful
        """
        restarted = False
        # Attempt to connect to the host to begin restarting the VM
        Windows.logger.info(f'Attempting to connect to host @ {vm["host_name"]} to restart VM #{vm["idVM"]}')
        try:
            # Generate the command that restart the VM
            cmd = utils.jinja_env.get_template('windows_vm_restart_cmd.j2').render(
                **vm,
            )
            Windows.logger.debug(f'Generated restart command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to restart VM #{vm["idVM"]}')
            # Connecting HyperV host with session
            session = winrm.Session(vm['host_name'], auth=('administrator', password))
            response = fix_run_ps(self=session, script=cmd)
            if response.status_code == 0:
                msg = response.std_out.strip()
                Windows.logger.info(f'VM restart command for VM #{vm["idVM"]} generated stdout\n{msg}')
                restarted = f'VM={vm["vm_identifier"]} Successfully Rebooted.' in msg.decode()
            else:
                msg = response.std_err.strip()
                Windows.logger.warning(f'VM restart command for VM #{vm["idVM"]} generated stderr\n{msg}')
        except winrm.exceptions.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the restart of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return restarted
