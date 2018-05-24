# python
import os
import subprocess
import sys
import getpass
import time
import netaddr

# libs
from inotify_simple import INotify, flags

# local
import utils
from utils import get_logger_for_name
from ro import service_entity_list, service_entity_read, \
    service_entity_update, password_generator
from vrfBuilders import vrfBuilder
from vmBuilders import vmBuilder
from netBuilders import netBuilder

robot_logger = get_logger_for_name('robot')


def watch_directory() -> INotify:
    """
    Watches the robot directory for changes.
    If a change is deteced, spawn a new Robot instance and kill this one
    :returns: An Inotify instance that can be used to tell if the directory
              has changed
    """
    inotify = INotify()
    # Create flags for the usual things a deployment will change
    watch_flags = flags.CREATE | flags.DELETE | flags.MODIFY
    inotify.add_watch('.', watch_flags)
    return inotify


def call_vrf_builder(vrf, password):
    """
    VRF Dispatcher, takes one VRF, arranges in required format for VRFBuilder
    (VRF Driver) then calls VRFBuilder which will Deploy the VRF in Router
    If success then changes VRF state to Built(4) otherwise on fail changes
    VRF state to Unresourced(3)
    :param VRF: dict object
    :param password: str
    :return: None
    """

    VRF = vrf
    # changing state to Building (2)
    VRF['state'] = 2
    params = {'data': VRF, 'pk': VRF['idVRF']}
    service_entity_update('iaas', 'vrf', params)

    vrfLans = service_entity_list('iaas', 'subnet', {'vrf': VRF['idVRF']})
    regionIPs = service_entity_list('iaas', 'ipaddress', {})

    vrfJson = dict()
    vrfJson['idProject'] = VRF['idProject']
    vrfJson['outBoundIP'] = VRF['IPVrf']

    vrfJson['NATs'] = list()
    vrfJson['vLANs'] = list()
    for vrfLan in vrfLans:
        vrfJson['vLANs'].append({'vLAN': vrfLan['vLAN'],
                                 'subnet': vrfLan['addressRange']})
        # --------------------------------------------------------------
        # NET BUILD CHECK
        if not call_net_builder(vrfLan['vLAN']):
            # changing state to Unresourced (3)
            VRF['state'] = 3
            params = {'data': VRF, 'pk': VRF['idVRF']}
            service_entity_update('iaas', 'vrf', params)
        # ---------------------------------------------------------------

        for ip in regionIPs:
            if ip['idSubnet'] == vrfLan['idSubnet'] and \
                    ip['idIPAddressFIP'] is not None:
                pip = service_entity_read('iaas', 'ipaddress',
                                          {'pk': ip['idIPAddressFIP']})
                vrfJson['NATs'].append({'fIP': str(ip['address']) + '/32',
                                        'pIP': str(pip['address']) + '/32'})

    vrfJson['VPNs'] = service_entity_list('iaas', 'vpn_tunnel',
                                          {'vrf': VRF['idVRF']})

    router = service_entity_read('iaas', 'router', {'pk': VRF['idRouter']})
    vrfJson['oobIP'] = str(router['ipOOB'])

    # ################# data/ip validations ##########################
    # TODO
    # ################################################################

    if vrfBuilder(vrfJson, password):
        robot_logger.info("VRF %d Successfully Built in Router %d"
                          % (VRF['idVRF'], VRF['idRouter']))
        # changing state to Built (4)
        VRF['state'] = 4
        params = {'data': VRF, 'pk': VRF['idVRF']}
        service_entity_update('iaas', 'vrf', params)
    else:
        robot_logger.error("VRF %d Failed to Built in Router %d "
                           "so vrf is unresourced"
                           % (VRF['idVRF'], VRF['idRouter']))
        # changing state to Unresourced (3)
        VRF['state'] = 3
        params = {'data': VRF, 'pk': VRF['idVRF']}
        service_entity_update('iaas', 'vrf', params)
    return


def call_net_builder(vlan):
    """
    NET dispatcher, takes the value of vlan and compares with the max and min
    limits of the QFX fabric.
    :param vlan: int
    :return: boolean
    """
    return netBuilder(vlan)


