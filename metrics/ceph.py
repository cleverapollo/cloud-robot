from settings import REGION_NAME
from cloudcix_metrics import prepare_metrics, Metric


def build_success(total_secs: int):
    """
    Sends a data packet to Influx reporting a successful build
    :param total_secs: The total number of seconds that Robot took to build the Ceph (from request to build)
    """
    tags = {'region': REGION_NAME}
    prepare_metrics(lambda: Metric('ceph_build_success', 1, tags))
    prepare_metrics(lambda: Metric('ceph_time_to_build', total_secs, tags))


def build_failure():
    """
    Sends a data packet to Influx reporting a failed build
    """
    prepare_metrics(lambda: Metric('ceph_build_failure', 1, {'region': REGION_NAME}))
