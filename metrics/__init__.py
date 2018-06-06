import influxdb
from datetime import datetime
from settings import REGION_NAME


INFLUX_CLIENT = influxdb.InfluxDBClient(
    host='influx.cloudcix.com',
    port=80,
    database='robot'
)


def heartbeat(value: int = 1):
    """
    Test version of heartbeat for RobotAlpha
    :param value: The value to send to Influx. Defaults to 1
        NOTE: Only send a 0 when Robot has gone down
    """
    data = [{
        'measurement': 'robot_heartbeat',
        'tags': {
            'region': REGION_NAME
        },
        'time': datetime.utcnow(),
        'fields': {
            'value': value
        }
    }]
    INFLUX_CLIENT.write_points(data)
