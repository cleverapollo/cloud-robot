"""
restarter class for virtual_routers

- gathers template data
- generates setconf
- deploys setconf to the chosen router
"""

# stdlib
import logging
from typing import Any, Dict, Optional
# lib
import opentracing
from cloudcix.api.compute import Compute
from jaeger_client import Span
from netaddr import IPAddress
# local
import utils
from mixins import VirtualRouterMixin

__all__ = [
    'VirtualRouter',
]


class VirtualRouter(VirtualRouterMixin):
    """
    Class that handles the restarting of the specified virtual_router
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.restarters.virtual_router')
    # Keep track of the keys necessary for the template, so we can check all keys are present before restarting
    template_keys = {
        # The IP Address of the Management port of the physical Router
        'management_ip',
        # The id of the Project that owns the virtual_router being restarted
        'project_id',
    }

    @staticmethod
    def restart(virtual_router_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the restart of a virtual_router using the data read from the API
        :param virtual_router_data: The result of a read request for the specified virtual_router
        :param span: The tracing span in use for this restart task
        :return: A flag stating whether or not the restart was successful
        """
        virtual_router_id = virtual_router_data['id']

        # Start by generating the proper dict of data needed by the template
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = VirtualRouter._get_template_data(virtual_router_data, child_span)
        child_span.finish()

        # Check that the template data was successfully retrieved
        if template_data is None:
            VirtualRouter.logger.error(
                f'Failed to retrieve template data for virtual_router #{virtual_router_id}.',
            )
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in VirtualRouter.template_keys):
            missing_keys = [
                f'"{key}"' for key in VirtualRouter.template_keys if template_data[key] is None
            ]
            VirtualRouter.logger.error(
                f'Template Data Error, the following keys were missing from the virtual_router restart data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence restarting the virtual_router
        child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
        conf = utils.JINJA_ENV.get_template('virtual_router/restart.j2').render(**template_data)
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
        Given the virtual_router data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the restart method and not here, this method is only concerned with fetching the
        data that it can.
        :param virtual_router_data: The data on the virtual_router that was retrieved from the API
        :param span: The tracing span in use for this task. In this method just pass it to API calls
        :returns: Constructed template data, or None if something went wrong
        """
        virtual_router_id = virtual_router_data['id']
        VirtualRouter.logger.debug(f'Compiling template data for virtual_router #{virtual_router_id}')
        data: Dict[str, Any] = {key: None for key in VirtualRouter.template_keys}

        data['project_id'] = virtual_router_data['project']['id']

        # Get the management ip address which is IPv6 and Gateway as name of Router ips
        management_ip = None
        child_span = opentracing.tracer.start_span('reading_router', child_of=span)
        router = utils.api_read(Compute.router, virtual_router_data['router_id'], span=child_span)
        child_span.finish()
        if 'ip_addresses' not in router.keys():
            VirtualRouter.logger.error(
                f'Invalid router data fot the Router # {router["id"]}',
            )
            return None
        for ip in router['ip_addresses']:
            if IPAddress(ip['address']).version == 6 and ip['name'] == 'Gateway':
                management_ip = ip['address']
                break
        if management_ip is None:
            VirtualRouter.logger.error(
                f'Mangement ip address not found for the Router # {router["id"]}',
            )
            return None
        data['management_ip'] = management_ip

        return data
