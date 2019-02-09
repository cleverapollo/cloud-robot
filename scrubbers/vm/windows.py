# libs
import os
import winrm
# local
import settings
import utils

DRIVE_PATH = '/mnt/images/HyperV'
FREENAS_URL = f'\\\\{settings.REGION_NAME}-freenas.cloudcix.com\\mnt\\volume\\{settings.REGION_NAME}'


class Windows:
    """
    Scrubber class for Scrubbing Windows VMs
    """
    logger = utils.get_logger_for_name('scrubbers.vm.windows')

    @staticmethod
    def scrub(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Windows VM to be deleted in the specified HyperV host and
        return a flag indicating whether or not the scrub was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to build the VM
        :return: A flag stating whether or not the scrub was successful
        """
        scrubbed = False
        try:
            if os.path.exists(f'{DRIVE_PATH}/unattend_xmls/{vm["vm_identifier"]}.xml'):
                os.remove(f'{DRIVE_PATH}/unattend_xmls/{vm["vm_identifier"]}.xml')
            Windows.logger.debug(f'Deleted {vm["vm_identifier"]}.xml file from FreeNas drive')
        except IOError:
            Windows.logger.error(f'Failed to delete unattend file of VM #{vm["idVM"]}', exc_info=True)

        # Attempt to connect to the host to begin removing the VM
        Windows.logger.info(f'Attempting to connect to host @ {vm["host_name"]} to scrub VM #{vm["idVM"]}')
        try:
            # Generate the command that actually scrubs the VM
            cmd = utils.jinja_env.get_template('windows_vm_scrub_cmd.j2').render(freenas_url=FREENAS_URL, **vm)
            Windows.logger.debug(f'Generated scrub command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to scrub VM #{vm["idVM"]}')
            # Connecting HyperV host with session
            session = winrm.Session(vm['host_name'], auth=('administrator', password))
            shell_id = session.protocol.open_shell()
            command_id = session.protocol.run_command(shell_id=shell_id, command=cmd)
            std_out, std_err, status_code = session.protocol.get_command_output(
                shell_id=shell_id,
                command_id=command_id,
            )
            if std_out:
                msg = std_out.strip().decode()
                Windows.logger.info(f'VM scrub command for VM #{vm["idVM"]} generated stdout\n{msg}')
                scrubbed = 'VM Successfully Deleted.' in msg.decode()
            if std_err:
                msg = std_err.strip().decode()
                Windows.logger.warning(f'VM scrub command for VM #{vm["idVM"]} generated stderr\n{msg}')

            session.protocol.cleanup_command(shell_id=shell_id, command_id=command_id)
            session.protocol.close_shell(shell_id=shell_id)
        except winrm.exceptions.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the scrub of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return scrubbed
