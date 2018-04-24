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
from vrfBuilder import vrfBuild
from vmBuilders import vmBuilder

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


def call_vrf_builder(VRF, password):
    """
    VRF Dispatcher, takes one VRF, arranges in required format for VRFBuilder
    (VRF Driver) then calls VRFBuilder which will Deploy the VRF in Router
    If success then changes VRF state to Built(4) otherwise on fail changes
    VRF state to Unresourced(3)
    :param VRF: dict object
    :param password: str
    :return: None
    """
    vrfJson = dict()
    vrfJson['idProject'] = VRF['idProject']
    vrfJson['publicIP'] = [service_entity_read('iaas', 'ipaddress',
                                               {'pk': VRF['idIPVrf']}
                                               )['address']]
    vrfLans = service_entity_list('iaas', 'subnet', {'vrf': VRF['idVRF']})
    vrfJson['vLANs'] = list()
    vrfIPs = list()
    for vrfLan in vrfLans:
        vrfJson['vLANs'].append([vrfLan['vLAN'], vrfLan['addressRange']])
        vrfIPs.extend(service_entity_list('iaas', 'ipaddress',
                                          {'subnet': vrfLan['idSubnet']}))
    vrfJson['privateNATips'] = list()
    vrfJson['proxyIPs'] = list()
    for vrfIP in vrfIPs:
        if vrfIP['idIPAddressFIP']:
            vrfJson['privateNATips'].append(str(vrfIP['address']) + '/32')
            fip = service_entity_read('iaas', 'ipaddress',
                                      {'pk': vrfIP['idIPAddressFIP']})
            vrfJson['proxyIPs'].append(str(fip['address']) + '/32')
    router = service_entity_read('iaas', 'router', {'pk': VRF['idRouter']})
    vrfJson['oobIP'] = str(router['ipOOB'])
    vrfJson['VPNs'] = service_entity_list('iaas', 'vpn_tunnel',
                                          {'vrf': VRF['idVRF']})
    ################## data/ip validations ##########################
    # TODO
    #################################################################
    if vrfBuild(vrfJson, password):
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


def vmAssetAssign(vm):
    """
    Finds best suited asset for a VM and assigns that asset's id to VM
    as idAsset
    :param vm: dictionary object
    :return:status: None or True; idAsset: None or int
    """
    status = None
    asset = dict()
    # list all assets(which are hosts) to Build/Delete VMs
    hosts = service_entity_list('asset', 'asset', {'extra__host': True})
    # list all VMs which are already assinged with idAsset.
    assetedVms = service_entity_list('iaas', 'vm',
                                     {'state__in':
                                         [2, 3, 4, 5, 6, 7, 8, 10, 11]})
    if hosts:
        # the type of host ie HyperV or KVM
        image = service_entity_read('iaas', 'image', {'pk': vm['idImage']})
        if image:
            hypervisor = image['idHypervisor']
        else:
            robot_logger.error("VM has no image specified, %d "
                               "this VM will not be created"
                               % vm['idVM'])
            return status
        for host in hosts:
            if host['extra']['type'] == hypervisor:
                if len(assetedVms) > 0:
                    for assetedVm in assetedVms:
                        if assetedVm['idAsset'] == host['id']:
                            host['extra']['hdd'] -= assetedVm['hdd']
                            host['extra']['flash'] -= assetedVm['flash']

                if (((host['extra']['hdd'] - 20) >= vm['hdd'] or
                   (host['extra']['flash'] - 20) >= vm['flash']) and
                   (host['extra']['ram']) > vm['ram']):
                    vm['idAsset'] = host['id']
                    vm['state'] = 2
                    params = {'data': vm, 'pk': vm['idVM']}
                    if service_entity_update('iaas', 'vm', params):
                        status = True
                        # Get the asset details
                        asset['idAsset'] = vm['idAsset']
                        for mac in host['extra']['macAddresses']:
                            if mac['ip'] != '' and mac['status'] == 'up':
                                asset['host_ip'] = mac['ip']
                                # asset['host_name'] = TODO
                        robot_logger.info("%d VM is allocated in %d Asset"
                                          % (vm['idVM'], vm['idAsset']))
                    else:
                        robot_logger.error("Failed to Update VM %d with %d "
                                           "idAsset" % (vm['idVM'],
                                                        host['id']))
                    break
    else:
        robot_logger.info("No host has capacity to accommodate \
                               a VM, please add an Asset for hosting!")
    return status, asset


def call_vm_builder(VM, password):
    """
    VM Dispatcher, takes one VM,
    First calls for vmAssetAssign() to get idAsset(host, where vm will be
    created) for this vm.
    On success of above call, arranges data in required format for VMBuilder
    (VM Driver) then calls VMBuilder(different VMBuilder for different
    flavour) which will create the VM in Host
    If success then changes VM state to Built(4) otherwise on fail changes
    VM state to Unresourced(3)
    :param VM: dict object
    :param password: string
    :return: None
    """
    # calling vmAssetAssign()
    status, asset = vmAssetAssign(VM)
    if status:
        robot_logger.info("Calling VMBuilder for %d" % VM['idVM'])
        # Arranging vm data in required format for vmBuilders
        vmJson = dict()
        # naming of vmname = 123_2345 idProject_idVM
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
                    addRange =  str(ip_subnet['addressRange'])
                    vmJson['gateway'] = addRange.split('/')[0]
                    vmJson['netmask'] = addRange.split('/')[1]
                    vmJson['netmask_ip'] = str(netaddr.IPNetwork(
                        addRange).netmask)
                    vmJson['vlan'] = ip_subnet['vlan']
        vmJson['lang'] = 'en_US'  # need to add in db (for kvm and hyperv)
        vmJson['keyboard'] = 'us'  # need to add in db (for kvm only)
        vmJson['tz'] = 'America/New_York'  # need to add in db(kvm and hyperv)
        vmJson['host_ip'] = asset['host_ip']
        vmJson['host_name'] = asset['host_name']
        ################## data/ip validations ##########################
        # TODO
        #################################################################
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
    else:
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
