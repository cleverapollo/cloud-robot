# python
import netaddr
import time
from collections import deque

# locals
from builders import VRF as Builder
import metrics
import ro
import utils
import vm_builder
import vrf_builders
from net_builders import is_valid_vlan


class VRF:
    """
    A class that handles 'dispatching' a VRF to various services such as builders, scrubbers, etc.
    """

    # Network password used to login to the routers
    password: str

    def __init__(self, password: str):
        self.password = password

    def build(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for building it and requests to build it
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.build')
        vrf_id = vrf['idVRF']
        logger.info(f'Commencing build dispatch of VRF #{vrf_id}')
        # Change the state of the vrf to be 'Building' (2)
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 2})

        # Get other necessary information about the VRF
        nats = deque()
        vlans = deque()
        vpns = deque()

        # Build up details for these deques
        for subnet in ro.service_entity_list('IAAS', 'subnet', {'vrf': vrf_id}):
            # First check if the VLAN number is valid for the switch
            if not is_valid_vlan(subnet['vLAN']):
                ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
                logger.error(
                    f'VRF {vrf_id} has become Unresourced as it has an invalid '
                    f'vlan ({vrf_lan["vLAN"]})',
                )
                return
            vlans.append({'vlan': subnet['vLAN'], 'address_range': subnet['addressRange']})

            # Check if there are any nats for this subnet
            params = {'subnet__idSubnet': subnet['idSubnet'], 'idIPAddressFIP__isnull': False, 'fields': '(*,fip)'}
            for ip in ro.service_entity_list('IAAS', 'ipaddress', params):
                nats.append({'private': ip['address'], 'public': ip['fip']['address']})

        # VPNs
        for vpn in ro.service_entity_list('IAAS', 'vpn_tunnel', {'vrf': vrf_id}):
            subnet = ro.service_entity_read('IAAS', 'subnet', vpn['vpnLocalSubnet'])
            vpn['vlan'] = subnet['vLAN']
            vpn['local_subnet'] = netaddr.IPNetwork(subnet['addressRange']).cidr
            vpns.append(vpn)

        # OOB IP
        vrf['oob_ip'] = ro.service_entity_read('IAAS', 'router', vrf['idRouter'])['ipManagement']

        # TODO - Add data/ip validations to vrf dispatcher

        # Attempt to build the VRF
        if Builder.build(vrf, self.password):
            logger.info(f'Successfully built VRF #{vrf_id} in router {vrf["idRouter"]}')
            # Change the state to 4 and report a success to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 4})
            metrics.vrf_success()
        else:
            logger.error(
                f'VRF #{vrf_id} failed to build, so it is being moved to Unresourced state. Check log for details',
            )
            # Change the state to 3 and report a failure to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
            metrics.vrf_failure()
