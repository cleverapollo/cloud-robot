# python
import logging
import time
from crypt import crypt, mksalt, METHOD_SHA512
from pathlib import Path
# lib
import paramiko
import winrm
# local
import utils

driver_logger = utils.get_logger_for_name(
    'vm_builder.vm_build',
    logging.DEBUG,
)


def vm_build(vm: dict, password: str) -> bool:
    """
    Builds a VM with the given information
    :param vm: Data to use for building the VM
    :param password: Password for the VM
    :return: vm_built: Flag stating whether or not the build succeeded
    """
    if vm['hypervisor'] == 1:  # HyperV hosted
        vm['dns'] = str(vm['dns']).split(',')
        vm['tz'] = 'GMT Standard Time'
        return _build_windows_vm(vm, password)
    elif vm['hypervisor'] == 2:  # KVM hosted
        # encrypting root and user password
        vm['crypted_root_password'] = str(crypt(
            vm['root_password'],
            mksalt(METHOD_SHA512),
        ))
        vm['crypted_user_password'] = str(crypt(
            vm['user_password'],
            mksalt(METHOD_SHA512),
        ))

        return _build_linux_vm(vm, password)
    else:
        driver_logger.error(
            f'Unsupported  idHypervisor={vm["hypervisor"]} value of VM '
            f'{vm["vm_identifier"]} cannot be built',
        )
        return False


def _build_windows_vm(vm: dict, password: str) -> bool:
    """
    builds a windows based vm in the hyperv host
    :param vm: dict
    :param password: str
    :return: vm_built: bool
    """
    # FREENAS mounted location in the host /mnt/images and drive path
    freenas_url = '\\\\alpha-freenas.cloudcix.com\\mnt\\volume\\alpha'
    drive_path = '/mnt/images/HyperV/'

    vm_built = False
    if vm['id_image'] == 3:
        xml = utils.jinja_env.get_template(
            'windows2016_unattend.j2',
        ).render(**vm)
    else:
        driver_logger.error(
            f'Invalid id_image for VM '
            f'#{vm["vm_identifier"]}. VM is set to KVM hypervisor but '
            'does not have a valid Windows image id; expected in [3], '
            f'received {vm["id_image"]}',
        )
        return vm_built

    try:
        file_name = f'{drive_path}unattend_xmls/{vm["vm_identifier"]}.xml'
        with open(file_name, 'w') as file:
            file.write(xml)
        driver_logger.debug(
            f'Generated xml file for vm #{vm["vm_identifier"]}\n{xml}',
        )
    except Exception:
        driver_logger.error(
            f'Failed to write unattend to file for VM {vm["vm_identifier"]}',
            exc_info=True,
        )
        return vm_built

    try:
        session = winrm.Session(
            vm['host_name'],
            auth=('administrator', str(password)),
        )
        cmd = utils.jinja_env.get_template(
            'windows_vm_build_cmd.j2',
        ).render(freenas_url=freenas_url, **vm)
        driver_logger.debug(
            f'Windows VM Build Command for VM  #{vm["vm_identifier"]}'
            f'generated:\n{cmd}',
        )
        driver_logger.info(
            f'Executing command to build VM  #{vm["vm_identifier"]}',
        )
        run = session.run_cmd(cmd)
        if run.std_out:
            msg = run.std_out.strip()
            driver_logger.info(
                f'Build of VM  #{vm["vm_identifier"]} generated stdout: '
                f'{msg}',
            )
            vm_built = True
        elif run.std_err:
            run.std_err.strip()
            driver_logger.info(
                f'Build of VM  #{vm["vm_identifier"]} generated stderr: '
                f'{msg}',
            )
            driver_logger.error(run.std_err)
    except Exception:
        driver_logger.error(
            f'Exception thrown when attempting to connect to '
            f'{vm["host_name"]} for WinRM',
            exc_info=True,
        )
    return vm_built


