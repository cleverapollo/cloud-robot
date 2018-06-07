import utils
from ._helpers import generate_data_packet


def build_success():
    """
    Sends a data packet to Influx reporting a successful build
    """
    client = utils.get_influx_client()
    data = generate_data_packet("vm_success", value=1)
    client.write_points(data)


def build_failure():
    """
    Sends a data packet to Influx reporting a successful build
    """
    client = utils.get_influx_client()
    data = generate_data_packet("vm_failure", value=1)
    client.write_points(data)
