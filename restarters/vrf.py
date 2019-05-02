"""
restarter class for vrfs

- gathers template data
- generates setconf
- deploys setconf to the chosen router
"""

# stdlib
import logging
from typing import Any, Dict, Optional
# lib
from jaeger_client import Span
# local
import utils
from celery_app import tracer
from mixins import VrfMixin

__all__ = [
    'Vrf',
]


class Vrf(VrfMixin):
    """
    Class that handles the restarting of the specified VRF
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.restarters.vrf')
    # Keep track of the keys necessary for the template, so we can check all keys are present before restarting
    template_keys = {
        # The IP Address of the Management port of the physical Router
        'management_ip',
        # The id of the Project that owns the VRF being restarted
        'project_id',
    }

    @staticmethod
    def restart(vrf_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the restart of a vrf using the data read from the API
        :param vrf_data: The result of a read request for the specified VRF
        :param span: The tracing span in use for this restart task
        :return: A flag stating whether or not the restart was successful
        """
        vrf_id = vrf_data['idVRF']

        # Start by generating the proper dict of data needed by the template
        with tracer.start_span('generate_template_data', child_of=span) as child_span:
            template_data = Vrf._get_template_data(vrf_data, child_span)

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
                f'Template Data Error, the following keys were missing from the VRF restart data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence restarting the VRF
        management_ip = template_data.pop('management_ip')
        with tracer.start_span('generate_setconf', child_of=span):
            conf = utils.JINJA_ENV.get_template('vrf/restart.j2').render(**template_data)
        Vrf.logger.debug(f'Generated setconf for VRF #{vrf_id}\n{conf}')

        # Deploy the generated setconf to the router
        with tracer.start_span('deploy_setconf', child_of=span):
            return Vrf.deploy(conf, management_ip)

    @staticmethod
    def _get_template_data(vrf_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vrf data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the restart method and not here, this method is only concerned with fetching the
        data that it can.
        :param vrf_data: The data on the vrf that was retrieved from the API
        :param span: The tracing span in use for this task. In this method just pass it to API calls
        :returns: Constructed template data, or None if something went wrong
        """
        vrf_id = vrf_data['idVRF']
        Vrf.logger.debug(f'Compiling template data for VRF #{vrf_id}')
        data: Dict[str, Any] = {key: None for key in Vrf.template_keys}

        data['project_id'] = vrf_data['idProject']

        # Get the management ip address
        router_data = Vrf._get_router_data(vrf_data['idRouter'], span)
        if router_data is None:
            # We can't unresource this, so just return
            return None
        data['management_ip'] = router_data['management_ip']

        return data
