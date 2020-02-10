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
from scrubbers import Vr as VrScrubber
from settings import (
    SUCCESS_STATUS_CODE,
    NOT_FOUND_STATUS_CODE,
    UPDATE_STATUS_CODE,
)

__all__ = [
    'scrub_vr',
]


@app.task
def scrub_vr(vr_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.scrub_vr')
    span.set_tag('vr_id', vr_id)
    _scrub_vr(vr_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _scrub_vr(vr_id: int, span: Span):
    """
    Task to scrub the specified vr
    """
    logger = logging.getLogger('robot.tasks.vr.scrub')
    logger.info(f'Commencing scrub of VR #{vr_id}')

    # Read the VR
    # Don't use utils so we can check the response code
    child_span = opentracing.tracer.start_span('read_vr', child_of=span)
    response = Compute.virtual_router.read(
        token=Token.get_instance().token,
        pk=vr_id,
        span=child_span,
    )
    child_span.finish()

    if response.status_code == NOT_FOUND_STATUS_CODE:
        logger.info(
            f'Received scrub task for VR #{vr_id} but it was already deleted from the API',
        )
        span.set_tag('return_reason', 'already_deleted')
        return
    elif response.status_code != SUCCESS_STATUS_CODE:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch VR #{vr_id};\n'
            f'Response Text: {response.content.decode()}',
        )
        span.set_tag('return_reason', 'invalid_vr_id')
        return
    vr = response.json()['content']

    # Ensure that the state of the vr is still currently SCRUB_QUEUE
    if vr['state'] != state.SCRUB_QUEUE:
        logger.warning(
            f'Cancelling scrub of VR #{vr_id}. Expected state to be SCRUB, found {vr["state"]}.',
        )
        # Return out of this function without doing anything
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # There's no in-between state for Scrub tasks, just jump straight to doing the work
    success: bool = False
    child_span = opentracing.tracer.start_span('scrub', child_of=span)
    try:
        success = VrScrubber.scrub(vr, child_span)
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to scrub VR #{vr_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully scrubbed VR #{vr_id}')
        metrics.vr_scrub_success()
        # Delete the VR from the DB
        child_span = opentracing.tracer.start_span('delete_vr_from_api', child_of=span)
        response = Compute.virtual_router.delete(
            token=Token.get_instance().token,
            pk=vr_id,
            span=child_span,
        )
        child_span.finish()

        if response.status_code == UPDATE_STATUS_CODE:
            logger.info(f'VR #{vr_id} successfully deleted from the API')
        else:
            logger.error(
                f'HTTP {response.status_code} response received when attempting to delete VR #{vr_id};\n'
                f'Response Text: {response.content.decode()}',
            )

        child_span = opentracing.tracer.start_span('delete_project_from_api', child_of=span)
        utils.project_delete(vr['project']['id'], child_span)
        child_span.finish()
    else:
        logger.error(f'Failed to scrub VR #{vr_id}')
        metrics.vr_scrub_failure()

        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        try:
            EmailNotifier.vr_failure(vr, 'scrub')
        except Exception:
            logger.error(
                f'Failed to send build failure email for VR #{vr["idVR"]}',
                exc_info=True,
            )
        child_span.finish()
