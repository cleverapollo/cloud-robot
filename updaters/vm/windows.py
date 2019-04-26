# libs
import winrm
# local
import utils
from ro import fix_run_ps


class Windows:
    """
    Updater class for Updating Windows VMs
    """

    logger = utils.get_logger_for_name('updaters.vm.windows')

    @staticmethod
    def update(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Windows VM to be updated in the specified HyperV host and
        return a flag indicating whether or not the update was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to update the VM
        :return: A flag stating whether or not the update was successful
        """
        updated = False
        # Attempt to connect to the host to begin Updating the VM
        Windows.logger.info(f'Attempting to connect to host @ {vm["host_name"]} to update VM #{vm["idVM"]}')
        try:
            # Generate the command that actually updates the VM
            cmd = utils.jinja_env.get_template('windows_vm_update_cmd.j2').render(**vm)
            Windows.logger.debug(f'Generated update command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to update VM #{vm["idVM"]}')
            # Connecting HyperV host with session
            session = winrm.Session(vm['host_name'], auth=('administrator', password))
            response = fix_run_ps(self=session, script=cmd)
            if response.status_code == 0:
                msg = response.std_out.strip().decode()
                Windows.logger.info(f'VM update command for VM #{vm["idVM"]} generated stdout\n{msg}')
                updated = 'VM Successfully Shutdown, Updated and Rebooted.' in msg
            else:
                msg = response.std_err.strip().decode()
                Windows.logger.warning(f'VM update command for VM #{vm["idVM"]} generated stderr\n{msg}')
        except winrm.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the update of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return updated
