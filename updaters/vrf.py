"""
updater class for vrfs

- gathers template data
- generates setconf
- deploys setconf to the chosen router
"""

# stdlib
import logging
from typing import Any, Dict
# local
import utils
from builders import Vrf as VrfBuilder

__all__ = [
    'Vrf',
]


class Vrf(VrfBuilder):
    """
    Class that handles the updating of the specified VRF

    Inherits the Builder class as both classes have the same template data gathering method
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('updaters.vrf')

    # Override this method to ensure that nobody calls this accidentally
    @staticmethod
    def build(vrf_data: Dict[str, Any]) -> bool:
        """
        Shadow the build class build job to make sure we don't accidentally call it in this class
        """
        raise NotImplementedError('If you want to build a VRF, use `builders.vrf`, not `updaters.vrf`')

    @staticmethod
    def update(vrf_data: Dict[str, Any]) -> bool:
        """
        Commence the update of a vrf using the data read from the API
        :param vrf_data: The result of a read request for the specified VRF
        :return: A flag stating whether or not the update was successful
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
                f'Template Data Error, the following keys were missing from the VRF update data: '
                f'{", ".join(missing_keys)}',
            )
            return False

        # If everything is okay, commence updating the VRF
        router_model = template_data.pop('router_model')
        management_ip = template_data.pop('management_ip')
        try:
            template_name = f'vrf/update_{router_model}.j2'
            conf = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        except Exception:
            Vrf.logger.error(
                f'Unable to find the update template for {router_model} Routers',
                exc_info=True,
            )
            return False
        Vrf.logger.debug(
            f'Generated setconf for VRF #{vrf_id}\n{conf}',
        )

        # Deploy the generated setconf to the router
        return Vrf.deploy(conf, management_ip)
