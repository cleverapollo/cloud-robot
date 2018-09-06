# libs
import winrm
# local
import utils


DRIVE_PATH = '/mnt/images/HyperV'
FREENAS_URL = r'\\alpha-freenas.cloudcix.com\mnt\volume\alpha'
TEMPLATE_MAP = {
    3: 'windows2016',
}


class Windows:
    """
    Builder class for building Windows VMs
    """

    logger = utils.get_logger_for_name('builders.vm.linux')

    @staticmethod
    def build(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Windows VM to be built in the specified KVM host and return a
        flag indicating whether or not the build was successful.
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
            with open(f'{DRIVE_PATH}/unattend_xmls/{vm["vm_identifier"]}.xml', 'w') as f:
                f.write(unattend)
            Windows.logger.debug(f'Generated unattend file for VM #{vm["idVM"]}\n{unattend}')
        except IOError:
            Windows.logger.error(f'Failed to write unattend file for VM #{vm["idVM"]}', exc_info=True)
            return False

        # Attempt to connect to the host to begin building the VM
        Windows.logger.info(f'Attempting to connect to host @ {vm["host_name"]} to build VM #{vm["idVM"]}')
        try:
            session = winrm.Session(vm['host_name'], auth=('administrator', password))
            # Generate the command that actually builds the VM
            cmd = utils.jinja_env.get_template('windows_vm_build_cmd.j2').render(freenas_url=FREENAS_URL, **vm)
            Windows.logger.debug(f'Generated build command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to build VM #{vm["idVM"]}')
            run = session.run_cmd(cmd)
            if run.std_out:
                msg = run.std_out.strip()
                Windows.logger.info(f'VM build command for VM #{vm["idVM"]} generated stdout\n{msg}')
                built = b'VM Successfully Created and Hosted.' in msg
            if run.std_err:
                msg = run.std_err.strip()
                Windows.logger.warning(f'VM build command for VM #{vm["idVM"]} generated stderr\n{msg}')
        except TypeError:
            pass
        except winrm.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the build of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return built
