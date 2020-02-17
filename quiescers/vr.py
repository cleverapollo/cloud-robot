"""
quiescer class for vrs

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
from mixins import VrMixin

__all__ = [
    'Vr',
]


class Vr(VrMixin):
    """
    Class that handles the quiescing of the specified VR
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.quiescers.vr')
    # Keep track of the keys necessary for the template, so we can check all keys are present before quiescing
    template_keys = {
        # The IP Address of the Management port of the physical Router
        'management_ip',
        # The id of the Project that owns the VR being quiesced
        'project_id',
    }

    @staticmethod
    def quiesce(vr_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the quiesce of a vr using the data read from the API
        :param vr_data: The result of a read request for the specified VR
        :param span: The tracing span in use for this quiesce task
        :return: A flag stating whether or not the quiesce was successful
        """
        vr_id = vr_data['id']

        # Start by generating the proper dict of data needed by the template
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Vr._get_template_data(vr_data, child_span)
        child_span.finish()

        # Check that the template data was successfully retrieved
        if template_data is None:
            Vr.logger.error(
                f'Failed to retrieve template data for VR #{vr_id}.',
            )
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Vr.template_keys):
            missing_keys = [
                f'"{key}"' for key in Vr.template_keys if template_data[key] is None
            ]
            Vr.logger.error(
                f'Template Data Error, the following keys were missing from the VR quiesce data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence quiescing the VR
        child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
        conf = utils.JINJA_ENV.get_template('vr/quiesce.j2').render(**template_data)
        child_span.finish()

        Vr.logger.debug(f'Generated setconf for VR #{vr_id}\n{conf}')

        # Deploy the generated setconf to the router
        management_ip = template_data.pop('management_ip')
        child_span = opentracing.tracer.start_span('deploy_setconf', child_of=span)
        success = Vr.deploy(conf, management_ip, True)
        child_span.finish()
        return success

    @staticmethod
    def _get_template_data(vr_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vr data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the quiesce method and not here, this method is only concerned with fetching the
        data that it can.
        :param vr_data: The data on the vr that was retrieved from the API
        :param span: The tracing span in use for this task. In this method just pass it to API calls
        :returns: Constructed template data, or None if something went wrong
        """
        vr_id = vr_data['id']
        Vr.logger.debug(f'Compiling template data for VR #{vr_id}')
        data: Dict[str, Any] = {key: None for key in Vr.template_keys}

        data['project_id'] = vr_data['project']['id']

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

        return data
