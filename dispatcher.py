# python
import netaddr

# locals
import net_builders
import ro
import utils
import vm_builders
import vrf_builders


def dispatch_vrf(vrf: dict, password: str) -> None:
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
    ro.service_entity_update('iaas', 'vrf', params)

    vrfLans = ro.service_entity_list('iaas', 'subnet', {'vrf': VRF['idVRF']})
    regionIPs = ro.service_entity_list('iaas', 'ipaddress', {})

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
        if not dispatch_net(vrfLan['vLAN']):
            # changing state to Unresourced (3)
            VRF['state'] = 3
            params = {'data': VRF, 'pk': VRF['idVRF']}
            ro.service_entity_update('iaas', 'vrf', params)
            utils.get_logger_for_name('dispatcher.dispatch_vrf').error(
                f"VRF {VRF['idVRF']} Failed to Built in Router as its has "
                f"invalid vlan so vrf-{VRF['idVRF']} is unresourced")
        # ---------------------------------------------------------------

        for ip in regionIPs:
            if (ip['idSubnet'] == vrfLan['idSubnet'] and
                    ip['idIPAddressFIP'] is not None):
                pip = ro.service_entity_read('iaas', 'ipaddress',
                                             {'pk': ip['idIPAddressFIP']})
                vrfJson['NATs'].append({'fIP': str(ip['address']) + '/32',
                                        'pIP': str(pip['address']) + '/32'})

    vrfJson['VPNs'] = ro.service_entity_list('iaas', 'vpn_tunnel',
                                             {'vrf': VRF['idVRF']})

    router = ro.service_entity_read('iaas', 'router', {'pk': VRF['idRouter']})
    vrfJson['oobIP'] = str(router['ipOOB'])

    # ################# data/ip validations ##########################
    # TODO
    # ################################################################

    if vrf_builders.vrf_build(vrfJson, password):
        utils.get_logger_for_name('dispatcher.dispatch_vrf').info(
            f"VRF {VRF['idVRF']} Successfully Built in Router "
            f"{VRF['idRouter']}"
        )
        # changing state to Built (4)
        VRF['state'] = 4
        params = {'data': VRF, 'pk': VRF['idVRF']}
        ro.service_entity_update('iaas', 'vrf', params)
    else:
        utils.get_logger_for_name('dispatcher.dispatch_vrf').error(
            f"VRF {VRF['idVRF']} Failed to Built in Router "
            f"{VRF['idVRF']} so vrf is unresourced")
        # changing state to Unresourced (3)
        VRF['state'] = 3
        params = {'data': VRF, 'pk': VRF['idVRF']}
        ro.service_entity_update('iaas', 'vrf', params)
    return


def dispatch_net(vlan: int) -> bool:
    """
    NET dispatcher, takes the value of vlan and compares with the max and min
    limits of the QFX fabric.
    :param vlan: int
    :return: boolean
    """
    return net_builders.is_valid_vlan(vlan)


def dispatch_vm(vm: dict, password: str) -> None:
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
    ro.service_entity_update('iaas', 'vm', params)

    vmJson = dict()
    # naming of vmname = 123_2345 (idProject_idVM)
    vmJson['vmname'] = str(VM['idProject']) + '_' + str(VM['idVM'])
    vmJson['hdd'] = VM['hdd']
    vmJson['flash'] = VM['flash']
    vmJson['cpu'] = VM['cpu']
    vmJson['ram'] = VM['ram']
    vmJson['idImage'] = VM['idImage']
    image = ro.service_entity_read('iaas', 'image', {'pk': VM['idImage']})
    vmJson['image'] = str(image['name'])
    vmJson['u_name'] = VM['name']
    # Random passwords generated
    vmJson['u_passwd'] = ro.password_generator()
    vmJson['r_passwd'] = ro.password_generator()
    vmJson['dns'] = VM['dns'].split(',')
    # get the ipadddress and subnet details
    vm_ips = ro.service_entity_list('iaas', 'ipaddress', {'vm': VM['idVM']})
    if len(vm_ips) > 0:
        for vm_ip in vm_ips:
            if netaddr.IPAddress(str(vm_ip['address'])).is_private():
                vmJson['ip'] = str(vm_ip['address'])
                # get the subnet of this ip
                ip_subnet = ro.service_entity_read(
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
    server_macs = ro.service_entity_list('iaas', 'mac_address',
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
    vm_vrf = ro.service_entity_list('iaas', 'vrf',
                                    {'project': VM['idProject']})
    if not vm_vrf[0]['state'] == 4:
        # changing state to Unresourced (3)
        VM['state'] = 3
        params = {'data': VM, 'pk': VM['idVM']}
        ro.service_entity_update('iaas', 'vm', params)
    # ----------------------------------------------------------------

    # Despatching VMBuilder driver
    if vm_builders.vm_builder(vmJson, password):
        utils.get_logger_for_name('dispatcher.dispatch_vm').info(
            f"VM {VM['idVM']} Successfully Built in Asset {VM['idAsset']}"
        )
        # changing state to Built (4)
        VM['state'] = 4
        params = {'data': VM, 'pk': VM['idVM']}
        ro.service_entity_update('iaas', 'vm', params)
    else:
        utils.get_logger_for_name('dispatcher.dispatch_vm').error(
            f"VM {VM['idVM']} Failed to Built in Asset {VM['idAsset']}, "
            f"so VM is unresourced"
        )
        # changing state to Unresourced (3)
        VM['state'] = 3
        params = {'data': VM, 'pk': VM['idVM']}
        ro.service_entity_update('iaas', 'vm', params)

    return
