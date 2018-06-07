# python
import paramiko
from crypt import crypt, mksalt, METHOD_SHA512
# local
import utils

# kickstart files path
path = '/mnt/images/kickstarts/'
driver_logger = utils.get_logger_for_name('ubuntu1404x64.vm_build')


def vm_build(vm: dict, password: str) -> bool:
    """
    Builds a VM with the given information
    :param vm: Data to use for building the VM
    :param password: Password for the VM
    :return: vm_built: Flag stating whether or not the build succeeded
    """
    vm_built = False
    # encrypting root and user password
    vm['crypted_root_pw'] = str(
        crypt(vm['root_password'], mksalt(METHOD_SHA512)))
    vm['crypted_user_pw'] = str(
        crypt(vm['user_password'], mksalt(METHOD_SHA512)))
    ks_text = utils.jinja_env.get_template('ubuntu_kickstart.j2').render(**vm)
    driver_logger.debug(
        f'Generated KS file for vm #{vm["vm_identifier"]}\n{ks_text}'
    )
    ks_file = f'{vm["name"]}.cfg'
    with open(f'{path}{ks_file}', 'w') as ks:
        ks.write(ks_text)
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=vm['host_ip'],
            username='administrator',
            password=password
        )

        # make the cmd
        image_replaced = vm['image'].replace(' ', r'\ ')
        cmd = (
            f'sudo virt-install --name {vm["name"]} --memory {vm["ram"]} '
            f'--vcpus {vm["cpu"]} --disk path=/var/lib/libvirt/images/'
            f'{vm["name"]}.qcow2,size={vm["hdd"]} --graphics vnc --location '
            f'/mnt/images/{image_replaced}.iso --os-variant '
            f'rhel6 --initrd-inject {path}{ks_file} -x "ks=file:/{ks_file}" '
            f'--network bridge=br{vm["vlan"]}'
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
            f'Exception occurred during SSHing into host {vm["host_ip"]}',
            exc_info=True
        )

    else:
        client.close()
    return vm_built
