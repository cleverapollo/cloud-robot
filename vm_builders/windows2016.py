# python
import winrm
import xmltodict
from collections import OrderedDict

# local
import utils

driver_logger = utils.get_logger_for_name('windows2016.vm_build')
# FREENAS mounted location in the host /mnt/images
freenas_path = 'alpha-freenas.cloudcix.com\\mnt\\volume\\alpha'
path = '/mnt/images/UnattendXMLfiles/'
os_name = 'WindowsServer2016x64'
xmlns_wcm = 'http://schemas.microsoft.com/WMIConfig/2002/State'
xmlns_xsi = 'http://www.w3.org/2001/XMLSchema-instance'


def vm_build(vm: dict, password: str) -> bool:
    """
    Prepares an answerfile in freenas, and creates a VM in HyperV using WinRM
    :param vm: Data about the VM to be built
    :param password: Password for the host
    :return: Flag stating whether or not the build was successful
    """
    vm_built = False
    xml = utils.jinja_env.get_template('windows2016_unattend.j2').render(**vm)
    try:
        with open(f'{path}{vm["vm_identifer"]}.xml', 'w') as file:
            file.write(xml)
    except Exception:
        driver_logger.exception(
            f'Failed to write answerfile to file for VM {vm["vm_identifier"]}'
        )
        return vm_built
    try:
        session = winrm.Session(
            vm['host_name'],
            auth=('administrator', str(password))
        )

        cmd = (
            f'mount \\\\{freenas_path} Z: -o nolock & powershell -file '
            f'Z:\scripts\VMCreator.ps1 -VMName {vm["vm_identifier"]} -Gen 1 '
            f'-OSName {os_name} -ProcessorCount {vm["cpu"]} -Dynamic 1 -Ram '
            f'{vm["ram"]} -Hdd {vm["hdd"]} -Flash {vm["flash"]} -VlanId '
            f'{vm["vlan"]} -Verbose'
        )

        run = session.run_cmd(cmd)
        if run.std_out:
            for line in run.std_out:
                driver_logger.info(line)
            vm_built = True
        elif run.std_err:
            driver_logger.error(run.std_err)
    except Exception:
        driver_logger.exception(
            f'Exception thrown when attempting to connect to '
            f'{vm["host_name"]} for WinRM'
        )
    return vm_built
