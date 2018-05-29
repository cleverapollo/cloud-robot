import influxdb
from datetime import datetime

INFLUX_CLIENT = influxdb.InfluxDBClient(
    host='influx.cloudcix.com',
    port=80,
    database="robot"
)


def heartbeat():
    """
    Test version of heartbeat for RobotAlpha
    """
    data = [{
        "measurement": "robot_heartbeat",
        "tags": {
            "region": "alpha"
        },
        "time": datetime.utcnow(),
        "fields": {
            "value": 1
        }
    }]
    INFLUX_CLIENT.write_points(data)


def robot_down():
    """
    Informs Influx that the Robot is dead
    """
    data = [{
        "measurement": "robot_heartbeat",
        "tags": {
            "region": "alpha"
        },
        "time": datetime.utcnow(),
        "fields": {
            "value": 0
        }
    }]
    INFLUX_CLIENT.write_points(data)
