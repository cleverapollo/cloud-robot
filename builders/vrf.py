"""
builder class for vrfs

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
from cloudcix.api import IAAS
from jaeger_client import Span
from netaddr import IPNetwork
# local
import utils
from mixins import VrfMixin

__all__ = [
    'Vrf',
]

ADDRESS_NAME_SUB_PATTERN = re.compile(r'[\.\/:]')


class Vrf(VrfMixin):
    """
    Class that handles the building of the specified VRF
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.vrf')
    # Keep track of the keys necessary for the template, so we can check all keys are present before building
    template_keys = {
        # The IP Address of the Management port of the physical Router
        'management_ip',
        # A list of NAT rules to be built in the VRF
        'nats',
        # The address family for the firewall port
        'port_address_family',
        # The private port of the firewall
        'private_port',
        # The id of the Project that owns the VRF being built
        'project_id',
        # The public port of the Router
        'public_port',
        # A list of vLans to be built in the VRF
        'vlans',
        # A list of VPNs to be built in the VRF
        'vpns',
        # A list of firewall rules to be built in the VRF
        'firewall_rules',
        # if inbound firewall exists or not
        'inbound_firewall',
        # if outbound firewall exists or not
        'outbound_firewall',
        # The IP Address of the VRF
        'vrf_ip',
        # The VRF IP Subnet Mask, which is needed when making the VRF
        'vrf_subnet_mask',
        # The vxLan to use for the project (the project's address id)
        'vxlan',
        # RoboSOC firewalls enabled only for inbound rule with source-address is 'any'
        'robosoc',
    }

    @staticmethod
    def build(vrf_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the build of a vrf using the data read from the API
        :param vrf_data: The result of a read request for the specified VRF
        :param span: The tracing span in use for this build task
        :return: A flag stating whether or not the build was successful
        """
        vrf_id = vrf_data['idVRF']

        # Start by generating the proper dict of data needed by the template
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Vrf._get_template_data(vrf_data, child_span)
        child_span.finish()

        # Check that the template data was successfully retrieved
        if template_data is None:
            Vrf.logger.error(
                f'Failed to retrieve template data for VRF #{vrf_data["idVRF"]}.',
            )
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Vrf.template_keys):
            missing_keys = [
                f'"{key}"' for key in Vrf.template_keys if template_data[key] is None
            ]
            Vrf.logger.error(
                f'Template Data Error, the following keys were missing from the VRF build data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence building the VRF
        child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
        conf = utils.JINJA_ENV.get_template('vrf/build.j2').render(**template_data)
        child_span.finish()

        Vrf.logger.debug(f'Generated setconf for VRF #{vrf_id}\n{conf}')

        # Deploy the generated setconf to the router
        management_ip = template_data.pop('management_ip')
        child_span = opentracing.tracer.start_span('deploy_setconf', child_of=span)
        success = Vrf.deploy(conf, management_ip)
        child_span.finish()
        return success

    @staticmethod
    def _get_template_data(vrf_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vrf data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vrf_data: The data on the vrf that was retrieved from the API
        :param span: The tracing span in use for this task. In this method just pass it to API calls
        :returns: Constructed template data, or None if something went wrong
        """
        vrf_id = vrf_data['idVRF']
        Vrf.logger.debug(f'Compiling template data for VRF #{vrf_id}')
        data: Dict[str, Any] = {key: None for key in Vrf.template_keys}

        project_id = vrf_data['idProject']
        data['project_id'] = project_id

        # Read the project to get the customer idAddress for vxlan
        project = utils.api_read(IAAS.project, project_id, span=span)
        if project is None:
            # An error will have been logged by the utils function, so we can just exit
            return None
        data['vxlan'] = project['idAddCust']

        # Get the vlans and nat rules for the VRF
        vlans: Deque[Dict[str, str]] = deque()
        nats: Deque[Dict[str, str]] = deque()
        # Iterate through subnets for the vrf and check vlans and nat rules
        subnets = utils.api_list(IAAS.subnet, {'vrf': vrf_id}, span=span)
        for subnet in subnets:
            # Get the type of the subnet using netaddr
            subnet_address_family: str = 'inet'
            if IPNetwork(subnet['addressRange']).version == 6:
                subnet_address_family = 'inet6'

            # Add the vlan information to the deque
            vlans.append({
                'address_family': subnet_address_family,
                'address_range': subnet['addressRange'],
                'vlan': subnet['vLAN'],
            })

            # Check if there are any NAT rules needed in this subnet
            params = {
                'fields': '(*,fip)',
                'fip_id__isnull': False,
                'subnet__idSubnet': subnet['idSubnet'],
            }
            for ip in utils.api_list(IAAS.ipaddress, params, span=span):
                nats.append({
                    'private_address': ip['address'],
                    'public_address': ip['fip']['address'],
                    'vlan': subnet['vLAN'],
                })
        data['vlans'] = vlans
        data['nats'] = nats

        # Retrieve the IP Address and Subnet Mask for the VRF
        # Get the IP Address of the VRF
        vrf_ip = utils.api_read(IAAS.ipaddress, vrf_data['idIPVrf'], span=span)
        if vrf_ip is None:
            # The utils method will have logged an error
            return None
        # Get the Subnet for the VRF to get the subnet mask
        vrf_subnet = utils.api_read(IAAS.subnet, vrf_ip['idSubnet'], span=span)
        if vrf_subnet is None:
            # The utils method will have logged an error
            return None
        data['vrf_ip'] = vrf_ip['address']
        data['vrf_subnet_mask'] = vrf_subnet['addressRange'].split('/')[1]

        # Get the management ip address
        management_ip = Vrf._get_router_ip(vrf_data['idRouter'], span)
        if management_ip is None:
            # We can't unresource this, so just return
            return None
        data['management_ip'] = management_ip

        # Get the ports data to determine the vrf's interface and public interface
        child_span = opentracing.tracer.start_span('get_router_data', child_of=span)
        router_data = Vrf._get_router_data(vrf_data['idRouter'], vrf_ip['idSubnet'], child_span)
        child_span.finish()

        if router_data is None:
            return None
        data['port_address_family'] = router_data['address_family']
        data['private_port'] = router_data['private_port']
        data['public_port'] = router_data['public_port']

        data['robosoc'] = False

        # Firewall rules
        data['inbound_firewall'] = False
        data['outbound_firewall'] = False
        firewalls: Deque[Dict[str, Any]] = deque()
        vrf_address_book_name = f'vrf-{project_id}-address-book'
        vrf_zone_name = f'vrf-{project_id}'
        for firewall in sorted(vrf_data['firewall_rules'], key=lambda fw: fw['order']):
            # Add the names of the source and destination addresses by replacing IP characters with hyphens
            firewall['source_address_name'] = ADDRESS_NAME_SUB_PATTERN.sub('-', firewall['source'])
            firewall['destination_address_name'] = ADDRESS_NAME_SUB_PATTERN.sub('-', firewall['destination'])

            # Handle the inbound / outbound case stuff
            if firewall['inbound']:
                # Source is public, destination is private
                firewall['source_address_book'] = 'global'
                firewall['destination_address_book'] = vrf_address_book_name
                firewall['scope'] = 'inbound'
                firewall['from_zone'] = 'PUBLIC'
                firewall['to_zone'] = vrf_zone_name
                data['inbound_firewall'] = True
                if firewall['source'] == '0.0.0.0/0':
                    data['robosoc'] = True
            else:
                # Source is private, destination is public
                firewall['source_address_book'] = vrf_address_book_name
                firewall['destination_address_book'] = 'global'
                firewall['scope'] = 'outbound'
                firewall['from_zone'] = vrf_zone_name
                firewall['to_zone'] = 'PUBLIC'
                data['outbound_firewall'] = True

            # Determine what permission string to include in the firewall rule
            firewall['permission'] = 'permit' if firewall['allow'] else 'deny'

            # Check port and protocol to allow any port for a specific protocol
            if firewall['port'] == -1 and firewall['protocol'] != 'any':
                firewall['port'] = '0-65535'

            firewalls.append(firewall)

        data['firewall_rules'] = firewalls

        # Finally, get the VPNs for the Project
        vpns: Deque[Dict[str, Any]] = deque()
        for vpn in utils.api_list(IAAS.vpn_tunnel, {'vrf': vrf_id}, span=span):
            vpns.append(
                {
                    'vlan': vpn['vpnLocalSubnetDict']['vLAN'],
                    'local_subnet': IPNetwork(vpn['vpnLocalSubnetDict']['addressRange']).cidr,
                    'ike': vpn['ike'],
                    'ipsec': vpn['ipsec'],
                    'remote_subnet': IPNetwork(f'{vpn["vpnRemoteSubnetIP"]}/{vpn["vpnRemoteSubnetMask"]}').cidr,
                },
            )
        data['vpns'] = vpns

        # Store necessary data back in vrf data for the email
        vrf_data['vrf_ip'] = data['vrf_ip']
        vrf_data['vlans'] = data['vlans']
        vrf_data['vpns'] = data['vpns']

        return data
