# stdlib
import logging
# lib
import opentracing
from cloudcix.api.compute import Compute
from jaeger_client import Span
# local
import metrics
import state
import utils
from builders import Vr as VrBuilder
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier
from settings import UPDATE_STATUS_CODE

__all__ = [
    'build_vr',
]


@app.task
def build_vr(vr_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.build_vr')
    span.set_tag('vr_id', vr_id)
    _build_vr(vr_id, span)
    span.finish()
    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _build_vr(vr_id: int, span: Span):
    """
    Task to build the specified vr
    """
    logger = logging.getLogger('robot.tasks.vr.build')
    logger.info(f'Commencing build of VR #{vr_id}')

    # Read the VR
    child_span = opentracing.tracer.start_span('read_vr', child_of=span)
    vr = utils.api_read(Compute.virtual_router, vr_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vr is None:
        # Rely on the utils method for logging
        metrics.vr_build_failure()
        span.set_tag('return_reason', 'invalid_vr_id')
        return

    # Ensure that the state of the vr is still currently REQUESTED (it hasn't been picked up by another runner)
    if vr['state'] != state.REQUESTED:
        logger.warning(f'Cancelling build of VR #{vr_id}. Expected state to be {state.REQUESTED}, found {vr["state"]}.')
        # Return out of this function without doing anything as it was already handled
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # If all is well and good here, update the VR state to BUILDING and pass the data to the builder
    child_span = opentracing.tracer.start_span('update_to_building', child_of=span)
    response = Compute.virtual_router.partial_update(
        token=Token.get_instance().token,
        pk=vr_id,
        data={'state': state.BUILDING},
        span=child_span,
    )
    child_span.finish()

    if response.status_code != UPDATE_STATUS_CODE:
        logger.error(
            f'Could not update VR #{vr_id} to state BUILDING. Response: {response.content.decode()}.',
        )
        metrics.vr_build_failure()
        span.set_tag('return_reason', 'could_not_update_state')
        return

    success: bool = False
    child_span = opentracing.tracer.start_span('build', child_of=span)
    try:
        success = VrBuilder.build(vr, child_span)
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to build VR #{vr_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully built VR #{vr_id}')
        metrics.vr_build_success()

        # Update state to RUNNING in the API
        child_span = opentracing.tracer.start_span('update_to_running', child_of=span)
        response = Compute.virtual_router.partial_update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.RUNNING},
            span=child_span,
        )
        child_span.finish()

        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'Could not update VR #{vr_id} to state RUNNING. Response: {response.content.decode()}.',
            )

        # Check if they built any VPNs and if so, send an email
        send_email_vpns = [vpn for vpn in vr.get('vpns', []) if vpn['send_email']]
        if len(send_email_vpns) > 0:
            for vpn in send_email_vpns:
                vpn['vr_ip_address'] = vr['vr_ip']
                child_span = opentracing.tracer.start_span('send_email', child_of=span)
                try:
                    EmailNotifier.vpn_build_success(vpn)
                    # update the send_email to False.
                    child_span = opentracing.tracer.start_span('update_to_send_email', child_of=span)
                    response = Compute.vpn.partial_update(
                        token=Token.get_instance().token,
                        pk=vpn['id'],
                        data={'send_email': False},
                        span=child_span,
                    )
                    child_span.finish()
                    if response.status_code != UPDATE_STATUS_CODE:
                        logger.error(
                            f'Could not update VPN #{vpn["id"]} to reset send_email. '
                            f'Response: {response.content.decode()}.',
                        )
                except Exception:
                    logger.error(
                        f'Failed to send build success email for VPN #{vpn["id"]}',
                        exc_info=True,
                    )
                child_span.finish()
    else:
        logger.error(f'Failed to build VR #{vr_id}')
        metrics.vr_build_failure()

        # Update state to UNRESOURCED in the API
        child_span = opentracing.tracer.start_span('update_to_unresourced', child_of=span)
        response = Compute.virtual_router.partial_update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.UNRESOURCED},
            span=child_span,
        )
        child_span.finish()

        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'Could not update VR #{vr_id} to state UNRESOURCED. Response: {response.content.decode()}.',
            )

        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        try:
            EmailNotifier.vr_failure(vr, 'build')
        except Exception:
            logger.error(
                f'Failed to send build failure email for VR #{vr_id}',
                exc_info=True,
            )
        child_span.finish()
