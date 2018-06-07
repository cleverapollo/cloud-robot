import utils
from ._helpers import generate_data_packet


def current_commit(sha: str):
    """
    Logs the currently running commit for this instance of Robot.
    Grafana will display this at the top of each Robot's dashboard
    :param sha: The commit sha obtained from git
    """
    client = utils.get_influx_client()
    data = generate_data_packet('robot_commit', value=sha)
    client.write_points(data)
