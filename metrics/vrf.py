from cloudcix_metrics import prepare_metrics, Metric
from settings import REGION_NAME


def build_success():
    """
    Sends a data packet to Influx reporting a successful build
    """
    prepare_metrics(lambda: Metric('vrf_success', 1, {'region': REGION_NAME}))


def build_failure():
    """
    Sends a data packet to Influx reporting a failed build
    """
    prepare_metrics(lambda: Metric('vrf_failure', 1, {'region': REGION_NAME}))


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
