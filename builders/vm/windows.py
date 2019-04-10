# libs
import winrm
# local
import settings
import utils

ROBOT_DRIVE_PATH = settings.ROBOT_HYV_DRIVE_PATH
FREENAS_URL = settings.FREENAS_URL
TEMPLATE_MAP = settings.OS_TEMPLATE_MAP['Windows']


class Windows:
    """
    Builder class for building Windows VMs
    """

    logger = utils.get_logger_for_name('builders.vm.windows')

    @staticmethod
    def build(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Windows VM to be built in the specified HyperV host and
        return a flag indicating whether or not the build was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to build the VM
        :return: A flag stating whether or not the build was successful
        """
        built = False
        # Determine the template to use to build the VM
        os_name = TEMPLATE_MAP.get(vm['idImage'], None)
        if os_name is None:
            valid_ids = [str(k) for k in TEMPLATE_MAP.keys()]
            Windows.logger.error(
                f'Invalid image id for VM #{vm["idVM"]}. VM has HyperV hypervisor but {vm["idImage"]} is not a valid '
                f'Windows image id. Valid Windows image ids are {", ".join(valid_ids)}.',
            )
            return False
        unattend = utils.jinja_env.get_template(f'{os_name}_unattend.j2').render(**vm)
        try:
            with open(f'{ROBOT_DRIVE_PATH}/unattend_xmls/{vm["vm_identifier"]}.xml', 'w') as f:
                f.write(unattend)
            Windows.logger.debug(f'Generated unattend file for VM #{vm["idVM"]}\n{unattend}')
        except IOError:
            Windows.logger.error(f'Failed to write unattend file for VM #{vm["idVM"]}', exc_info=True)
            return False

        # Attempt to connect to the host to begin building the VM
        Windows.logger.info(f'Attempting to connect to host @ {vm["host_name"]} to build VM #{vm["idVM"]}')
        try:
            # Generate the command that actually builds the VM
            cmd = utils.jinja_env.get_template('windows_vm_build_cmd.j2').render(freenas_url=FREENAS_URL, **vm)
            Windows.logger.debug(f'Generated build command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to build VM #{vm["idVM"]}')
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
                Windows.logger.info(f'VM build command for VM #{vm["idVM"]} generated stdout\n{msg}')
                built = 'VM Successfully Created' in msg
            if std_err:
                msg = std_err.strip().decode()
                Windows.logger.warning(f'VM build command for VM #{vm["idVM"]} generated stderr\n{msg}')
            session.protocol.cleanup_command(shell_id=shell_id, command_id=command_id)
            session.protocol.close_shell(shell_id=shell_id)
        except winrm.exceptions.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the build of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return built
