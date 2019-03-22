from cloudcix_metrics import prepare_metrics, Metric
from settings import REGION_NAME


def build_success():
    """
    Sends a data packet to Influx reporting a successful build
    """
    prepare_metrics(lambda: Metric('vrf_build_success', 1, {'region': REGION_NAME}))


def build_failure():
    """
    Sends a data packet to Influx reporting a failed build
    """
    prepare_metrics(lambda: Metric('vrf_build_failure', 1, {'region': REGION_NAME}))


def scrub_success():
    """
    Sends a data packet to Influx reporting a successful scrub
    """
    prepare_metrics(lambda: Metric('vrf_scrub_success', 1, {'region': REGION_NAME}))


def scrub_failure():
    """
    Sends a data packet to Influx reporting a failed scrub
    """
    prepare_metrics(lambda: Metric('vrf_scrub_failure', 1, {'region': REGION_NAME}))


def update_success():
    """
    Sends a data packet to Influx reporting a successful update
    """
    prepare_metrics(lambda: Metric('vrf_update_success', 1, {'region': REGION_NAME}))


def update_failure():
    """
    Sends a data packet to Influx reporting a failed update
    """
    prepare_metrics(lambda: Metric('vrf_update_failure', 1, {'region': REGION_NAME}))


def quiesce_success():
    """
    Sends a data packet to Influx reporting a successful quiesce
    """
    prepare_metrics(lambda: Metric('vrf_quiesce_success', 1, {'region': REGION_NAME}))


def quiesce_failure():
    """
    Sends a data packet to Influx reporting a failed quiesce
    """
    prepare_metrics(lambda: Metric('vrf_quiesce_failure', 1, {'region': REGION_NAME}))


def restart_success():
    """
    Sends a data packet to Influx reporting a successful restart
    """
    prepare_metrics(lambda: Metric('vrf_restart_success', 1, {'region': REGION_NAME}))


def restart_failure():
    """
    Sends a data packet to Influx reporting a failed restart
    """
    prepare_metrics(lambda: Metric('vrf_restart_failure', 1, {'region': REGION_NAME}))
