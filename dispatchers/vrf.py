# python
import netaddr
from collections import deque

# locals
from builders import Vrf as Builder
from quiescers import Vrf as Quiescer
from scrubbers import Vrf as Scubber
import metrics
import ro
import utils
from net_builders import is_valid_vlan


class Vrf:
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
                    f'vlan ({subnet["vLAN"]})',
                )
                return
            vlans.append({'vlan': subnet['vLAN'], 'address_range': subnet['addressRange']})

            # Check if there are any nats for this subnet
            params = {'subnet__idSubnet': subnet['idSubnet'], 'fip_id__isnull': False, 'fields': '(*,fip)'}
            for ip in ro.service_entity_list('IAAS', 'ipaddress', params):
                nats.append({'private': ip['address'], 'public': ip['fip']['address']})

        # VPNs
        for vpn in ro.service_entity_list('IAAS', 'vpn_tunnel', {'vrf': vrf_id}):
            subnet = ro.service_entity_read('IAAS', 'subnet', vpn['vpnLocalSubnet'])
            vpn['vlan'] = subnet['vLAN']
            vpn['remote_subnet_cidr'] = netaddr.IPNetwork(
                f'{vpn["vpnRemoteSubnetIP"]}/{vpn["vpnRemoteSubnetMask"]}',
            ).cidr
            vpns.append(vpn)

        # adding vlans, nats and vpns to vrf
        vrf['vlans'] = vlans
        vrf['nats'] = nats
        vrf['vpns'] = vpns

        # Router data: maskVPN and OOB IP
        router_data = ro.service_entity_read('IAAS', 'router', vrf['idRouter'])
        vrf['oob_ip'] = router_data['ipManagement']
        vrf['mask_vpn'] = router_data['maskVPN']

        # TODO - Add data/ip validations to vrf dispatcher

        # Attempt to build the VRF
        if Builder.build(vrf, self.password):
            logger.info(f'Successfully built VRF #{vrf_id} in router {vrf["idRouter"]}')
            # Change the state to 4 and report a success to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 4})
            metrics.vrf_build_success()
        else:
            logger.error(
                f'VRF #{vrf_id} failed to build so it is being moved to Unresourced (3). Check log for details.',
            )
            # Change the state to 3 and report a failure to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
            metrics.vrf_build_failure()

    def quiesce(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, it and requests to quiesce the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.quiesce')
        vrf_id = vrf['idVRF']
        logger.info(f'Commencing quiesce dispatch of VRF #{vrf_id}')
        # OOB IP
        vrf['oob_ip'] = ro.service_entity_read('IAAS', 'router', vrf['idRouter'])['ipManagement']
        # Attempt to quiesce the VRF
        if Quiescer.quiesce(vrf, self.password):
            logger.info(f'Successfully quiesced VRF #{vrf_id} in router {vrf["idRouter"]}')
            # Change the state of the VRF to Quiesced (6) and report a success to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 6})
            metrics.vrf_quiesce_success()
        else:
            logger.error(
                f'VRF #{vrf_id} failed to quiesce. Check log for details.',
            )
            metrics.vrf_quiesce_failure()

    def scrub(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, it and requests to scrub the Vrf
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.scrub')
        vrf_id = vrf['idVRF']
        logger.info(f'Commencing scrub dispatch of VRF #{vrf_id}')
        # OOB IP
        vrf['oob_ip'] = ro.service_entity_read('IAAS', 'router', vrf['idRouter'])['ipManagement']
        # Attempt to scrub the VRF
        if Scubber.scrub(vrf, self.password):
            logger.info(f'Successfully scrubbed VRF #{vrf_id} in router {vrf["idRouter"]}')
            # Change the state of the VRF to 9(Deleted) and report a success to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 9})
            metrics.vrf_scrub_success()
        else:
            logger.error(
                f'VRF #{vrf_id} failed to scrub. Check log for details.',
            )
            metrics.vrf_scrub_failure()
