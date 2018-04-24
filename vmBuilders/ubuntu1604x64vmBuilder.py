# python
import paramiko
from crypt import crypt, mksalt, METHOD_SHA512

# local
from ro import robot_logger

# kickstarts files path
path = "/mnt/images/kickstarts/"


def answerFile(vm):
    """
    creates a answerfile data from given vm
    :param vm: dict
    :return: ks_text: string
    """
    ks_text = ''
    comment = "# {0} Kickstart for VM {1} \n".format(vm['idImage'],
                                                     vm['vmname'])
    ks_text += comment
    # System authorization information
    ks_text += "auth --useshadow --enablemd5\n"
    # System language
    ks_text += "lang " + str(vm['lang']) + "\n"
    # Language modules to install
    ks_text += "langsupport " + str(vm['lang']) + "\n"
    # System keyboard
    ks_text += "keyboard " + str(vm['keyboard']) + "\n"
    # System mouse
    ks_text += "mouse\n"
    # System timezone
    ks_text += "timezone " + str(vm['tz']) + "\n"
    # Root password
    ks_text += "rootpw --iscrypted {0}\n".format(vm['root_pw'])
    # username and password
    ks_text += "user administrator --fullname \"" + str(vm['u_name']) \
               + "\" --password " + str(vm['u_passwd']) + "\n"
    # Reboot after installation
    ks_text += "reboot\n"
    # Use text mode install
    ks_text += "text\n"
    # Install OS instead of upgrade
    ks_text += "install\n"
    # Installation media
    ks_text += "cdrom\n"
    # System bootloader configuration
    ks_text += "bootloader --location=mbr\n"
    # Clear the Master Boot Record
    ks_text += "zerombr yes\n"
    ks_text += "autopart\n"
    # Partition clearing information
    ks_text += "clearpart --all --initlabel\n"
    # Basic disk partition
    ks_text += "part / --fstype ext4 --size 1 --grow --asprimary\n"
    ks_text += "part swap --size 1024\n"
    ks_text += "part / boot --fstype ext4 --size 256 --asprimary\n"
    # System authorization infomation
    ks_text += "auth --useshadow --enablemd5\n"
    # Network
    ks_text += "network --bootproto=static --ip=" + str(vm['ip']) + \
               " --netmask=" + str(vm['netmask_ip']) + " --gateway=" + \
               str(vm['gateway']) + " --nameserver=" + str(vm['dns']) + "\n"
    # Do not configure the X Window System
    ks_text += "iskipx\n"
    # post installation
    ks_text += "%packages\n"
    ks_text += "@ ubuntu-server\n"
    ks_text += "@ openssh-server\n"

    return ks_text


def vmBuild(vm, password):
    """

    :param vm:
    :param password:
    :return: vm_biuld: boolean
    """
    vm_build = False
    # encrypting root and user password
    vm['root_pw'] = str(crypt(vm['r_passwd'], mksalt(METHOD_SHA512)))
    vm['user_pw'] = str(crypt(vm['u_passwd'], mksalt(METHOD_SHA512)))
    ks_text = answerFile(vm)
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
                robot_logger.info(line)
            vm_build = True
        elif stderr:
            robot_logger.error(stderr)
    except Exception as err:
        robot_logger.error(err)

    finally:
        client.close()
    return vm_build