def _build_linux_vm(vm: dict, password: str) -> bool:
    """
    builds a linux based vm in the kvm host
    :param vm: dict
    :param password: str
    :return: vm_built: bool
    """
    vm_built = False
    drive_path = '/mnt/images/KVM/'

    # kickstart file creation
    if vm['id_image'] in [6, 7, 8, 9]:
        ks_text = utils.jinja_env.get_template(
            'ubuntu_kickstart.j2',
        ).render(**vm)
    elif vm['id_image'] in [10, 11]:
        ks_text = utils.jinja_env.get_template(
            'centos_kickstart.j2',
        ).render(**vm)
    else:
        driver_logger.error(
            f'Invalid id_image for VM '
            f'#{vm["vm_identifier"]}. VM is set to KVM hypervisor but '
            'does not have a valid Linux image id; expected in [6..11], '
            f'received {vm["id_image"]}',
        )
        return vm_built

    ks_file = f'{vm["vm_identifier"]}.cfg'
    try:
        with open(f'{drive_path}kickstarts/{ks_file}', 'w') as ks:
            ks.write(ks_text)
        driver_logger.debug(
            f'Generated KS file for vm #{vm["vm_identifier"]}\n{ks_text}',
        )
    except Exception:
        driver_logger.error(
            f'Failed to write kickstart to file for VM {vm["vm_identifier"]}',
            exc_info=True,
        )
        return vm_built

    # bridge network xml file creation
    bridge_file_name = f'{drive_path}bridge_xmls/br{ vm["vlan"] }.xml'
    bridge_file = Path(bridge_file_name)
    if not bridge_file.is_file():
        xml_text = utils.jinja_env.get_template(
            'kvm_bridge_network.j2',
        ).render(**vm)
        with open(bridge_file_name, 'w') as xt:
            xt.write(xml_text)
    # make the bridge building command
    br_cmd = utils.jinja_env.get_template(
        'kvm_bridge_build_cmd.j2',
    ).render(drive_path=drive_path, **vm)
    driver_logger.debug(
        f'Generated Bridge Build command for VM #{vm["vm_identifier"]}:'
        f'\n{br_cmd}',
    )
    # make the vm build command
    vm_cmd = utils.jinja_env.get_template(
        'linux_vm_build_cmd.j2',
    ).render(drive_path=drive_path, SUDO_PASS=password, **vm)
    driver_logger.debug(
        f'Generated VM Build command for VM #{vm["vm_identifier"]}:'
        f'\n{vm_cmd}',
    )
    try:
        driver_logger.info(
            f'Attempting to connect to Server @ {vm["host_ip"]}',
        )
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=vm['host_ip'],
            username='administrator',
            password=password,
        )
        # executing bridge interface build command
        driver_logger.info(
            f'Attempting to build bridge network for VM '
            f'#{vm["vm_identifier"]}',
        )
        _, stdout, stderr = client.exec_command(br_cmd)
        if stdout:
            msg = stdout.read().decode().strip()
            if msg:
                driver_logger.info(
                    f'Bridge network build for VM #{vm["vm_identifier"]} '
                    f'generated stdout: {msg}',
                )
        elif stderr:
            msg = stderr.read().decode().strip()
            driver_logger.error(
                f'Bridge network build for VM #{vm["vm_identifier"]} '
                f'generated stderr: {msg}',
            )
        # executing the VM build command
        driver_logger.info(
            f'Attempting to build VM #{vm["vm_identifier"]}',
        )
        _, stdout, stderr = client.exec_command(vm_cmd)
        # Sleep for 10 seconds to ensure that we get enough stdout
        time.sleep(10)
        while stdout.channel.recv_ready():
            msg = stdout.channel.recv(1024).decode()
            if msg:
                driver_logger.info(
                    f'VM build for VM #{vm["vm_identifier"]} '
                    f'generated stdout: {msg}',
                )
            vm_built = True
        while stderr.channel.recv_ready():
            msg = stderr.channel.recv(1024).decode()
            driver_logger.error(
                f'VM build for VM #{vm["vm_identifier"]} '
                f'generated stderr: {msg}',
            )
            vm_built = False
    except Exception:
        driver_logger.error(
            f'Exception occurred during SSHing into host {vm["host_ip"]} '
            f'for the build of VM #{vm["vm_identifier"]}',
            exc_info=True,
        )
    finally:
        client.close()
    return vm_built
