"""
updater class for virtual_routers

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
from builders import VirtualRouter as VirtualRouterBuilder

__all__ = [
    'VirtualRouter',
]


class VirtualRouter(VirtualRouterBuilder):
    """
    Class that handles the updating of the specified virtual_router

    Inherits the Builder class as both classes have the same template data gathering method
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.updaters.virtual_router')

    # Override this method to ensure that nobody calls this accidentally
    @staticmethod
    def build(virtual_router_data: Dict[str, Any], span: Span) -> bool:
        """
        Shadow the build class build job to make sure we don't accidentally call it in this class
        """
        raise NotImplementedError(
            'If you want to build a virtual_router, use `builders.virtual_router`, not `updaters.virtual_router`',
        )

    @staticmethod
    def update(virtual_router_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the update of a virtual_router using the data read from the API
        :param span: The tracing span in use for this update task
        :param virtual_router_data: The result of a read request for the specified virtual_router
        :return: A flag stating whether or not the update was successful
        """
        virtual_router_id = virtual_router_data['id']

        # Start by generating the proper dict of data needed by the template
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = VirtualRouter._get_template_data(virtual_router_data, child_span)
        child_span.finish()

        # Check that the template data was successfully retrieved
        if template_data is None:
            error = f'Failed to retrieve template data for virtual_router #{virtual_router_id}.'
            VirtualRouter.logger.error(error)
            virtual_router_data['errors'].append(error)
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in VirtualRouter.template_keys):
            missing_keys = [f'"{key}"' for key in VirtualRouter.template_keys if template_data[key] is None]
            error = (
                f'Template Data Error, the following keys were missing from the virtual_router update data: '
                f'{", ".join(missing_keys)}'
            )
            VirtualRouter.logger.error(error)
            virtual_router_data['errors'].append(error)
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence updating the virtual_router
        child_span = opentracing.tracer.start_span('generate_setconf', child_of=span)
        update_conf = utils.JINJA_ENV.get_template('virtual_router/update.j2').render(**template_data)
        child_span.finish()

        VirtualRouter.logger.debug(f'Generated update setconf for virtual_router #{virtual_router_id}\n{update_conf}')

        # Deploy the generated setconf to the router
        management_ip = template_data.pop('management_ip')
        child_span = opentracing.tracer.start_span('deploy_update_setconf', child_of=span)
        success, errors = VirtualRouter.deploy(update_conf, management_ip, True)
        virtual_router_data['errors'].extend(errors)
        child_span.finish()
        return success
