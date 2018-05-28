# python
import paramiko
from crypt import crypt, mksalt, METHOD_SHA512

# local
import utils

# kickstart files path
path = "/mnt/images/kickstarts/"
driver_logger = utils.get_logger_for_name('centos7.vm_build')


def answer_file(vm: dict) -> str:
    """
    creates a answerfile data from given vm
    :param vm: dict
    :return: ks_text: string
    """
    ks_text = ''
    comment = f"# {vm['idImage']} Kickstart for VM {vm['vmname']} \n"
    ks_text += comment
    # System authorization information
    ks_text += "auth --enableshadow --passalgo=sha512\n"
    # Clear the Master Boot Record
    ks_text += "zerombr\n"
    # Partition clearing information
    ks_text += "clearpart --all --initlabel\n"
    # Use text mode install
    ks_text += "text\n"
    # Firewall configuration
    ks_text += "firewall --disabled\n"
    # Run the Setup Agent on first boot
    ks_text += "firstboot --disable\n"
    # System keyboard
    ks_text += "keyboard {}\n".format(vm['keyboard'])
    # System language
    ks_text += "lang {}.UTF-8\n".format(vm['lang'])
    # Installation logging level
    ks_text += "logging --level=info\n"
    #  installation media
    ks_text += "cdrom\n"
    # Network Information
    ks_text += "network --bootproto=static --ip=" + str(vm['ip']) + \
               " --netmask=" + str(vm['netmask_ip']) + " --gateway=" + \
               str(vm['gateway']) + " --nameserver=" + str(vm['dns']) + "\n"
    # System bootloader configuration
    ks_text += "bootloader --location=mbr\n"
    # Disk Partioning
    ks_text += "clearpart --all --initlabel\n"
    ks_text += "part swap --asprimary --fstype=\"swap\" --size=1024\n"
    ks_text += "part /boot --fstype xfs --size=200\n"
    ks_text += "part pv.01 --size=1 --grow\n"
    ks_text += "volgroup rootvg01 pv.01\n"
    ks_text += "logvol / --fstype xfs --name=lv01 --vgname=rootvg01" \
               " --size=1 --grow\n"
    # Root password
    ks_text += "rootpw --iscrypted {0}\n".format(vm['root_pw'])
    # username and password
    ks_text += "user administrator --name \"" + str(vm['u_name']) \
               + "\" --password=" + str(vm['user_pw']) + " --iscrypted\n"
    # SELinux configuration
    ks_text += "selinux --disabled\n"
    # Do not configure the X Window System
    ks_text += "skipx\n"
    # System timezone
    ks_text += "timezone --utc {}\n".format(vm['tz'])
    # Install OS instead of upgrade
    ks_text += "install\n"
    # Reboot after installation
    ks_text += "reboot\n"
    # list of packages to be installed
    ks_text += "%packages\n@core\n%end\n"

    return ks_text


def vm_build(vm: dict, password: str) -> bool:
    """

    :param vm:
    :param password:
    :return: vm_biuld: boolean
    """
    vm_built = False
    # encrypting root and user password
    vm['root_pw'] = str(crypt(vm['r_passwd'], mksalt(METHOD_SHA512)))
    vm['user_pw'] = str(crypt(vm['u_passwd'], mksalt(METHOD_SHA512)))
    ks_text = answer_file(vm)
    ks_file = str(vm['name']) + ".cfg"
    with open(path + ks_file, 'w') as ks:
        ks.write(ks_text)
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=vm['host_ip'], username='administrator',
                       password=password)

        # make the cmd
        cmd = "sudo virt-install --name " + vm['name'] + " --memory " + \
              str(vm['ram']) + " --vcpus " + str(vm['cpu']) + \
              " --disk path=/var/lib/libvirt/images/" + str(vm['name']) + \
              ".qcow2,size=" + str(vm['hdd']) + \
              " --graphics vnc --location /mnt/images/" + \
              str(vm['image']).replace(' ', '\ ') + ".iso" + \
              " --os-variant rhel6 --initrd-inject " + path + ks_file + \
              " -x  \"ks=file:/" + ks_file + "\" --network bridge=br" + \
              str(vm['vlan'])
        stdin, stdout, stderr = client.exec_command(cmd)
        if stdout:
            for line in stdout:
                driver_logger.info(line)
            vm_built = True
        elif stderr:
            driver_logger.error(stderr)
    except Exception:
        driver_logger.exception("Exception occurred during SSHing into host")

    finally:
        client.close()
    return vm_built
