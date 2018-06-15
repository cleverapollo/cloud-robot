"""
A file of helper methods for any metrics that are needed / would be helpful
"""
import settings
from datetime import datetime
from typing import List, Dict, Union


# Define a helper data type for Influx data
InfluxData = Dict[str, Union[str, int, datetime]]


__all__ = [
    'generate_data_packet',
]


def generate_data_packet(measurement: str, **fields) -> List[InfluxData]:
    """
    Generates a data packet for the current region with the given measure name
    and whatever fields are passed to this method, and turns it into a format
    to be sent to influx
    :param measurement: The name of the measurement to send
    :param fields: key-value pairs of data to be sent
    :return: A prepared data packet in a form ready to be sent to InfluxDB
    """
    data = [{
        'measurement': measurement,
        'tags': {
            'region': settings.REGION_NAME,
        },
        'time': datetime.utcnow(),
        'fields': fields,
    }]
    return data
