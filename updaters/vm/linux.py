# lib
import paramiko
# local
import utils
from ro import get_full_response


DRIVE_PATH = '/mnt/images/KVM'


class Linux:
    """
    Updater class for updating Linux VMs
    """

    logger = utils.get_logger_for_name('updaters.vm.linux')

    @staticmethod
    def update(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Linux VM to be updated in the specified KVM host and return a
        flag indicating whether or not the update was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to update the VM
        :return: A flag stating whether or not the update was successful
        """
        updated = False
        # Attempt to connect to the host server
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            Linux.logger.info(f'Attempting to connect to host server @ {vm["host_ip"]}')
            client.connect(hostname=vm['host_ip'], username='administrator', password=password)
            # Generate and execute the command to update the actual VM
            Linux.logger.info(f'Attempting to update VM #{vm["idVM"]}')
            cmd = utils.jinja_env.get_template('linux_vm_update_cmd.j2').render(
                drive_path=DRIVE_PATH,
                SUDO_PASS=password,
                **vm,
            )
            Linux.logger.debug(f'Generated VM update command for VM #{vm["idVM"]}\n{cmd}')

            # Run the command and log the output and err.
            _, stdout, stderr = client.exec_command(cmd)
            output = get_full_response(stdout.channel)
            if output:
                Linux.logger.info(f'VM update command for VM #{vm["idVM"]} generated stdout.\n{output}')
                updated = True
            err = get_full_response(stderr.channel)
            if err:
                Linux.logger.warning(f'VM update command for VM #{vm["idVM"]} generated stderr.\n{err}')

        except paramiko.SSHException:
            Linux.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the update of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        client.close()
        return updated
