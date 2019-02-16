# python
# lib
import paramiko
# local
import utils
from ro import get_full_response


class Linux:
    """
    Restarter class for Linux VMs
    Restart:  Restarts the VM in host server
    """
    logger = utils.get_logger_for_name('restarters.linux')

    @staticmethod
    def restart(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Linux VM to be restart in the specified KVM host and return a
        flag indicating whether or not the restart was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to restart the VM
        :return: A flag stating whether or not the restart was successful
        """
        restarted = False
        # Attempt to connect to the host server
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            Linux.logger.info(f'Attempting to connect to host server @ {vm["host_ip"]}')
            client.connect(hostname=vm['host_ip'], username='administrator', password=password)
            # Generate and execute the command to restart the actual VM
            Linux.logger.info(f'Attempting to restart the VM #{vm["idVM"]}')
            cmd = f'virsh start {vm["vm_identifier"]}'
            Linux.logger.debug(f'Generated VM restart command for VM #{vm["idVM"]}\n{cmd}')

            # Run the command and log the output and err.
            _, stdout, stderr = client.exec_command(cmd)
            output = get_full_response(stdout.channel)
            if output:
                Linux.logger.info(f'VM restart command for VM #{vm["idVM"]} generated stdout.\n{output}')
                restarted = True
            err = get_full_response(stderr.channel)
            if err:
                Linux.logger.warning(f'VM restart command for VM #{vm["idVM"]} generated stderr.\n{err}')
        except paramiko.SSHException:
            Linux.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the restart of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        client.close()
        return restarted
