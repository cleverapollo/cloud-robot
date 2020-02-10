"""
updater class for vrs

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
from builders import Vr as VrBuilder

__all__ = [
    'Vr',
]


class Vr(VrBuilder):
    """
    Class that handles the updating of the specified VR

    Inherits the Builder class as both classes have the same template data gathering method
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.updaters.vr')

    # Override this method to ensure that nobody calls this accidentally
    @staticmethod
    def build(vr_data: Dict[str, Any], span: Span) -> bool:
        """
        Shadow the build class build job to make sure we don't accidentally call it in this class
        """
        raise NotImplementedError('If you want to build a VR, use `builders.vr`, not `updaters.vr`')

    @staticmethod
    def update(vr_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the update of a vr using the data read from the API
        :param span: The tracing span in use for this update task
        :param vr_data: The result of a read request for the specified VR
        :return: A flag stating whether or not the update was successful
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
                f'Template Data Error, the following keys were missing from the VR update data: '
                f'{", ".join(missing_keys)}',
            )
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence updating the VR
        child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
        update_conf = utils.JINJA_ENV.get_template('vr/update.j2').render(**template_data)
        child_span.finish()

        Vr.logger.debug(f'Generated update setconf for VR #{vr_id}\n{update_conf}')

        # Deploy the generated setconf to the router
        management_ip = template_data.pop('management_ip')
        child_span = opentracing.tracer.start_span('deploy_update_setconf', child_of=span)
        success = Vr.deploy(update_conf, management_ip, True)
        child_span.finish()
        return success
