# python
import os
# lib
import paramiko
# local
import utils
import settings
from ro import get_full_response


DRIVE_PATH = settings.KVM_DRIVE_PATH


class Linux:
    """
    Scrubber class for Linux VMs
    Scrubber: Deletes the VM completely from host server
    """
    logger = utils.get_logger_for_name('scrubbers.vm.linux')

    @staticmethod
    def scrub(vm: dict, password: str) -> bool:
        """
        Given data from the VM dispatcher, request for a Linux VM to be scrubbed in the specified KVM host and return a
        flag indicating whether or not the scrub was successful.
        :param vm: The data about the VM from the dispatcher
        :param password: The password used to log in to the host to scrub the VM
        :return: A flag stating whether or not the scrub was successful
        """
        scrubbed = False
        # Attempt to connect to the host server
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            Linux.logger.info(f'Attempting to connect to host server @ {vm["host_ip"]}')
            client.connect(hostname=vm['host_ip'], username='administrator', password=password)
            # Generate and execute the command to scrub the VM
            Linux.logger.info(f'Attempting to scrub VM #{vm["idVM"]}')
            cmd = utils.jinja_env.get_template('linux_vm_scrub_cmd.j2').render(
                drive_path=DRIVE_PATH,
                SUDO_PASS=password,
                **vm,
            )
            Linux.logger.debug(f'Generated VM scrub command for VM #{vm["idVM"]}\n{cmd}')

            # Run the command and log the output and err.
            _, stdout, stderr = client.exec_command(cmd)
            output = get_full_response(stdout.channel)
            if output:
                Linux.logger.info(f'VM scrub command for VM #{vm["idVM"]} generated stdout.\n{output}')
                scrubbed = True
            err = get_full_response(stderr.channel)
            if err:
                Linux.logger.warning(f'VM scrub command for VM #{vm["idVM"]} generated stderr.\n{err}')

            if scrubbed:
                try:
                    if os.path.exists(f'{DRIVE_PATH}/kickstarts/{vm["vm_identifier"]}.cfg'):
                        os.remove(f'{DRIVE_PATH}/kickstarts/{vm["vm_identifier"]}.cfg')
                    Linux.logger.debug(f'Deleted {vm["vm_identifier"]}.cfg file for FreeNas drive')
                except IOError:
                    Linux.logger.error(f'Failed to delete kickstart conf of VM #{vm["idVM"]}', exc_info=True)

            if vm['bridge_delete'] is True:
                # Generate and execute the command to delete the bridge
                bridge_delete_cmd = utils.jinja_env.get_template('kvm_bridge_scrub_cmd.j2').render(vlan=vm['vlan'])
                Linux.logger.debug(f'Generated bridge delete command for vlan #br{vm["vlan"]}\n{bridge_delete_cmd}')

                # Run the command and log the output and err.
                _, stdout, stderr = client.exec_command(bridge_delete_cmd)
                output = get_full_response(stdout.channel)
                if output:
                    Linux.logger.info(f'Bridge delete command for vlan #br{vm["vlan"]} generated stdout.\n{output}')
                err = get_full_response(stderr.channel)
                if err:
                    Linux.logger.warning(f'Bridge delete command for vlan #br{vm["vlan"]} generated stderr.\n{err}')
                # Delete the bridge xml file
                try:
                    if os.path.exists(f'{DRIVE_PATH}/bridge_xmls/br{vm["vlan"]}.xml'):
                        os.remove(f'{DRIVE_PATH}/bridge_xmls/br{vm["vlan"]}.xml')
                    Linux.logger.debug(f'Removed br{vm["vlan"]}.xml file for FreeNas drive')
                except IOError:
                    Linux.logger.error(
                        f'Failed to delete bridge file br{vm["vlan"]}.xml of VM #{vm["idVM"]}',
                        exc_info=True,
                    )
        except paramiko.SSHException:
            Linux.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the remove of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        client.close()
        return scrubbed
