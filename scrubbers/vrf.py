"""
scrubber class for vrfs

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
    Class that handles the scrubbing of the specified VRF
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.scrubbers.vrf')
    # Keep track of the keys necessary for the template, so we can check all keys are present before scrubbing
    template_keys = {
        # The IP Address of the Management port of the physical Router
        'management_ip',
        # The id of the Project that owns the VRF being scrubbed
        'project_id',
    }

    @staticmethod
    def scrub(vrf_data: Dict[str, Any]) -> bool:
        """
        Commence the scrub of a vrf using the data read from the API
        :param vrf_data: The result of a read request for the specified VRF
        :return: A flag stating whether or not the scrub was successful
        """
        vrf_id = vrf_data['idVRF']

        # Start by generating the proper dict of data needed by the template
        template_data = Vrf._get_template_data(vrf_data)

        # Check that the template data was successfully retrieved
        if template_data is None:
            Vrf.logger.error(
                f'Failed to retrieve template data for VRF #{vrf_data["idVRF"]}.',
            )
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Vrf.template_keys):
            missing_keys = [
                f'"{key}"' for key in Vrf.template_keys if template_data[key] is None
            ]
            Vrf.logger.error(
                f'Template Data Error, the following keys were missing from the VRF scrub data: '
                f'{", ".join(missing_keys)}',
            )
            return False

        # If everything is okay, commence scrubbing the VRF
        management_ip = template_data.pop('management_ip')
        conf = utils.JINJA_ENV.get_template('vrf/scrub.j2').render(**template_data)
        Vrf.logger.debug(f'Generated setconf for VRF #{vrf_id}\n{conf}')

        # Deploy the generated setconf to the router
        success = Vrf.deploy(conf, management_ip, True)
        return success

    @staticmethod
    def _get_template_data(vrf_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Given the vrf data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the scrub method and not here, this method is only concerned with fetching the data
        that it can.
        :param vrf_data: The data on the vrf that was retrieved from the API
        :returns: Constructed template data, or None if something went wrong
        """
        vrf_id = vrf_data['idVRF']
        Vrf.logger.debug(f'Compiling template data for VRF #{vrf_id}')
        data: Dict[str, Any] = {key: None for key in Vrf.template_keys}

        data['project_id'] = vrf_data['idProject']

        # Get the management ip address
        router_data = Vrf._get_router_data(vrf_data['idRouter'])
        if router_data is None:
            # We can't unresource this, so just return
            return None
        data['management_ip'] = router_data['management_ip']

        return data
