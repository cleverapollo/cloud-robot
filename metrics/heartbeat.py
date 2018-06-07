import settings
import utils
from datetime import datetime


def heartbeat(value: int = 1):
    """
    Test version of heartbeat for RobotAlpha
    :param value: The value to send to Influx. Defaults to 1
        NOTE: Only send a 0 when Robot has gone down
    """
    client = utils.get_influx_client()
    data = [{
        'measurement': 'robot_heartbeat',
        'tags': {
            'region': settings.REGION_NAME
        },
        'time': datetime.utcnow(),
        'fields': {
            'value': value
        }
    }]
    client.write_points(data)
