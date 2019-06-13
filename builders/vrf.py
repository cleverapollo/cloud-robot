"""
builder class for vrfs

- gathers template data
- generates setconf
- deploys setconf to the chosen router
"""

# stdlib
import logging
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


class Vrf(VrfMixin):
    """
    Class that handles the building of the specified VRF
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.vrf')
    # Keep track of the keys necessary for the template, so we can check all keys are present before building
    template_keys = {
        # A flag stating whether or not there is a firewall for the project
        'has_firewall',
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
        # The model name of the physical router. Needed to specify the template to build with.
        'router_model',
        # A list of vLans to be built in the VRF
        'vlans',
        # A list of VPNs to be built in the VRF
        'vpns',
        # The IP Address of the VRF
        'vrf_ip',
        # The VRF IP Subnet Mask, which is needed when making the VRF
        'vrf_subnet_mask',
        # The vxLan to use for the project (the project's address id)
        'vxlan',
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
        router_model = template_data.pop('router_model')
        management_ip = template_data.pop('management_ip')
        try:
            child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
            template_name = f'vrf/build_{router_model}.j2'
            child_span.set_tag('template_name', template_name)
            conf = utils.JINJA_ENV.get_template(template_name).render(**template_data)
            child_span.finish()
        except Exception:
            Vrf.logger.error(
                f'Unable to find the build template for {router_model} Routers',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'invalid_template_name')
            return False
        Vrf.logger.debug(f'Generated setconf for VRF #{vrf_id}\n{conf}')

        # Deploy the generated setconf to the router
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

        # Get the management ip address and the router model
        # These are used to determine the template to use and where to connect
        child_span = opentracing.tracer.start_span('get_router_data', child_of=span)
        router_data = Vrf._get_router_data(vrf_data['idRouter'], child_span)
        child_span.finish()

        if router_data is None:
            return None
        data['management_ip'] = router_data['management_ip']
        data['router_model'] = router_data['router_model']

        # Get the port data for the VRF
        child_span = opentracing.tracer.start_span('get_vrf_port_data', child_of=span)
        port_data = Vrf._get_vrf_port_data(vrf_ip['idSubnet'], vrf_data['idRouter'], child_span)
        child_span.finish()

        if port_data is None:
            # The function will have done the logging so we should be okay to just return
            return None
        data['port_address_family'] = port_data['address_family']
        data['has_firewall'] = port_data['has_firewall']
        data['private_port'] = port_data['private_port']
        data['public_port'] = port_data['public_port']

        # Finally, get the VPNs for the Project
        vpns: Deque[Dict[str, Any]] = deque()
        for vpn in utils.api_list(IAAS.vpn_tunnel, {'vrf': vrf_id}, span=span):
            vpn_data = {
                'vlan': '',
                'site_to_site': vpn['siteToSite'],
                'ike': '',
                'pre_shared_key': vpn['preSharedKey'],
                'remote_ip_address': vpn['ipRemoteAddress'],
                'ipsec': '',
                'remote_subnet': '',
            }
            # Gather the required data for the vpns
            # Fetch the subnet
            subnet = utils.api_read(IAAS.subnet, vpn['vpnLocalSubnet'], span=span)
            vpn_data['vlan'] = subnet['vLAN']
            vpn_data['remote_subnet'] = IPNetwork(
                f'{vpn["vpnRemoteSubnetIP"]}/{vpn["vpnRemoteSubnetMask"]}',
            ).cidr
            # Fetch the IKE name
            ike = utils.api_read(IAAS.ike, vpn['ike_id'], span=span)
            if ike is None:
                return None
            vpn['ike'] = ike['name']
            # Fetch the IPSec Name
            ipsec = utils.api_read(IAAS.ipsec, vpn['ipsec_id'], span=span)
            if ipsec is None:
                return None
            vpn['ipsec'] = ipsec['name']
            vpns.append(vpn)
        data['vpns'] = vpns

        return data
