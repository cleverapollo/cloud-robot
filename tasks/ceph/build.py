# stdlib
import logging
from typing import Any, Dict
# lib
import opentracing
from cloudcix.api.iaas import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from builders import Ceph
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier

__all__ = [
    'build_ceph',
]


def _unresource(ceph: Dict[str, Any], span: Span):
    """
    unresource the specified ceph because something went wrong
    """
    ceph_id = ceph['id']
    metrics.ceph_build_failure()

    # Update state to UNRESOURCED in the API
    child_span = opentracing.tracer.start_span('update_to_unresourced', child_of=span)
    response = IAAS.ceph.partial_update(
        token=Token.get_instance().token,
        pk=ceph_id,
        data={'state': state.UNRESOURCED},
        span=child_span,
    )
    child_span.finish()

    if response.status_code != 200:
        logging.getLogger('robot.tasks.ceph.build').error(
            f'could not update Ceph #{ceph_id} to state UNRESOURCED. \nResponse: {response.content.decode()}.',
        )

    child_span = opentracing.tracer.start_span('send_email', child_of=span)
    try:
        EmailNotifier.ceph_build_failure(ceph)
    except Exception:
        logging.getLogger('robot.tasks.ceph.build').error(
            f'Failed to send build failure email for Ceph #{ceph_id}',
            exc_info=True,
        )
    child_span.finish()


@app.task
def build_ceph(ceph_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.build_ceph')
    span.set_tag('ceph_id', ceph_id)
    _build_ceph(ceph_id, span)
    span.finish()

    # Flush the loggers after closing the span
    utils.flush_logstash()


def _build_ceph(ceph_id: int, span: Span):
    """
    Task to build the specified ceph
    """
    logger = logging.getLogger('robot.tasks.ceph.build')
    logger.info(f'Commencing build of Ceph #{ceph_id}.')

    # Read the Ceph record
    child_span = opentracing.tracer.start_span('read_ceph', child_of=span)
    ceph = utils.api_read(IAAS.ceph, ceph_id, span=child_span)
    child_span.finish()

    # Ensure it is not empty
    if not bool(ceph):
        # Reply on the utils method for logging
        metrics.ceph_build_failure()
        span.set_tag('return_reason', 'invalid_ceph_id')
        return

    # Ensure that the state of the Ceph is still currently REQUESTED (it hasn't been picked up by another runner)
    if ceph['state'] != state.REQUESTED:
        logger.warning(
            f'Cancelling build of ceph #{ceph_id}. '
            'Expected state to be {state.REQUESTED}, found {ceph["state"]},',
        )
        # Return out of this function without doing anything as if was already handled
        span.set_tag('return_reason', 'not_in_correct_state')
        return

    # catch all the errors if any
    ceph['errors'] = []

    # If all is well and good here, update the Ceph state to BUILDING and pass the data to the builder
    response = IAAS.ceph.partial_update(
        token=Token.get_instance().token,
        pk=ceph_id,
        data={'state': state.BUILDING},
        span=child_span,
    )
    child_span.finish()

    if response.status_code != 200:
        logger.error(
            f'Could not update Ceph #{ceph_id} to state BUILDING. \nResponse: {response.content.decode()}.',
        )
        metrics.ceph_build_failure()
        span.set_tag('return_reason', 'could_not_update_state')
        return

    # Call the appropriate builder
    success: bool = False
    child_span = opentracing.tracer.start_span('build', child_of=span)
    try:
        success = Ceph.build(ceph, child_span)
    except Exception as err:
        error = f'An unexpected error occurred when attempting to build Ceph #{ceph_id}.'
        logger.error(error, exc_info=True)
        ceph['errors'].append(f'{error} Error: {err}')
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully built Ceph #{ceph_id}')

        # Update state to RUNNING in the API
        child_span = opentracing.tracer.start_span('update_to_running', child_of=span)
        response = IAAS.ceph.partial_update(
            token=Token.get_instance().token,
            pk=ceph_id,
            data={'state': state.RUNNING},
            span=child_span,
        )
        child_span.finish()

        if response.status_code != 200:
            logger.error(
                f'Could not update Ceph #{ceph_id} to state RUNNING. Response: {response.content.decode()}.',
            )

        # Don't send an email for a successfully created ceph
        # If later this feature is added, code goes here
    else:
        logger.error(f'Failed to build Ceph #{ceph_id}')
        _unresource(ceph, span)
