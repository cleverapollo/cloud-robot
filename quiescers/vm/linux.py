# python
# lib
import paramiko
# local
import utils
from ro import get_full_response


class Linux:
    """
    Quiescer class for Linux VMs
    Quiesce: Shuts down the VM in host server
    """
    logger = utils.get_logger_for_name('quiescers.vm.linux')

    @staticmethod
    def quiesce(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Linux VM to be quiesced in the specified KVM host and return a
        flag indicating whether or not the quiesce was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to quiesce the VM
        :return: A flag stating whether or not the quiesce was successful
        """
        quiesced = False
        # Attempt to connect to the host server
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            Linux.logger.info(f'Attempting to connect to host server @ {vm["host_ip"]}')
            client.connect(hostname=vm['host_ip'], username='administrator', password=password)
            # Generate and execute the command to quiesce the actual VM
            Linux.logger.info(f'Attempting to quiesce the VM #{vm["idVM"]}')
            cmd = utils.jinja_env.get_template('linux_vm_quiesce_cmd.j2').render(
                vm_identifier=vm['vm_identifier'],
            )
            Linux.logger.debug(f'Generated VM quiesce command for VM #{vm["idVM"]}\n{cmd}')

            # Run the command and log the output and err.
            _, stdout, stderr = client.exec_command(cmd)
            output = get_full_response(stdout.channel)
            if output:
                Linux.logger.info(f'VM quiesce command for VM #{vm["idVM"]} generated stdout.\n{output}')
                quiesced = True
            err = get_full_response(stderr.channel)
            if err:
                Linux.logger.warning(f'VM quiesce command for VM #{vm["idVM"]} generated stderr.\n{err}')
        except paramiko.SSHException:
            Linux.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the quiesce of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        client.close()
        return quiesced
