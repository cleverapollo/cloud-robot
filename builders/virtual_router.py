"""
builder class for virtual_routers

- gathers template data
- generates setconf
- deploys setconf to the chosen router
"""

# stdlib
import logging
import re
from collections import deque
from typing import Any, Deque, Dict, List, Optional
# lib
import opentracing
from cloudcix.api.iaas import IAAS
from jaeger_client import Span
from netaddr import IPNetwork
# local
import utils
from mixins import VirtualRouterMixin

__all__ = [
    'VirtualRouter',
]

ADDRESS_NAME_SUB_PATTERN = re.compile(r'[\.\/:]')


class VirtualRouter(VirtualRouterMixin):
    """
    Class that handles the building of the specified virtual_router
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.virtual_router')
    # Keep track of the keys necessary for the template, so we can check all keys are present before building
    template_keys = {
        # A list of firewall rules to be built in the virtual_router
        'firewall_rules',
        # if inbound firewall exists or not
        'inbound_firewall',
        # The IP Address of the Management interface of the physical Router
        'management_ip',
        # A list of NAT rules to be built in the virtual_router
        'nats',
        # if outbound firewall exists or not
        'outbound_firewall',
        # The address family for the firewall port
        'interface_address_family',
        # The private interface of the firewall
        'private_interface',
        # The id of the Project that owns the virtual_router being built
        'project_id',
        # The public interface of the Router
        'public_interface',
        # A list of vLans to be built in the virtual_router
        'vlans',
        # A list of VPNs to be built in the virtual_router
        'vpns',
        # The IP Address of the virtual_router
        'virtual_router_ip',
        # The virtual_router IP Subnet Mask, which is needed when making the virtual_router
        'virtual_router_subnet_mask',
        # The vxLan to use for the project (the project's address id)
        'vxlan',
    }

    @staticmethod
    def build(virtual_router_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the build of a virtual_router using the data read from the API
        :param virtual_router_data: The result of a read request for the specified virtual_router
        :param span: The tracing span in use for this build task
        :return: A flag stating whether or not the build was successful
        """
        virtual_router_id = virtual_router_data['id']

        # Start by generating the proper dict of data needed by the template
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = VirtualRouter._get_template_data(virtual_router_data, child_span)
        child_span.finish()

        # Check that the template data was successfully retrieved
        if template_data is None:
            VirtualRouter.logger.error(
                f'Failed to retrieve template data for virtual router #{virtual_router_id}.',
            )
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in VirtualRouter.template_keys):
            missing_keys = [
                f'"{key}"' for key in VirtualRouter.template_keys if template_data[key] is None
            ]
            VirtualRouter.logger.error(
                f'Template Data Error, the following keys were missing from the virtual_router build data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence building the virtual_router
        child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
        conf = utils.JINJA_ENV.get_template('virtual_router/build.j2').render(**template_data)
        child_span.finish()

        VirtualRouter.logger.debug(f'Generated setconf for virtual_router #{virtual_router_id}\n{conf}')

        # Deploy the generated setconf to the router
        management_ip = template_data.pop('management_ip')
        child_span = opentracing.tracer.start_span('deploy_setconf', child_of=span)
        success = VirtualRouter.deploy(conf, management_ip)
        child_span.finish()
        return success

    @staticmethod
    def _get_template_data(virtual_router_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the virtual_router data from the API, create a dictionary that contains all of the necessary keys for the
        template.
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param virtual_router_data: The data on the virtual_router that was retrieved from the API
        :param span: The tracing span in use for this task. In this method just pass it to API calls
        :returns: Constructed template data, or None if something went wrong
        """
        virtual_router_id = virtual_router_data['id']
        VirtualRouter.logger.debug(f'Compiling template data for virtual_router #{virtual_router_id}')
        data: Dict[str, Any] = {key: None for key in VirtualRouter.template_keys}

        data['project_id'] = project_id = virtual_router_data['project']['id']
        data['vxlan'] = virtual_router_data['project']['address_id']
        # Gather the IP Address and Subnet Mask for the virtual_router
        data['virtual_router_ip'] = virtual_router_data['ip_address']['address']
        data['virtual_router_subnet_mask'] = virtual_router_data['ip_address']['subnet']['address_range'].split('/')[1]

        # Get the vlans and nat rules for the virtual_router
        vlans: Deque[Dict[str, str]] = deque()
        nats: Deque[Dict[str, str]] = deque()

        subnets = virtual_router_data['subnets']
        # Add the vlan information to the deque
        for subnet in subnets:
            vlans.append({
                'address_family': 'inet6' if IPNetwork(subnet['address_range']).version == 6 else 'inet',
                'address_range': subnet['address_range'],
                'vlan': subnet['vlan'],
            })
        data['vlans'] = vlans

        # Check if there are any NAT rules needed in this subnet
        params = {'search[subnet_id__in]': [subnet['id'] for subnet in subnets]}
        child_span = opentracing.tracer.start_span('listing_ip_addresses', child_of=span)
        subnet_ips = utils.api_list(IAAS.ip_address, params, span=child_span)
        child_span.finish()
        for ip in subnet_ips:
            if len(ip['public_ip']) != 0:
                nats.append({
                    'private_address': ip['address'],
                    'public_address': ip['public_ip']['address'],
                    'vlan': ip['subnet']['vlan'],
                })
        data['nats'] = nats

        # Get the management ip address from the Router.
        child_span = opentracing.tracer.start_span('reading_router', child_of=span)
        router = utils.api_read(IAAS.router, virtual_router_data['router_id'], span=child_span)
        child_span.finish()
        data['management_ip'] = router['management_ip']

        # Router interface information
        data['private_interface'] = router['private_interface']
        data['public_interface'] = router['public_interface']

        # Firewall rules
        data['inbound_firewall'] = False
        data['outbound_firewall'] = False
        firewalls: Deque[Dict[str, Any]] = deque()
        # 'vrf' name is necessary to maintain the existing virtual routers on routers
        virtual_router_zone_name = f'vrf-{project_id}'
        virtual_router_address_book_name = f'vrf-{project_id}-address-book'
        for firewall in sorted(virtual_router_data['firewall_rules'], key=lambda fw: fw['order']):
            # Add the names of the source and destination addresses by replacing IP characters with hyphens
            firewall['source_address_name'] = ADDRESS_NAME_SUB_PATTERN.sub('-', firewall['source'])
            firewall['destination_address_name'] = ADDRESS_NAME_SUB_PATTERN.sub('-', firewall['destination'])

            inbound: bool = IPNetwork(firewall['source']).is_private()
            # Handle the inbound / outbound case stuff
            if inbound:
                # Source is public, destination is private
                firewall['source_address_book'] = 'global'
                firewall['destination_address_book'] = virtual_router_address_book_name
                firewall['scope'] = 'inbound'
                firewall['from_zone'] = 'PUBLIC'
                firewall['to_zone'] = virtual_router_zone_name
                data['inbound_firewall'] = True
            else:
                # Source is private, destination is public
                firewall['source_address_book'] = virtual_router_address_book_name
                firewall['destination_address_book'] = 'global'
                firewall['scope'] = 'outbound'
                firewall['from_zone'] = virtual_router_zone_name
                firewall['to_zone'] = 'PUBLIC'
                data['outbound_firewall'] = True

            # Determine what permission string to include in the firewall rule
            firewall['permission'] = 'permit' if firewall['allow'] else 'deny'

            # logging
            firewall['log'] = True if firewall['pci_logging'] else firewall['debug_logging']

            # Check port and protocol to allow any port for a specific protocol
            if firewall['port'] == '-1' and firewall['protocol'] != 'any':
                firewall['port'] = '0-65535'

            firewalls.append(firewall)

        data['firewall_rules'] = firewalls

        # Finally, get the VPNs for the Project
        vpns: Deque[Dict[str, Any]] = deque()
        params = {'search[virtual_router_id]': virtual_router_id}
        child_span = opentracing.tracer.start_span('listing_vpns', child_of=span)
        virtual_router_vpns = utils.api_list(IAAS.vpn, params, span=child_span)
        child_span.finish()
        for vpn in virtual_router_vpns:
            customer_subnets: List[str] = []
            for customer_subnet in vpn['customer_subnets']:
                customer_subnets.append(IPNetwork(str(customer_subnet)).cidr)
            vpn['customer_subnets'] = customer_subnets
            vpn['local_proxy'] = IPNetwork(vpn['local_subnet']['address_range']).cidr
            vpn['remote_proxy'] = customer_subnets[0]
            vpns.append(vpn)

            # if send_email is true then read VPN for email addresses
            if vpn['send_email']:
                child_span = opentracing.tracer.start_span('reading_vpn', child_of=span)
                vpn['emails'] = utils.api_read(IAAS.vpn, pk=vpn['id'])['email']
                child_span.finish()
            vpns.append(vpn)
        data['vpns'] = vpns

        # Store necessary data back in virtual_router data for the email
        virtual_router_data['virtual_router_ip'] = data['virtual_router_ip']
        virtual_router_data['vlans'] = data['vlans']
        virtual_router_data['vpns'] = data['vpns']

        return data
