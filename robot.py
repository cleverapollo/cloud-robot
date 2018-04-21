# python
import subprocess
import sys
import getpass
import time

# libs
from inotify_simple import INotify, flags

# local
import state
from ro import *
from vrfBuilder import vrfBuild
from vmBuilders import vmBuilder


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
                                        {'pk': VRF['idIPVrf']})['address']]
    vrfLans = service_entity_list('iaas', 'subnet',{'vrf': VRF['idVRF']})
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
                                      {'pk': vrfIP['idIPAdressFIP']})
            vrfJson['proxyIPs'].append(str(fip['address']) + '/32')
    router = service_entity_read('iaas', 'router', {'pk': VRF['idRouter']})
    vrfJson['oobIP'] = str(router['ipOOB'])
    vrfJson['VPNs'] = [service_entity_list('iaas', 'vpn_tunnel',
                                           {'vrf': VRF['idVRF']})]
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
    :return: None or True
    """
    status = None
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
                               %vm['idVM'])
            return status
        for host in hosts:
            if host['extra']['type'] == hypervisor:
                for assetedVm in assetedVms:
                    if assetedVm['idAsset'] == host['id']:
                        host['extra']['hdd'] -= assetedVm['hdd']
                        host['extra']['sdd'] -= assetedVm['sdd']
                        host['extra']['ram'] -= assetedVm['ram']

            if (((host['extra']['hdd'] - 20) >= vm['hdd'] or
               (host['extra']['ssd'] - 20) >= vm['ssd']) and
               (host['extra']['ram']) >= vm['ram']):
                vm['idAsset'] = host['id']
                vm['state'] = 2
                params = {'data': vm, 'pk': vm['idVM']}
                if service_entity_update('iaas', 'vm', params):
                    assetedVms.append(vm)
                    status = True
                    robot_logger.info("%d VM is allocated in %d Asset"
                                      %(vm['idVM'], vm['idAsset']))
                else:
                    robot_logger.error("Failed to Update VM %d with %d "
                                       "idAsset" %(vm['idVM'], host['id']))
                break
    else:
        robot_logger.info("No host has capacity to accommodate \
                               a VM, please add an Asset for hosting!")
    return status


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
    if vmAssetAssign(VM):
        robot_logger.info("Calling VMBuilder for %d"%VM['idVM'])

        vmJson = dict()
        # vmJson['vmname'] =
        # vmJson['hdd'] =
        # vmJson['flash'] =
        # vmJson['cpu'] =
        # vmJson['image'] =
        vmJson['u_name'] = 'Naveen'
        vmJson['u_passwd'] = 'n@V33n@01'
        vmJson['r_passwd'] = 'c3nt05o7'
        vmJson['lang'] = 'en_US'
        vmJson['keyboard'] = 'us'
        vmJson['tz'] = 'America/New_York'
        vmJson['ip'] = '192.168.65.3'
        vmJson['netmask'] = '255.255.255.0'
        vmJson['gateway'] = '192.168.65.1'
        vmJson['dns'] = '91.103.0.1'
        vmJson['vlan'] = 1000
        # TODO
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
        ##################  VRF BUILD ######################################
        VRF = state.vrf(1)
        if VRF is not None:
            robot_logger.info('Building VRF with ID %i.' % VRF['idVRF'])
            call_vrf_builder(VRF, password)
        else:
            robot_logger.info('No VRFs in "Requested" state.')
        ######################### VM BUILD  ################################
        VM = state.vm(1)
        if VM is not None:
            robot_logger.info('Building VM with ID %i' % VM['idVM'])
            call_vm_builder(VM, password)
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
    robot_logger = utils.get_logger_for_name('robot')
    robot_logger.info(
        'Robot starting. Current Commit >> %s' % utils.get_current_git_sha())
    mainloop(watch_directory(), password)
