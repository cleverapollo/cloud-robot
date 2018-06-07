import utils
from ._helpers import generate_data_packet


def heartbeat(value: int = 1):
    """
    Test version of heartbeat for RobotAlpha
    :param value: The value to send to Influx. Defaults to 1
        NOTE: Only send a 0 when Robot has gone down
    """
    client = utils.get_influx_client()
    data = generate_data_packet('robot_heartbeat', value=value)
    client.write_points(data)
