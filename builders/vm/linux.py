# python
import time
# lib
import paramiko
# local
import settings
import utils
from ro import get_full_response


SERVER_DRIVE_PATH = settings.SERVER_KVM_DRIVE_PATH
ROBOT_DRIVE_PATH = settings.ROBOT_KVM_DRIVE_PATH
TEMPLATE_MAP = settings.OS_TEMPLATE_MAP['Linux']


class Linux:
    """
    Builder class for building Linux VMs
    """

    logger = utils.get_logger_for_name('builders.vm.linux')

    @staticmethod
    def build(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Linux VM to be built in the specified KVM host and return a
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
            Linux.logger.error(
                f'Invalid image id for VM #{vm["idVM"]}. VM has KVM hypervisor but {vm["idImage"]} is not a valid '
                f'Linux image id. Valid Linux image ids are {", ".join(valid_ids)}.',
            )
            return False
        try:
            kickstart = utils.jinja_env.get_template(f'{os_name}_kickstart.j2').render(**vm)
            with open(f'{ROBOT_DRIVE_PATH}/kickstarts/{vm["vm_identifier"]}.cfg', 'w') as f:
                f.write(kickstart)
            Linux.logger.debug(f'Generated Kickstart file for vm #{vm["idVM"]}\n{kickstart}')
        except IOError:
            Linux.logger.error(f'Failed to write kickstart conf to file for VM #{vm["idVM"]}', exc_info=True)
            return False

        # Create the XML to build the bridge network
        with open(f'{ROBOT_DRIVE_PATH}/bridge_xmls/br{vm["vlan"]}.xml', 'w') as f:
            f.write(utils.jinja_env.get_template('kvm_bridge_network.j2').render(**vm))

        # Attempt to connect to the host server
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            Linux.logger.info(f'Attempting to connect to host server @ {vm["host_ip"]}')
            client.connect(hostname=vm['host_ip'], username='administrator', password=password)

            # Generate and execute the command to build the bridge interface
            Linux.logger.info(f'Attempting to build bridge network for VM #{vm["idVM"]}')
            cmd = utils.jinja_env.get_template('kvm_bridge_build_cmd.j2').render(
                drive_path=SERVER_DRIVE_PATH,
                SUDO_PASS=password,
                **vm,
            )
            Linux.logger.debug(f'Generated command to build bridge network for VM #{vm["idVM"]}\n{cmd}')

            # Run the command and log the output and err. For the bridge build we don't care if there's an error
            _, stdout, stderr = client.exec_command(cmd)
            # Block until command finishes
            stdout.channel.recv_exit_status()
            output = get_full_response(stdout.channel)
            if output:
                Linux.logger.info(f'Bridge build command for VM #{vm["idVM"]} generated stdout.\n{output}')
            err = get_full_response(stderr.channel)
            if err:
                Linux.logger.warning(f'Bridge build command for VM #{vm["idVM"]} generated stderr.\n{err}')

            # Generate and execute the command to build the actual VM
            Linux.logger.info(f'Attempting to build VM #{vm["idVM"]}')
            cmd = utils.jinja_env.get_template('linux_vm_build_cmd.j2').render(
                drive_path=SERVER_DRIVE_PATH,
                SUDO_PASS=password,
                **vm,
            )
            Linux.logger.debug(f'Generated VM Build command for VM #{vm["idVM"]}\n{cmd}')

            # Run the command and log the output and err. Check if the string "Restarting guest" is in the output
            _, stdout, stderr = client.exec_command(cmd)
            # Block until command finishes
            stdout.channel.recv_exit_status()
            output = get_full_response(stdout.channel)
            if output:
                Linux.logger.info(f'VM build command for VM #{vm["idVM"]} generated stdout.\n{output}')
            err = get_full_response(stderr.channel)
            if err:
                Linux.logger.warning(f'VM build command for VM #{vm["idVM"]} generated stderr.\n{err}')
            built = 'Creating domain' in output
            if built:
                time.sleep(30)

        except paramiko.SSHException:
            Linux.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the build of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        client.close()
        return built
