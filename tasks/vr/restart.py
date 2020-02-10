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
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier
from restarters import Vr as VrRestarter
from settings import UPDATE_STATUS_CODE

__all__ = [
    'restart_vr',
]


@app.task
def restart_vr(vr_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.restart_vr')
    span.set_tag('vr_id', vr_id)
    _restart_vr(vr_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _restart_vr(vr_id: int, span: Span):
    """
    Task to restart the specified vr
    """
    logger = logging.getLogger('robot.tasks.vr.restart')
    logger.info(f'Commencing restart of VR #{vr_id}')

    # Read the VR
    child_span = opentracing.tracer.start_span('read_vr', child_of=span)
    vr = utils.api_read(Compute.virtual_router, vr_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vr is None:
        # Rely on the utils method for logging
        metrics.vr_restart_failure()
        span.set_tag('return_reason', 'invalid_vr_id')
        return

    # Ensure that the state of the vr is still currently RESTART
    if vr['state'] != state.RESTART:
        logger.warning(
            f'Cancelling restart of VR #{vr_id}. Expected state to be RESTART, found {vr["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # Update to intermediate state here (RESTARTING - 13)
    child_span = opentracing.tracer.start_span('update_to_restarting', child_of=span)
    response = Compute.virtual_router.partial_update(
        token=Token.get_instance().token,
        pk=vr_id,
        data={'state': state.RESTARTING},
        span=child_span,
    )
    child_span.finish()

    # Ensure the update was successful
    if response.status_code != UPDATE_STATUS_CODE:
        logger.error(
            f'Could not update VM #{vr_id} to the necessary RESTARTING. Response: {response.content.decode()}.',
        )
        span.set_tag('return_reason', 'could_not_update_state')
        metrics.vr_restart_failure()
        # Update to Unresourced?
        return

    # Do the actual restarting
    success: bool = False
    child_span = opentracing.tracer.start_span('restart', child_of=span)
    try:
        success = VrRestarter.restart(vr, child_span)
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to restart VR #{vr_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully restarted VR #{vr_id}')
        metrics.vr_restart_success()

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
    else:
        logger.error(f'Failed to restart VR #{vr_id}')
        metrics.vr_restart_failure()

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
            EmailNotifier.vr_failure(vr, 'restart')
        except Exception:
            logger.error(
                f'Failed to send build failure email for VR #{vr_id}',
                exc_info=True,
            )
        child_span.finish()
