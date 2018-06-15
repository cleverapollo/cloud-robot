# python
import netaddr
import time
from collections import deque

# locals
import metrics
import net_builders
import ro
import utils
import vm_builder
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
        f'Commencing dispatch to build VRF #{vrf_id}',
    )
    ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 2})

    vrf_lans = ro.service_entity_list('IAAS', 'subnet', {'vrf': vrf_id})
    region_ips = ro.service_entity_list('IAAS', 'ipaddress', {})

    vrf_json = {
        'idProject': vrf['idProject'],
        'outBoundIP': vrf['IPVrf'],
        'NATs': deque(),
        'vLANs': deque(),
    }
    for vrf_lan in vrf_lans:
        vrf_json['vLANs'].append(
            {'vLAN': vrf_lan['vLAN'], 'subnet': vrf_lan['addressRange']},
        )
        # --------------------------------------------------------------
        # NET BUILD CHECK
        if not dispatch_net(vrf_lan['vLAN']):
            # changing state to Unresourced (3)
            vrf['state'] = 3
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
            logger.error(
                f'VRF {vrf_id} has become Unresourced as it has an invalid '
                f'vlan ({vrf_lan["vLAN"]})',
            )
        # ---------------------------------------------------------------

        for ip in region_ips:
            if (ip['idSubnet'] == vrf_lan['idSubnet'] and
                    ip['idIPAddressFIP'] is not None):
                pip = ro.service_entity_read(
                    'IAAS',
                    'ipaddress',
                    ip['idIPAddressFIP'],
                )
                vrf_json['NATs'].append({
                    'fIP': f'{ip["address"]}/32',
                    'pIP': f'{pip["address"]}/32',
                })

    vrf_json['VPNs'] = ro.service_entity_list(
        'IAAS',
        'vpn_tunnel',
        {'vrf': vrf['idVRF']},
    )

    router = ro.service_entity_read('IAAS', 'router', vrf['idRouter'])
    vrf_json['oobIP'] = str(router['ipManagement'])

    # ################# data/ip validations ##########################
    # TODO - Add data/ip validations to vrf dispatcher
    # ################################################################

    if vrf_builders.vrf_build(vrf_json, password):
        logger.info(
            f'Successfully built vrf #{vrf["idVRF"]} in router '
            f'{vrf["idRouter"]}',
        )
        # changing state to Built (4)
        vrf['state'] = 4
        # Log a success in Influx
        metrics.vrf_success()
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 4})
    else:
        logger.error(
            f'VRF #{vrf_id} failed to build, so it is being moved to '
            'Unresourced state. Check log for details',
        )
        # changing state to Unresourced (3)
        vrf['state'] = 3
        # Log a failure in Influx
        metrics.vrf_failure()
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
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
        f'Commencing dispatch to build VM #{vm_id}',
    )
    ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 2})

    image = ro.service_entity_read('IAAS', 'image', vm['idImage'])
    vm_json = {
        # Unique Identifer for VM
        'vm_identifier': f'{vm["idProject"]}_{vm["idVM"]}',
        'hdd': vm['hdd'],
        'flash': vm['flash'],
        'cpu': vm['cpu'],
        'ram': vm['ram'],
        'id_image': vm['idImage'],
        'image': str(image['name']).replace(' ', r'\ '),
        'hypervisor': image['idHypervisor'],
        'username': vm['name'],
        'user_password': ro.password_generator(chars='a', size=8),
        'root_password': ro.password_generator(),
        'dns': vm['dns'].split(','),
    }
    # get the ipadddress and subnet details
    vm_ips = ro.service_entity_list('IAAS', 'ipaddress', {'vm': vm['idVM']})
    if len(vm_ips) > 0:
        for vm_ip in vm_ips:
            if netaddr.IPAddress(str(vm_ip['address'])).is_private():
                vm_json['ip'] = str(vm_ip['address'])
                # get the subnet of this ip
                ip_subnet = ro.service_entity_read(
                    'IAAS',
                    'subnet',
                    vm_ip['idSubnet'],
                )
                address_range = str(ip_subnet['addressRange'])
                vm_json['gateway'] = address_range.split('/')[0]
                vm_json['netmask'] = address_range.split('/')[1]
                vm_json['netmask_ip'] = str(
                    netaddr.IPNetwork(address_range).netmask,
                )
                vm_json['vlan'] = ip_subnet['vLAN']
    vm_json['lang'] = 'en_IE'  # need to add in db (for kvm and hyperv)
    vm_json['keyboard'] = 'ie'  # need to add in db (for kvm only)
    vm_json['tz'] = 'Ireland/Dublin'  # need to add in db(kvm and hyperv)
    # Get the server details
    server_macs = ro.service_entity_list(
        'IAAS',
        'macaddress',
        {},
        idServer=vm['idServer'],
    )
    # get the server's ip address from the mac address, there will be only one
    # mac address with its status as True and a valid ipaddress out of many mac
    # addresses of the server.
    for mac in server_macs:
        if mac['status'] is True and mac['ip'] is not None:
            try:
                vm_json['host_ip'] = str(netaddr.IPAddress(str(mac['ip'])))
                vm_json['host_name'] = mac['dnsName']
                break
            except netaddr.AddrFormatError:
                logger.error(
                    f'Exception occurred during reading ip address of mac '
                    f'with id:{mac["idMacAddress"]} so {vm_id} vm is '
                    f'unresourced',
                    exc_info=True,
                )
                # changing state to Unresourced (3)
                vm['state'] = 3
                # Log a failure in Influx
                metrics.vm_failure()
                ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})

    # ################# data/ip validations ##########################
    # TODO - Add data/ip validations to vm dispatcher
    # ################################################################

    # ----------------------------------------------------------------
    # CHECK IF VRF IS BUILT OR NOT
    # Get the vrf via idProject which is common for both VM and VRF
    vrf_request_data = {'project': vm['idProject']}
    vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)
    while vm_vrf[0]['state'] != 4:
        time.sleep(5)
        vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)
    # ----------------------------------------------------------------

    # Despatching VMBuilder driver
    if vm_builder.vm_build(vm_json, password):
        logger.info(
            f'VM #{vm["idVM"]} successfully built in Asset #{vm["idAsset"]}',
        )
        # changing state to Built (4)
        vm['state'] = 4
        # Log a success in Influx
        metrics.vm_success()
        ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 4})
    else:
        logger.error(
            f'VM #{vm_id} failed to build, so it is being moved to '
            'Unresourced state. Check log for details',
        )
        # changing state to Unresourced (3)
        vm['state'] = 3
        # Log a failure in Influx
        metrics.vm_failure()
        ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})

    return
