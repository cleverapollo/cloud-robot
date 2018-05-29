# python
import paramiko
from crypt import crypt, mksalt, METHOD_SHA512

# local
import utils

# kickstart files path
path = '/mnt/images/kickstarts/'
driver_logger = utils.get_logger_for_name('centos7.vm_build')


def answer_file(vm: dict) -> str:
    """
    Creates an answer file to be used to create the VM specified
    :param vm: Data for the VM that will be created
    :return: ks_text: The answer file that can build the specified VM
    """
    ks_text = f'# {vm["idImage"]} Kickstart for VM {vm["vmname"]} \n'
    # System authorization information
    ks_text += 'auth --enableshadow --passalgo=sha512\n'
    # Clear the Master Boot Record
    ks_text += 'zerombr\n'
    # Partition clearing information
    ks_text += 'clearpart --all --initlabel\n'
    # Use text mode install
    ks_text += 'text\n'
    # Firewall configuration
    ks_text += 'firewall --disabled\n'
    # Run the Setup Agent on first boot
    ks_text += 'firstboot --disable\n'
    # System keyboard
    ks_text += f'keyboard {vm["keyboard"]}\n'
    # System language
    ks_text += f'lang {vm["lang"]}.UTF-8\n'
    # Installation logging level
    ks_text += 'logging --level=info\n'
    #  installation media
    ks_text += 'cdrom\n'
    # Network Information
    ks_text += (
        f'network --bootproto=static --ip={vm["ip"]} '
        f'--netmask={vm["netmask_ip"]} --gateway={vm["gateway"]} '
        f'--nameserver={vm["dns"]}\n'
    )
    # System bootloader configuration
    ks_text += 'bootloader --location=mbr\n'
    # Disk Partioning
    ks_text += 'clearpart --all --initlabel\n'
    ks_text += 'part swap --asprimary --fstype=\'swap\' --size=1024\n'
    ks_text += 'part /boot --fstype xfs --size=200\n'
    ks_text += 'part pv.01 --size=1 --grow\n'
    ks_text += 'volgroup rootvg01 pv.01\n'
    ks_text += (
        'logvol / --fstype xfs --name=lv01 --vgname=rootvg01'
        ' --size=1 --grow\n'
    )
    # Root password
    ks_text += f'rootpw --iscrypted {vm["root_pw"]}\n'.format()
    # username and password
    ks_text += (
        f'user administrator --name "{vm["u_name"]}" '
        f'--password={vm["user_pw"]} --iscrypted\n'
    )
    # SELinux configuration
    ks_text += 'selinux --disabled\n'
    # Do not configure the X Window System
    ks_text += 'skipx\n'
    # System timezone
    ks_text += f'timezone --utc {vm["tz"]}\n'
    # Install OS instead of upgrade
    ks_text += 'install\n'
    # Reboot after installation
    ks_text += 'reboot\n'
    # list of packages to be installed
    ks_text += '%%packages\n@core\n%%end\n'

    return ks_text


def vm_build(vm: dict, password: str) -> bool:
    """
    Builds a VM with the given information
    :param vm: Data to use for building the VM
    :param password: Password for the VM
    :return: vm_built: Flag stating whether or not the build succeeded
    """
    vm_built = False
    # encrypting root and user password
    vm['root_pw'] = str(crypt(vm['r_passwd'], mksalt(METHOD_SHA512)))
    vm['user_pw'] = str(crypt(vm['u_passwd'], mksalt(METHOD_SHA512)))
    ks_text = answer_file(vm)
    ks_file = f'{vm['name']}.cfg'
    with open(f'{path}{ks_file}', 'w') as ks:
        ks.write(ks_text)
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=vm['host_ip'], username='administrator',
                       password=password)

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
        driver_logger.exception(
            f'Exception occurred during SSHing into host {vm["host_ip"]}'
        )

    finally:
        client.close()
    return vm_built
