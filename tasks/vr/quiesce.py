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
from quiescers import Vr as VrQuiescer
from settings import UPDATE_STATUS_CODE

__all__ = [
    'quiesce_vr',
]


@app.task
def quiesce_vr(vr_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.quiesce_vr')
    span.set_tag('vr_id', vr_id)
    _quiesce_vr(vr_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _quiesce_vr(vr_id: int, span: Span):
    """
    Task to quiesce the specified vr
    """
    logger = logging.getLogger('robot.tasks.vr.quiesce')
    logger.info(f'Commencing quiesce of VR #{vr_id}')

    # Read the VR
    child_span = opentracing.tracer.start_span('read_vr', child_of=span)
    vr = utils.api_read(Compute.virtual_router, vr_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vr is None:
        # Rely on the utils method for logging
        metrics.vr_quiesce_failure()
        span.set_tag('return_reason', 'invalid_vr_id')
        return

    # Ensure that the state of the vr is still currently SCRUB or QUIESCE
    valid_states = [state.QUIESCE, state.SCRUB]
    if vr['state'] not in valid_states:
        logger.warning(
            f'Cancelling quiesce of VR #{vr_id}. Expected state to be one of {valid_states}, found {vr["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    if vr['state'] == state.QUIESCE:
        # Update the state to QUIESCING (12)
        child_span = opentracing.tracer.start_span('update_to_quiescing', child_of=span)
        response = Compute.virtual_router.partial_update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.QUIESCING},
            span=child_span,
        )
        child_span.finish()

        # Ensure the update was successful
        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'Could not update VM #{vr_id} to the necessary QUIESCING. Response: {response.content.decode()}.',
            )
            span.set_tag('return_reason', 'could_not_update_state')
            metrics.vr_quiesce_failure()
            # Update to Unresourced?
            return
    else:
        # Update the state to SCRUB_PREP (14)
        child_span = opentracing.tracer.start_span('update_to_scrub_prep', child_of=span)
        response = Compute.virtual_router.partial_update(
            token=Token.get_instance().token,
            pk=vr_id,
            data={'state': state.SCRUB_PREP},
            span=child_span,
        )
        child_span.finish()
        # Ensure the update was successful
        if response.status_code != UPDATE_STATUS_CODE:
            logger.error(
                f'Could not update VM #{vr_id} to the necessary SCRUB_PREP. Response: {response.content.decode()}.',
            )
            span.set_tag('return_reason', 'could_not_update_state')
            metrics.vr_quiesce_failure()
            # Update to Unresourced?
            return

    # Do the actual quiescing
    success: bool = False
    child_span = opentracing.tracer.start_span('quiesce', child_of=span)
    try:
        success = VrQuiescer.quiesce(vr, child_span)
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to quiesce VR #{vr_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully quiesced VR #{vr_id}')
        metrics.vr_quiesce_success()
        # Update state, depending on what state the VR is currently in (QUIESCE -> QUIESCED, SCRUB -> SCRUB_QUEUE)
        if vr['state'] == state.QUIESCE:
            child_span = opentracing.tracer.start_span('update_to_quiescing', child_of=span)
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vr_id,
                data={'state': state.QUIESCED},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != UPDATE_STATUS_CODE:
                logger.error(
                    f'Could not update VR #{vr_id} to state QUIESCED. Response: {response.content.decode()}.',
                )
        elif vr['state'] == state.SCRUB:
            child_span = opentracing.tracer.start_span('update_to_deleted', child_of=span)
            response = Compute.virtual_router.partial_update(
                token=Token.get_instance().token,
                pk=vr_id,
                data={'state': state.SCRUB_QUEUE},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != UPDATE_STATUS_CODE:
                logger.error(
                    f'Could not update VR #{vr_id} to state SCRUB_QUEUE. Response: {response.content.decode()}.',
                )
        else:
            logger.error(
                f'VR #{vr_id} has been quiesced despite not being in a valid state. '
                f'Valid states: {valid_states}, VR is in state {vr["state"]}',
            )
    else:
        logger.error(f'Failed to quiesce VR #{vr_id}')
        metrics.vr_quiesce_failure()

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
            EmailNotifier.vr_failure(vr, 'quiesce')
        except Exception:
            logger.error(
                f'Failed to send build failure email for VR #{vr_id}',
                exc_info=True,
            )
        child_span.finish()
