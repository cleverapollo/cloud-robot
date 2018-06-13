# python
import paramiko
import winrm
from crypt import crypt, mksalt, METHOD_SHA512
# lib
from pathlib import Path
# local
import utils

driver_logger = utils.get_logger_for_name('vm_builder.vm_build')


def vm_build(vm: dict, password: str) -> bool:
    """
    Builds a VM with the given information
    :param vm: Data to use for building the VM
    :param password: Password for the VM
    :return: vm_built: Flag stating whether or not the build succeeded
    """
    vm_built = False

    # HyperV hosted
    if vm['hypervisor'] == 1:
        # FREENAS mounted location in the host /mnt/images
        vm['freenas_url'] = 'alpha-freenas.cloudcix.com\\mnt\\volume\\alpha'
        drive_path = '/mnt/images/HyperV/'
        template = vm['image'].replace(r'\ ', '_')
        xml = utils.jinja_env.get_template(
            f'{ template }.j2'
        ).render(**vm)
        try:
            with open(
                    f'{drive_path}unattend_xmls/{vm["vm_identifier"]}.xml',
                    'w'
            ) as file:
                file.write(xml)
            driver_logger.debug(
                f'Generated xml file for vm #{vm["vm_identifier"]}\n{xml}'
            )
        except Exception:
            driver_logger.error(
                f'Failed to write unattend to file for '
                f'VM {vm["vm_identifier"]}', exc_info=True
            )
            return vm_built
        try:
            session = winrm.Session(
                vm['host_name'], auth=('administrator', str(password))
            )
            cmd = utils.jinja_env.get_template(
                'win_cmd.j2'
            ).render(**vm)
            run = session.run_cmd(cmd)
            if run.std_out:
                for line in run.std_out:
                    driver_logger.info(line)
                vm_built = True
            elif run.std_err:
                driver_logger.error(run.std_err)
        except Exception:
            driver_logger.error(
                f'Exception thrown when attempting to connect to '
                f'{vm["host_name"]} for WinRM',
                exc_info=True
            )
        return vm_built

    # KVM hosted
    elif vm['hypervisor'] == 2:
        vm['drive_path'] = '/mnt/images/KVM/'
        # encrypting root and user password
        vm['crypted_root_pw'] = str(
            crypt(vm['root_password'], mksalt(METHOD_SHA512)))
        vm['crypted_user_pw'] = str(
            crypt(vm['user_password'], mksalt(METHOD_SHA512)))
        # kickstart file creation
        template = vm['image'].split(r'\ ')[0]
        ks_text = utils.jinja_env.get_template(
            f'{ template }.j2'
        ).render(**vm)
        ks_file = f'{vm["name"]}.cfg'
        try:
            with open(f'{drive_path}kickstarts/{ks_file}', 'w') as ks:
                ks.write(ks_text)
            driver_logger.debug(
                f'Generated KS file for vm #{vm["vm_identifier"]}\n{ks_text}'
            )
        except Exception:
            driver_logger.error(
                f'Failed to write kickstart to file for VM {vm["idVM"]}',
                exc_info=True
            )
            return vm_built
        # bridge network xml file creation
        bridge_file = Path(f'{drive_path}bridge_xmls/br{ vm["vlan"] }.xml')
        if not bridge_file.is_file():
            xml_text = utils.jinja_env.get_template(
                'kvm_bridge_network.j2'
            ).render(**vm['vlan'])
            with open(f'{drive_path}bridge_xmls/br{ vm["vlan"] }', 'w') as xt:
                xt.write(xml_text)
        # make the cmd
        cmd = utils.jinja_env.get_template(
                'linux_cmd.j2'
            ).render(**vm)
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=vm['host_ip'],
                username='administrator',
                password=password
            )
            stdin, stdout, stderr = client.exec_command(cmd)
            if stdout:
                for line in stdout:
                    driver_logger.info(line)
                vm_built = True
            elif stderr:
                driver_logger.error(stderr)
        except Exception:
            driver_logger.error(
                f'Exception occurred during SSHing into host {vm["host_ip"]} '
                f'for the build of VM #{vm["idVM"]}',
                exc_info=True
            )
        finally:
            client.close()
        return vm_built
