# libs
import os
import winrm
# local
import utils
from ro import fix_run_ps

DRIVE_PATH = '/mnt/images/HyperV'


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
        :param password: The password used to log in to the host to scrub the VM
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
            cmd = utils.jinja_env.get_template('windows_vm_scrub_cmd.j2').render(**vm)
            Windows.logger.debug(f'Generated scrub command for VM #{vm["idVM"]}\n{cmd}')
            Windows.logger.info(f'Attempting to execute the command to scrub VM #{vm["idVM"]}')
            # Connecting HyperV host with session
            session = winrm.Session(vm['host_name'], auth=('administrator', password))
            response = fix_run_ps(self=session, script=cmd)
            if response.status_code == 0:
                msg = response.std_out.strip()
                Windows.logger.info(f'VM scrub command for VM #{vm["idVM"]} generated stdout\n{msg}')
                scrubbed = 'VM Successfully Deleted.' in msg.decode()
            else:
                msg = response.std_err.strip()
                Windows.logger.warning(f'VM scrub command for VM #{vm["idVM"]} generated stderr\n{msg}')
        except winrm.exceptions.WinRMError:
            Windows.logger.error(
                f'Exception occurred while connected to host server @ {vm["host_ip"]} for the scrub of VM '
                f'#{vm["idVM"]}',
                exc_info=True,
            )
        return scrubbed