def call_vm_builder(vm, password):
    """
    VM Dispatcher, takes one VM,
    Arranges data in required format for VMBuilder
    (VM Driver) then calls VMBuilder(different VMBuilder for different
    flavour) which will create the VM in Host
    If success then changes VM state to Built(4) otherwise on fail changes
    VM state to Unresourced(3)
    :param VM: dict object
    :param password: string
    :return: None
    """
    VM = vm
    # changing state to Building (2)
    VM['state'] = 2
    params = {'data': VM, 'pk': VM['idVM']}
    service_entity_update('iaas', 'vm', params)

    vmJson = dict()
    # naming of vmname = 123_2345 (idProject_idVM)
    vmJson['vmname'] = str(VM['idProject']) + '_' + str(VM['idVM'])
    vmJson['hdd'] = VM['hdd']
    vmJson['flash'] = VM['flash']
    vmJson['cpu'] = VM['cpu']
    vmJson['ram'] = VM['ram']
    vmJson['idImage'] = VM['idImage']
    image = service_entity_read('iaas', 'image', {'pk': VM['idImage']})
    vmJson['image'] = str(image['name'])
    vmJson['u_name'] = VM['name']
    # Random passwords generated
    vmJson['u_passwd'] = password_generator()
    vmJson['r_passwd'] = password_generator()
    vmJson['dns'] = VM['dns'].split(',')
    # get the ipadddress and subnet details
    vm_ips = service_entity_list('iaas', 'ipaddress', {'vm': VM['idVM']})
    if len(vm_ips) > 0:
        for vm_ip in vm_ips:
            if netaddr.IPAddress(str(vm_ip['address'])).is_private():
                vmJson['ip'] = str(vm_ip['address'])
                # get the subnet of this ip
                ip_subnet = service_entity_read(
                    'iaas', 'subnet', {'idSubnet': vm_ip['idSubnet']})
                addRange = str(ip_subnet['addressRange'])
                vmJson['gateway'] = addRange.split('/')[0]
                vmJson['netmask'] = addRange.split('/')[1]
                vmJson['netmask_ip'] = str(netaddr.IPNetwork(
                    addRange).netmask)
                vmJson['vlan'] = ip_subnet['vlan']
    vmJson['lang'] = 'en_US'  # need to add in db (for kvm and hyperv)
    vmJson['keyboard'] = 'us'  # need to add in db (for kvm only)
    vmJson['tz'] = 'America/New_York'  # need to add in db(kvm and hyperv)
    # Get the server details
    server_macs = service_entity_list('iaas', 'mac_address',
                                      {'idServer': VM['idServer']})
    for mac in server_macs:
        if mac['status'] is True and netaddr.IPAddress(str(mac['ip'])):
            vmJson['host_ip'] = mac['ip']
            vmJson['host_name'] = mac['dnsName']
            break
    # ################# data/ip validations ##########################
    # TODO
    # ################################################################

    # ----------------------------------------------------------------
    # CHECK IF VRF IS BUILT OR NOT
    # Get the vrf via idProject which is common for both VM and VRF
    vm_vrf = service_entity_list('iaas', 'vrf', {'project': VM['idProject']})
    if not vm_vrf[0]['state'] == 4:
        # changing state to Unresourced (3)
        VM['state'] = 3
        params = {'data': VM, 'pk': VM['idVM']}
        service_entity_update('iaas', 'vm', params)
    # ----------------------------------------------------------------

    # Despatching VMBuilder driver
    if vmBuilder(vmJson, password):
        robot_logger.info("VM %d Successfully Built in Asset %d"
                          % (VM['idVM'], VM['idAsset']))
        # changing state to Built (4)
        VM['state'] = 4
        params = {'data': VM, 'pk': VM['idVM']}
        service_entity_update('iaas', 'vm', params)
    else:
        robot_logger.error("VM %d Failed to Built in Asset %d, "
                           "so VM is unresourced"
                           % (VM['idVM'], VM['idAsset']))
        # changing state to Unresourced (3)
        VM['state'] = 3
        params = {'data': VM, 'pk': VM['idVM']}
        service_entity_update('iaas', 'vm', params)

    return


def mainloop(watcher: INotify, password):
    """
    The main loop of the Robot program
    """
    last = time.time()
    while True:
        # First check to see if there have been any events
        if watcher.read(timeout=1000):
            robot_logger.info('Update detected. Spawning New Robot.')
            subprocess.Popen(['python3', 'robot.py'])
            # Wait a couple of seconds for the new robot to take over
            time.sleep(2)
            # Exit this process gracefully
            sys.exit(0)
        # Now handle the loop events
        # #################  VRF BUILD ######################################
        vrfs = service_entity_list('iaas', 'vrf', params={'state': 1})
        if len(vrfs) > 0:
            for vrf in vrfs:
                robot_logger.info('Building VRF with ID %i.' % vrf['idVRF'])
                call_vrf_builder(vrf, password)
        else:
            robot_logger.info('No VRFs in "Requested" state.')
        # ######################## VM BUILD  ################################
        vms = service_entity_list('iaas', 'vm', params={'state': 1})
        if len(vms) > 0:
            for vm in vms:
                robot_logger.info('Building VM with ID %i' % vm['idVM'])
                call_vm_builder(vm, password)
        else:
            robot_logger.info('No VMs in "Requested" state.')

        while last > time.time() - 20:
            time.sleep(1)
        last = time.time()


if __name__ == '__main__':
    os.system('clear')
    password = ""
    while password == "":
        password = getpass.getpass("Network Password (or exit to quit) ... ")
    if password == "exit":
        sys.exit()
    # When the script is run as the main
    robot_logger.info(
        'Robot starting. Current Commit >> %s' % utils.get_current_git_sha())
    mainloop(watch_directory(), password)
