"""
builder class for vrs

- gathers template data
- generates setconf
- deploys setconf to the chosen router
"""

# stdlib
import logging
import re
from collections import deque
from typing import Any, Deque, Dict, Optional
# lib
import opentracing
from cloudcix.api.compute import Compute
from cloudcix.api.ipam import IPAM
from jaeger_client import Span
from netaddr import IPAddress, IPNetwork
# local
import utils
from mixins import VrMixin
from settings import PRIVATE_PORT, PUBLIC_PORT

__all__ = [
    'Vr',
]

ADDRESS_NAME_SUB_PATTERN = re.compile(r'[\.\/:]')


class Vr(VrMixin):
    """
    Class that handles the building of the specified VR
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.vr')
    # Keep track of the keys necessary for the template, so we can check all keys are present before building
    template_keys = {
        # A list of firewall rules to be built in the VR
        'firewall_rules',
        # if inbound firewall exists or not
        'inbound_firewall',
        # The IP Address of the Management port of the physical Router
        'management_ip',
        # A list of NAT rules to be built in the VR
        'nats',
        # if outbound firewall exists or not
        'outbound_firewall',
        # The private port of the firewall
        'private_port',
        # The id of the Project that owns the VR being built
        'project_id',
        # The public port of the Router
        'public_port',
        # A list of vLans to be built in the VR
        'vlans',
        # A list of VPNs to be built in the VR
        'vpns',
        # The IP Address of the VR
        'vr_ip',
        # The VR IP Subnet Mask, which is needed when making the VR
        'vr_subnet_mask',
        # The vxLan to use for the project (the project's address id)
        'vxlan',
    }

    @staticmethod
    def build(vr_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the build of a vr using the data read from the API
        :param vr_data: The result of a read request for the specified VR
        :param span: The tracing span in use for this build task
        :return: A flag stating whether or not the build was successful
        """
        vr_id = vr_data['id']

        # Start by generating the proper dict of data needed by the template
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Vr._get_template_data(vr_data, child_span)
        child_span.finish()

        # Check that the template data was successfully retrieved
        if template_data is None:
            Vr.logger.error(
                f'Failed to retrieve template data for VR #{vr_data["idVR"]}.',
            )
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Vr.template_keys):
            missing_keys = [
                f'"{key}"' for key in Vr.template_keys if template_data[key] is None
            ]
            Vr.logger.error(
                f'Template Data Error, the following keys were missing from the VR build data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence building the VR
        child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
        conf = utils.JINJA_ENV.get_template('vr/build.j2').render(**template_data)
        child_span.finish()

        Vr.logger.debug(f'Generated setconf for VR #{vr_id}\n{conf}')

        # Deploy the generated setconf to the router
        management_ip = template_data.pop('management_ip')
        child_span = opentracing.tracer.start_span('deploy_setconf', child_of=span)
        success = Vr.deploy(conf, management_ip)
        child_span.finish()
        return success

    @staticmethod
    def _get_template_data(vr_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vr data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vr_data: The data on the vr that was retrieved from the API
        :param span: The tracing span in use for this task. In this method just pass it to API calls
        :returns: Constructed template data, or None if something went wrong
        """
        vr_id = vr_data['id']
        Vr.logger.debug(f'Compiling template data for VR #{vr_id}')
        data: Dict[str, Any] = {key: None for key in Vr.template_keys}

        data['project_id'] = project_id = vr_data['project']['id']
        data['vxlan'] = vr_data['project']['address_id']
        # Gather the IP Address and Subnet Mask for the VR
        data['vr_ip'] = vr_data['ip_address']['address']
        data['vr_subnet_mask'] = vr_data['ip_address']['subnet']['address_range'].split('/')[1]

        # Get the vlans and nat rules for the VR
        vlans: Deque[Dict[str, str]] = deque()
        nats: Deque[Dict[str, str]] = deque()

        subnets = vr_data['subnets']
        # Add the vlan information to the deque
        for subnet in subnets:
            vlans.append({
                'address_family': 'inet6' if IPNetwork(subnet['address_range']).version == 6 else 'inet',
                'address_range': subnet['address_range'],
                'vlan': subnet['vlan'],
            })
        data['vlans'] = vlans

        # Check if there are any NAT rules needed in this subnet
        params = {'subnet_id__in': [subnet['id'] for subnet in subnets]}
        child_span = opentracing.tracer.start_span('listing_ip_addresses', child_of=span)
        subnet_ips = utils.api_list(IPAM.ip_address, params, span=child_span)
        child_span.finish()
        for ip in subnet_ips:
            if len(ip['private_ip']) != 0 and len(ip['public_ip']) != 0:
                nats.append({
                    'private_address': ip['private_ip']['address'],
                    'public_address': ip['public_ip']['address'],
                    'vlan': ip['private_ip']['subnet']['vlan'],
                })
        data['nats'] = nats

        # Get the management ip address which is IPv6 and Gateway as name of Router ips
        management_ip = None
        child_span = opentracing.tracer.start_span('reading_router', child_of=span)
        router = utils.api_read(Compute.router, vr_data['router_id'], span=child_span)
        child_span.finish()
        if 'ip_addresses' not in router.keys():
            Vr.logger.error(
                f'Invalid router data fot the Router # {router["id"]}',
            )
            return None
        for ip in router['ip_addresses']:
            if IPAddress(ip['address']).version == 6 and ip['name'] == 'Gateway':
                management_ip = ip['address']
                break
        if management_ip is None:
            Vr.logger.error(
                f'Mangement ip address not found for the Router # {router["id"]}',
            )
            return None
        data['management_ip'] = management_ip

        # Router port information
        data['private_port'] = PRIVATE_PORT
        data['public_port'] = PUBLIC_PORT

        # Firewall rules
        data['inbound_firewall'] = False
        data['outbound_firewall'] = False
        firewalls: Deque[Dict[str, Any]] = deque()
        vr_address_book_name = f'vrf-{project_id}-address-book'
        vr_zone_name = f'vrf-{project_id}'
        for firewall in sorted(vr_data['firewall_rules'], key=lambda fw: fw['order']):
            # Add the names of the source and destination addresses by replacing IP characters with hyphens
            firewall['source_address_name'] = ADDRESS_NAME_SUB_PATTERN.sub('-', firewall['source'])
            firewall['destination_address_name'] = ADDRESS_NAME_SUB_PATTERN.sub('-', firewall['destination'])

            inbound: bool = IPNetwork(firewall['source']).is_private()
            # Handle the inbound / outbound case stuff
            if inbound:
                # Source is public, destination is private
                firewall['source_address_book'] = 'global'
                firewall['destination_address_book'] = vr_address_book_name
                firewall['scope'] = 'inbound'
                firewall['from_zone'] = 'PUBLIC'
                firewall['to_zone'] = vr_zone_name
                data['inbound_firewall'] = True
            else:
                # Source is private, destination is public
                firewall['source_address_book'] = vr_address_book_name
                firewall['destination_address_book'] = 'global'
                firewall['scope'] = 'outbound'
                firewall['from_zone'] = vr_zone_name
                firewall['to_zone'] = 'PUBLIC'
                data['outbound_firewall'] = True

            # Determine what permission string to include in the firewall rule
            firewall['permission'] = 'permit' if firewall['allow'] else 'deny'

            # Check port and protocol to allow any port for a specific protocol
            if firewall['port'] == '-1' and firewall['protocol'] != 'any':
                firewall['port'] = '0-65535'

            firewalls.append(firewall)

        data['firewall_rules'] = firewalls

        # Finally, get the VPNs for the Project
        vpns: Deque[Dict[str, Any]] = deque()
        params = {'virtual_router_id': vr_id}
        child_span = opentracing.tracer.start_span('listing_vpns', child_of=span)
        vr_vpns = utils.api_list(Compute.vpn, params, span=child_span)
        child_span.finish()
        for vpn in vr_vpns:
            vpn['cloud_proxy_id'] = str(IPNetwork(vpn['cloud_subnet']['address_range']).cidr)
            vpn['customer_proxy_id'] = str(IPNetwork(vpn['customer_subnets'][0]).cidr)
            vpn['customer_subnets'] = [str(IPNetwork(cus_subnet).cidr) for cus_subnet in vpn['customer_subnets']]
            vpn['vlan'] = vpn['cloud_subnet']['vlan']
            # if send_email is true then read VPN for email addresses
            if vpn['send_email']:
                child_span = opentracing.tracer.start_span('reading_vpn', child_of=span)
                vpn['emails'] = utils.api_read(Compute.vpn, pk=vpn['id'])['email']
                child_span.finish()
            vpns.append(vpn)
        data['vpns'] = vpns

        # Store necessary data back in vr data for the email
        vr_data['vr_ip'] = data['vr_ip']
        vr_data['vlans'] = data['vlans']
        vr_data['vpns'] = data['vpns']

        return data
