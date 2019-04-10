# python
import netaddr
from collections import deque
# locals
import metrics
import ro
import utils
from builders import Vrf as Builder
from net_builders import is_valid_vlan
from quiescers import Vrf as Quiescer
from restarters import Vrf as Restarter
from scrubbers import Vrf as Scubber
from updaters import Vrf as Updater


class Vrf:
    """
    A class that handles 'dispatching' a VRF to various services such as builders, scrubbers, etc.
    """

    # Network password used to login to the routers
    password: str

    def __init__(self, password: str):
        self.password = password

    @staticmethod
    def ntw_address(address_range, type_ip):
        """
        it will set the address range to first ip ie if address range is 10.1.0.0/24
        then the out put will be 10.1.0.1/24
        :param address_range: ip address network (ipv4/ipv6)
        :param type_ip: string of either 'inet' or 'inet6'
        :return: string of network address
        """
        ip_addr = str(address_range).split('/')
        # split the ip
        if type_ip == 'inet':
            li = ip_addr[0].split('.')
        elif type_ip == 'inet6':
            li = ip_addr[0].split(':')
        # set the octet to 1 if it is 0
        if li[-1] == '0':
            li[-1] = '1'
        # rearrange subnet
        if type_ip == 'inet':
            ntw_addr = '.'.join(f'{i}' for i in li)
        elif type_ip == 'inet6':
            ntw_addr = ':'.join(f'{i}' for i in li)
        return str(netaddr.IPNetwork(f'{ntw_addr}/{ip_addr[1]}'))

    def router_data(self, router_id):
        manage_ip = None
        router_model = None
        ports = ro.service_entity_list('IAAS', 'port', {}, router_id=router_id)
        for port in ports:
            # Get the Port names ie xe-0/0/0 etc
            rmpf = ro.service_entity_read(
                'IAAS',
                'router_model_port_function',
                pk=port['model_port_id'],
            )
            # Get the router model
            router_model = ro.service_entity_read(
                'IAAS',
                'router_model',
                pk=rmpf['router_model_id'],
            )['model']
            # Get the function names ie 'Management' etc
            port_fun = ro.service_entity_read(
                'IAAS',
                'port_function',
                pk=rmpf['port_function_id'],
            )
            if port_fun['function'] == 'Management':
                port_configs = ro.service_entity_list(
                    'IAAS',
                    'port_config',
                    {},
                    port_id=port['port_id'],
                )
                for port_config in port_configs:
                    # Get the ip address details
                    ip = ro.service_entity_read(
                        'IAAS',
                        'ipaddress',
                        pk=port_config['port_ip_id'],
                    )
                    manage_ip = ip['address']
                    break
                break
        return {'manage_ip': manage_ip, 'router_model': router_model}

    @staticmethod
    def ip_type(ip):
        """
        it finds out ip is v4 or v6 and returns 'inet' for v4 and 'inet6' for v6
        :param ip:  generic ip address
        :return ty: string
        """
        # find the ip type
        response = ro.api.IAAS.ip_validator.list(
            token=ro.TOKEN_WRAPPER.token,
            params={'ipAddresses': ip},
        )
        result = response.json()['ipAddresses'][ip]['result']
        ty = 'inet'
        if result['ipv4']:
            ty = 'inet'
        elif result['ipv6']:
            ty = 'inet6'
        return ty

    def get_vrf_port(self, vrf_ip_subnet_id, router_id):
        """
        It takes vrf ip to find out whether IP belongs to Floating or Floating Pre Filtered so that
        vrf will be configured on the port corresponding to its nature using router
        :param vrf_ip_subnet_id :type int subnet id of vrf ip
        :param router_id:
        :return: vrf_port: dict of vrf port details like Port name (xe-0/0/1 or ge-0/0/1 or etc)
        and under firewall or not
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.get_vrf_port')
        firewall = False
        interface = None
        private = None
        ty = None
        vrf_port = dict()
        # Get the Ports which are Floating and Floating Pre Filtered of Router
        ports = ro.service_entity_list('IAAS', 'port', {}, router_id=router_id)
        for port in ports:
            # Get the Port names ie xe-0/0/0 etc
            rmpf = ro.service_entity_read(
                'IAAS',
                'router_model_port_function',
                pk=port['model_port_id'],
            )
            # Get the function names ie 'Management' etc
            port_fun = ro.service_entity_read(
                'IAAS',
                'port_function',
                pk=rmpf['port_function_id'],
            )
            if port_fun['function'] == 'Private':
                private = rmpf['port_name']
            if port_fun['function'] == 'Floating Pre Filtered':
                port_configs = ro.service_entity_list(
                    'IAAS',
                    'port_config',
                    {},
                    port_id=port['port_id'],
                )
                for port_config in port_configs:
                    # Get the ip address details
                    ip = ro.service_entity_read(
                        'IAAS',
                        'ipaddress',
                        pk=port_config['port_ip_id'],
                    )
                    if str(ip['idSubnet']) == str(vrf_ip_subnet_id):
                        firewall = True
                        interface = rmpf['port_name']
                        ty = self.ip_type(ip['address'])
                        break
            if firewall and interface and private:
                break  # just exit for loop as we got required data
            if port_fun['function'] == 'Floating':
                port_configs = ro.service_entity_list(
                    'IAAS',
                    'port_config',
                    {},
                    port_id=port['port_id'],
                )
                for port_config in port_configs:
                    # Get the ip address details
                    ip = ro.service_entity_read(
                        'IAAS',
                        'ipaddress',
                        pk=port_config['port_ip_id'],
                    )
                    if str(ip['idSubnet']) == str(vrf_ip_subnet_id):
                        firewall = False
                        interface = rmpf['port_name']
                        ty = self.ip_type(ip['address'])
                        break
            if not firewall and interface and private:
                break  # just exit for loop as we got required data
        if interface and private:
            vrf_port = {
                'public_port': interface,
                'type': ty,
                'private_port': private,
                'firewall': firewall,
            }
        else:
            logger.error(
                f'Failed to get Vrf port details for given Router_id #{router_id} ',
                f'and vrf_ip_subnet_id #{vrf_ip_subnet_id}'
                f'Check log for details.',
            )
        return vrf_port

    def build(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for building it and requests to build it
        in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.build')
        vrf_id = vrf['idVRF']
        logger.info(f'Commencing build dispatch of VRF #{vrf_id}')
        # Read the project to get the customer idAddress for vxlan
        vrf['vxlan'] = ro.service_entity_read('IAAS', 'project', vrf['idProject'])['idAddCust']

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
                metrics.vrf_build_failure()
                return

            subnet_type = self.ip_type(str(subnet['addressRange']).split('/')[0])
            first_address_range = self.ntw_address(subnet['addressRange'], subnet_type)
            vlans.append(
                {
                    'vlan': subnet['vLAN'],
                    'address_range': first_address_range,
                    'type': subnet_type,
                },
            )

            # Check if there are any nats for this subnet
            params = {'subnet__idSubnet': subnet['idSubnet'], 'fip_id__isnull': False, 'fields': '(*,fip)'}
            for ip in ro.service_entity_list('IAAS', 'ipaddress', params):
                nats.append({'private': ip['address'], 'public': ip['fip']['address'], 'vlan': subnet['vLAN']})

        # vrf_ip and maskVPN
        vrf_ip = ro.service_entity_read('IAAS', 'ipaddress', pk=vrf['idIPVrf'])
        vrf_ip_subnet = ro.service_entity_read('IAAS', 'subnet', pk=vrf_ip['idSubnet'])
        vrf['vrf_ip'] = vrf_ip['address']
        vrf['mask_vpn'] = vrf_ip_subnet['addressRange'].split('/')[1]

        # Management IP and Router Model
        data_router = self.router_data(vrf['idRouter'])
        vrf['manage_ip'] = data_router['manage_ip']
        vrf['router_model'] = data_router['router_model']

        # vrf_port data
        vrf['port_data'] = self.get_vrf_port(vrf_ip['idSubnet'], vrf['idRouter'])

        # VPNs
        for vpn in ro.service_entity_list('IAAS', 'vpn_tunnel', {'vrf': vrf_id}):
            # check router compatability with RemoteAccess(siteToSite = False) typed vpn
            if vrf['router_model'] == 'J6350' and vpn['siteToSite'] is False:
                logger.error(
                    f'VRF #{vrf_id} failed to create as VPN #{vpn["idVPNTunnel"]} is incompatable with router '
                    f'so it is being moved to Unresourced (3)',
                )
                # Change the state to 3 and report a failure to influx
                ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
                metrics.vrf_build_failure()
                return
            # gather required data
            subnet = ro.service_entity_read('IAAS', 'subnet', vpn['vpnLocalSubnet'])
            vpn['vlan'] = subnet['vLAN']
            vpn['remote_subnet_cidr'] = netaddr.IPNetwork(
                f'{vpn["vpnRemoteSubnetIP"]}/{vpn["vpnRemoteSubnetMask"]}',
            ).cidr
            vpn['ike'] = ro.service_entity_read('IAAS', 'ike', pk=vpn['ike_id'])['name']
            vpn['ipsec'] = ro.service_entity_read('IAAS', 'ipsec', pk=vpn['ipsec_id'])['name']
            vpns.append(vpn)

        # adding vlans, nats and vpns to vrf
        vrf['vlans'] = vlans
        vrf['nats'] = nats
        vrf['vpns'] = vpns

        # TODO - Add data/ip validations to vrf dispatcher

        # Change the state of the vrf to be 'Building' (2)
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 2})
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
        # Mangement IP
        vrf['manage_ip'] = self.router_data(vrf['idRouter'])['manage_ip']
        # Attempt to quiesce the VRF
        if Quiescer.quiesce(vrf, self.password):
            logger.info(f'Successfully quiesced VRF #{vrf_id} in router {vrf["idRouter"]}')
            # Change the state of the VRF to:
            #  1. Quiesced (6) if the existing state is Quiescing (5)
            #  2. Deleted (9) if the existing state is Scheduled for Deletion (8)
            # And log a success in Influx
            if vrf['state'] == 5:
                ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 6})
            if vrf['state'] == 8:
                ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 9})
            metrics.vrf_quiesce_success()
        else:
            logger.error(
                f'VRF #{vrf_id} failed to quiesce. Check log for details.',
            )
            metrics.vrf_quiesce_failure()

    def restart(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for restarting it and
        requests to restart the Vrf in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.restart')
        vrf_id = vrf['idVRF']
        logger.info(f'Commencing restart dispatch of VRF #{vrf_id}')
        # Management IP
        vrf['manage_ip'] = self.router_data(vrf['idRouter'])['manage_ip']
        # Attempt to restart the VRF
        if Restarter.restart(vrf, self.password):
            logger.info(f'Successfully restarted VRF #{vrf_id} in router {vrf["idRouter"]}')
            # Change the state of the VRF to 4(build) and report a success to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 4})
            metrics.vrf_restart_success()
        else:
            logger.error(
                f'VRF #{vrf_id} failed to restart. Check log for details.',
            )
            metrics.vrf_restart_failure()

    def scrub(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for scrubbing it and
        requests to scrub the Vrf in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.scrub')
        vrf_id = vrf['idVRF']
        logger.info(f'Commencing scrub dispatch of VRF #{vrf_id}')
        # Management IP
        vrf['manage_ip'] = self.router_data(vrf['idRouter'])['manage_ip']
        # Attempt to scrub the VRF
        if Scubber.scrub(vrf, self.password):
            logger.info(f'Successfully scrubbed VRF #{vrf_id} in router {vrf["idRouter"]}')
            metrics.vrf_scrub_success()
            # Delete the VRF from the DB
            if ro.service_entity_delete('IAAS', 'vrf', vrf_id):
                logger.info(f'VRF #{vrf_id} successfully deleted from the API')
            else:
                logger.error(f'VRF #{vrf_id} API deletion failed. Check log for details')
        else:
            logger.error(
                f'VRF #{vrf_id} failed to scrub. Check log for details.',
            )
            metrics.vrf_scrub_failure()

    def update(self, vrf: dict):
        """
        Takes VRF data from the CloudCIX API, adds any additional data needed for updating it and
        requests to update the Vrf in the assigned physical Router.
        :param vrf: The VRF data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vrf.update')
        vrf_id = vrf['idVRF']
        logger.info(f'Commencing update dispatch of VRF #{vrf_id}')
        # Change the state of the vrf to be 'Updating' (11)
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 11})

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

            subnet_type = self.ip_type(str(subnet['addressRange']).split('/')[0])
            first_address_range = self.ntw_address(subnet['addressRange'], subnet_type)
            vlans.append(
                {
                    'vlan': subnet['vLAN'],
                    'address_range': first_address_range,
                    'type': subnet_type,
                },
            )

            # Check if there are any nats for this subnet
            params = {'subnet__idSubnet': subnet['idSubnet'], 'fip_id__isnull': False, 'fields': '(*,fip)'}
            for ip in ro.service_entity_list('IAAS', 'ipaddress', params):
                nats.append({'private': ip['address'], 'public': ip['fip']['address']})

        # vrf_ip and maskVPN
        vrf_ip = ro.service_entity_read('IAAS', 'ipaddress', pk=vrf['idIPVrf'])
        vrf_ip_subnet = ro.service_entity_read('IAAS', 'subnet', pk=vrf_ip['idSubnet'])
        vrf['vrf_ip'] = vrf_ip['address']
        vrf['mask_vpn'] = vrf_ip_subnet['addressRange'].split('/')[1]

        # Management IP and Router Model
        data_router = self.router_data(vrf['idRouter'])
        vrf['manage_ip'] = data_router['manage_ip']
        vrf['router_model'] = data_router['router_model']

        # vrf_port data
        vrf['port_data'] = self.get_vrf_port(vrf_ip['idSubnet'], vrf['idRouter'])

        # VPNs
        for vpn in ro.service_entity_list('IAAS', 'vpn_tunnel', {'vrf': vrf_id}):
            # check router compatability with RemoteAccess(siteTosite = False) typed vpn
            if vrf['router_model'] == 'J6350' and vpn['siteToSite'] is False:
                logger.error(
                    f'VRF #{vrf_id} failed to update as VPN #{vpn["idVPNTunnel"]} is incompatable with router '
                    f'so it is being moved to Unresourced (3)',
                )
                # Change the state to 3 and report a failure to influx
                ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
                metrics.vrf_update_failure()
                return
            # gather required data
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

        # TODO - Add data/ip validations to vrf dispatcher

        # Attempt to re-build the VRF
        ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 2})
        if Updater.update(vrf, self.password):
            logger.info(f'Successfully updated VRF #{vrf_id} in router {vrf["idRouter"]}')
            # Change the state to 4 and report a success to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 4})
            metrics.vrf_update_success()
        else:
            logger.error(
                f'VRF #{vrf_id} failed to update so it is being moved to Unresourced (3). Check log for details.',
            )
            # Change the state to 3 and report a failure to influx
            ro.service_entity_update('IAAS', 'vrf', vrf_id, {'state': 3})
            metrics.vrf_update_failure()
