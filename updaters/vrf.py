"""
updater class for vrfs

- gathers template data
- generates setconf
- deploys setconf to the chosen router
"""

# stdlib
import logging
from typing import Any, Dict
# lib
import opentracing
from jaeger_client import Span
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
    logger = logging.getLogger('robot.updaters.vrf')

    # Override this method to ensure that nobody calls this accidentally
    @staticmethod
    def build(vrf_data: Dict[str, Any], span: Span) -> bool:
        """
        Shadow the build class build job to make sure we don't accidentally call it in this class
        """
        raise NotImplementedError('If you want to build a VRF, use `builders.vrf`, not `updaters.vrf`')

    @staticmethod
    def update(vrf_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the update of a vrf using the data read from the API
        :param vrf_data: The result of a read request for the specified VRF
        :return: A flag stating whether or not the update was successful
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
                f'Template Data Error, the following keys were missing from the VRF update data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence updating the VRF
        router_model = template_data.pop('router_model')
        management_ip = template_data.pop('management_ip')
        try:
            child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
            build_template_name = f'vrf/build_{router_model}.j2'
            child_span.set_tag('template_name', build_template_name)
            build_conf = utils.JINJA_ENV.get_template(build_template_name).render(**template_data)
            delete_conf = utils.JINJA_ENV.get_template('vrf/scrub.j2').render(**template_data)
            child_span.finish()
        except Exception:
            Vrf.logger.error(
                f'Unable to find the update template for {router_model} Routers',
                exc_info=True,
            )
            span.set_tag('failed_reason', 'invalid_template_name')
            return False
        Vrf.logger.debug(f'Generated delete setconf for VRF #{vrf_id}\n{delete_conf}')
        Vrf.logger.debug(f'Generated build setconf for VRF #{vrf_id}\n{build_conf}')

        # Deploy the generated setconf to the router
        build_success = False
        child_span = opentracing.tracer.start_span('deploy_delete_setconf', child_of=span)
        delete_success = Vrf.deploy(delete_conf, management_ip)
        child_span.finish()
        if delete_success:
            child_span = opentracing.tracer.start_span('deploy_build_setconf', child_of=span)
            build_success = Vrf.deploy(build_conf, management_ip)
            child_span.finish()
            return build_success
        else:
            Vrf.logger.error(f'Failed to deploy delete conf for VRF #{vrf_id}')
            return delete_success
