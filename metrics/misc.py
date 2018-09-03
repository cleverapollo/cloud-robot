from cloudcix_metrics import prepare_metrics, Metric
from settings import REGION_NAME


def current_commit(sha: str):
    """
    Logs the currently running commit for this instance of Robot.
    Grafana will display this at the top of each Robot's dashboard
    :param sha: The commit sha obtained from git
    """
    prepare_metrics(lambda: Metric('robot_commit', sha, {'region': REGION_NAME}))
