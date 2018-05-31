# python
import netaddr
from collections import deque

# locals
import net_builders
import ro
import utils
import vm_builders
import vrf_builders


def dispatch_vrf(vrf: dict, password: str):
    """
    VRF Dispatcher, takes one VRF, arranges in required format for VRFBuilder
    (VRF Driver) then calls VRFBuilder which will Deploy the VRF in Router
    If success then changes VRF state to Built(4) otherwise on fail changes
    VRF state to Unresourced(3)
    :param vrf: Data about the vrf for use to build a VRF
    :param password: Network Password
    """
    logger = utils.get_logger_for_name('dispatcher.dispatch_vrf')
    # changing state to Building (2)
    vrf['state'] = 2
    vrf_id = vrf['idVRF']
    logger.info(
        f'Commencing dispatch to build VRF #{vrf_id}'
    )
    ro.service_entity_update('iaas', 'vrf', vrf_id, vrf)

    vrf_lans = ro.service_entity_list('iaas', 'subnet', {'vrf': vrf_id})
    region_ips = ro.service_entity_list('iaas', 'ipaddress', {})

    vrf_json = {
        'idProject': vrf['idProject'],
        'outBoundIP': vrf['IPVrf'],
        'NATs': deque(),
        'vLANs': deque()
    }
    for vrf_lan in vrf_lans:
        vrf_json['vLANs'].append(
            {'vLAN': vrf_lan['vLAN'], 'subnet': vrf_lan['addressRange']}
        )
        # --------------------------------------------------------------
        # NET BUILD CHECK
        if not dispatch_net(vrf_lan['vLAN']):
            # changing state to Unresourced (3)
            vrf['state'] = 3
            ro.service_entity_update('iaas', 'vrf', vrf_id, vrf)
            logger.error(
                f'VRF {vrf_id} has become Unresourced as it has an invalid '
                f'vlan ({vrf_lan["vLAN"]})'
            )
        # ---------------------------------------------------------------

        for ip in region_ips:
            if (ip['idSubnet'] == vrf_lan['idSubnet'] and
                    ip['idIPAddressFIP'] is not None):
                pip = ro.service_entity_read(
                    'iaas', 'ipaddress', ip['idIPAddressFIP']
                )
                vrf_json['NATs'].append({
                    'fIP': f'{ip["address"]}/32',
                    'pIP': f'{pip["address"]}/32'
                })

    vrf_json['VPNs'] = ro.service_entity_list(
        'iaas', 'vpn_tunnel', {'vrf': vrf['idVRF']})

    router = ro.service_entity_read('iaas', 'router', vrf['idRouter'])
    vrf_json['oobIP'] = str(router['ipOOB'])

    # ################# data/ip validations ##########################
    # TODO
    # ################################################################

    if vrf_builders.vrf_build(vrf_json, password):
        logger.info(
            f'Successfully built vrf #{vrf["idVRF"]} in router '
            f'{vrf["idRouter"]}'
        )
        # changing state to Built (4)
        vrf['state'] = 4
        ro.service_entity_update('iaas', 'vrf', vrf_id, vrf)
    else:
        logger.error(
            f'VRF #{vrf_id} failed to build, so it is being moved to '
            'Unresourced state. Check log for details'
        )
        # changing state to Unresourced (3)
        vrf['state'] = 3
        ro.service_entity_update('iaas', 'vrf', vrf_id, vrf)
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
    :param vm: dict object
    :param password: string
    :return: None
    """
    logger = utils.get_logger_for_name('dispatcher.dispatch_vm')
    # changing state to Building (2)
    vm['state'] = 2
    vm_id = vm['idVM']
    logger.info(
        f'Commencing dispatch to build VM #{vm_id}'
    )
    ro.service_entity_update('iaas', 'vm', vm_id, vm)

    image = ro.service_entity_read('iaas', 'image', vm['idImage'])
    vm_json = {
        # Unique Identifer for VM
        'vm_identifier': f'{vm["idProject"]}_{vm["idVM"]}',
        'hdd': vm['hdd'],
        'flash': vm['flash'],
        'cpu': vm['cpu'],
        'ram': vm['ram'],
        'id_image': vm['idImage'],
        'image': str(image['name']),
        'username': vm['name'],
        'user_password': ro.password_generator(),
        'root_password': ro.password_generator(),
        'dns': vm['dns'].split(',')
    }
    # get the ipadddress and subnet details
    vm_ips = ro.service_entity_list('iaas', 'ipaddress', {'vm': vm['idVM']})
    if len(vm_ips) > 0:
        for vm_ip in vm_ips:
            if netaddr.IPAddress(str(vm_ip['address'])).is_private():
                vm_json['ip'] = str(vm_ip['address'])
                # get the subnet of this ip
                ip_subnet = ro.service_entity_read(
                    'iaas', 'subnet', vm_ip['idSubnet'])
                address_range = str(ip_subnet['addressRange'])
                vm_json['gateway'] = address_range.split('/')[0]
                vm_json['netmask'] = address_range.split('/')[1]
                vm_json['netmask_ip'] = str(
                    netaddr.IPNetwork(address_range).netmask)
                vm_json['vlan'] = ip_subnet['vlan']
    vm_json['lang'] = 'en_IE'  # need to add in db (for kvm and hyperv)
    vm_json['keyboard'] = 'ie'  # need to add in db (for kvm only)
    vm_json['tz'] = 'Ireland/Dublin'  # need to add in db(kvm and hyperv)
    # Get the server details
    server_macs = ro.service_entity_list(
        'iaas', 'mac_address', {'idServer': vm['idServer']})
    for mac in server_macs:
        if mac['status'] is True and netaddr.IPAddress(str(mac['ip'])):
            vm_json['host_ip'] = mac['ip']
            vm_json['host_name'] = mac['dnsName']
            break

    # ################# data/ip validations ##########################
    # TODO
    # ################################################################

    # ----------------------------------------------------------------
    # CHECK IF VRF IS BUILT OR NOT
    # Get the vrf via idProject which is common for both VM and VRF
    vm_vrf = ro.service_entity_list(
        'iaas', 'vrf', {'project': vm['idProject']})
    if not vm_vrf[0]['state'] == 4:
        # TODO - Add a wait here until the vrf is built once we add asyncio
        pass
    # ----------------------------------------------------------------

    # Despatching VMBuilder driver
    if vm_builders.vm_builder(vm_json, password):
        logger.info(
            f'VM #{vm["idVM"]} successfully built in Asset #{vm["idAsset"]}'
        )
        # changing state to Built (4)
        vm['state'] = 4
        ro.service_entity_update('iaas', 'vm', vm_id, vm)
    else:
        logger.error(
            f'VM #{vm_id} failed to build, so it is being moved to '
            'Unresourced state. Check log for details'
        )
        # changing state to Unresourced (3)
        vm['state'] = 3
        ro.service_entity_update('iaas', 'vm', vm_id, vm)

    return
