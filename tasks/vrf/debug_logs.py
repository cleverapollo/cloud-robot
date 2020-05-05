# stdlib
import logging
from datetime import datetime, timedelta
# lib
import opentracing
from cloudcix.api import IAAS
from jaeger_client import Span
# local
import metrics
import state
import utils
from celery_app import app
from cloudcix_token import Token
from email_notifier import EmailNotifier
from updaters import Vrf as VrfUpdater

__all__ = [
    'debug_logs',
    'debug_logs_task',
]


@app.task
def debug_logs_task(vrf_id: int):
    """
    Waits for 15 min from the time latest updated or created for Firewall rules to reset the debug_logging field
    for all firewall rules of a VRF
    """
    vrf = utils.api_read(IAAS.vrf, vrf_id)
    if vrf is None:
        return
    firewall_rules = vrf['firewall_rules']
    if len(firewall_rules) == 0:
        return
    list_updated = [firewall_rule['updated'] for firewall_rule in firewall_rules]
    # Find the latest updated firewall
    now = datetime.now()
    latest = max(list_updated)

    # compare with 15 min
    delta = now - latest
    if delta >= timedelta(minutes=15):
        debug_logs.delay(vrf_id)


@app.task
def debug_logs(vrf_id: int):
    """
    Helper function that wraps the actual task in a span, meaning we don't have to remember to call .finish
    """
    span = opentracing.tracer.start_span('tasks.debug_logs')
    span.set_tag('vrf_id', vrf_id)
    _debug_logs(vrf_id, span)
    span.finish()

    # Flush the loggers here so it's not in the span
    utils.flush_logstash()


def _debug_logs(vrf_id: int, span: Span):
    """
    Task to change the debug state of firewall rule logs of the specified vrf
    """
    logger = logging.getLogger('robot.tasks.vrf.debug_logs')
    logger.info(f'Commencing update of VRF #{vrf_id} to disable the debug status of firewall logs')

    # Read the VRF
    child_span = opentracing.tracer.start_span('read_vrf', child_of=span)
    vrf = utils.api_read(IAAS.vrf, vrf_id, span=child_span)
    child_span.finish()

    # Ensure it is not none
    if vrf is None:
        # Rely on the utils method for logging
        metrics.vrf_update_failure()
        span.set_tag('return_reason', 'invalid_vrf_id')
        return

    # Ensure that the state of the vrf is in Running state
    if vrf['state'] != state.RUNNING:
        logger.warn(f'Cancelling update of VRF #{vrf_id} to disable the debug status of firewall logs.'
                    f'Expected state to be RUNNING, found {vrf["state"]}.')
        # Return out of this function without doing anything as it will be handled by other tasks
        span.set_tag('return_reason', 'not_in_valid_state')
        return

    # No need to update the state of vrf to updating as this is not actual UPDATE task.

    # change the debug_logging to false for all firewall rules
    for firewall in vrf['firewall_rules']:
        vrf[firewall]['debug_logging'] = False

    success: bool = False
    child_span = opentracing.tracer.start_span('update', child_of=span)
    try:
        success = VrfUpdater.update(vrf, child_span)
    except Exception:
        logger.error(
            f'An unexpected error occurred when attempting to disable the debug status of firewall logs VRF #{vrf_id}',
            exc_info=True,
        )
    child_span.finish()

    span.set_tag('return_reason', f'success: {success}')

    if success:
        logger.info(f'Successfully disabled the debug status of firewall logs VRF #{vrf_id}')
        metrics.vrf_update_success()

        # check the state of VRF in the API before changing the debug status of firewall rules of vrf.
        child_span = opentracing.tracer.start_span('read_vrf', child_of=span)
        vrf = utils.api_read(IAAS.vrf, vrf_id, span=child_span)
        child_span.finish()

        # Ensure it is not none
        if vrf is None:
            return

        # Ensure that the state of the vrf is in Running state otherwise no need to change the debug status
        # as the next tasks would take care of this.
        if vrf['state'] == state.RUNNING:
            child_span = opentracing.tracer.start_span('debug_to_false', child_of=span)
            response = IAAS.vrf.partial_update(
                token=Token.get_instance().token,
                pk=vrf_id,
                data={'debug': False},
                span=child_span,
            )
            child_span.finish()

            if response.status_code != 204:
                logger.error(
                    f'Could not reset the debug status of firewall logs of VRF #{vrf_id}. '
                    f'Response: {response.content.decode()}.',
                )
    else:
        logger.error(f'Failed to disable the debug status of firewall logs of VRF #{vrf_id} on router. ')
        metrics.vrf_update_failure()

        child_span = opentracing.tracer.start_span('send_email', child_of=span)
        try:
            EmailNotifier.vrf_failure(vrf, 'update')
        except Exception:
            logger.error(
                f'Failed to send update failure email for VRF #{vrf["idVRF"]}',
                exc_info=True,
            )
        child_span.finish()
