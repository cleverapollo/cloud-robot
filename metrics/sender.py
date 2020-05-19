"""
Have to abstract out the metrics from the library, as we cannot use it in a multiprocessing form inside celery
"""
# stdlib
import urllib3
from collections import namedtuple
from datetime import datetime
from typing import List, Dict, Callable, Optional, Any
# lib
import influxdb
# local
import settings

# Suppress InsecureRequestWarnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INFLUX_CLIENT = None

# Define a helper data type for Influx data
InfluxData = Dict[str, Any]

Metric = namedtuple('Metric', ['table', 'value', 'tags'])


def _generate_data_packet(measurement: str, fields: dict, tags: dict = {}) -> List[InfluxData]:
    """
    Generates a data packet for the current region with the given measure name
    and whatever fields are passed to this method, and turns it into a format to be sent to influx
    :param measurement: The name of the measurement to send
    :param fields: Key-value pairs of data to be sent. Not indexed in Influx
    :param tags: Extra meta-data to be associated with a data point. Indexed in Influx
    :return: A prepared data packet in a form ready to be sent to InfluxDB
    """
    tags = tags or {}
    extra_tags = getattr(settings, 'CLOUDCIX_INFLUX_TAGS', {})
    tags.update(extra_tags)
    data = [{
        'measurement': measurement,
        'tags': tags,
        'fields': fields,
        'time': datetime.utcnow(),
    }]
    return data


def _get_influx_client() -> influxdb.InfluxDBClient:
    """
    Lazy creates a client for connecting to our InfluxDB instance
    :return: An InfluxDBClient that can log metrics to our instance of Influx
    """
    global INFLUX_CLIENT
    if INFLUX_CLIENT is None and settings.INFLUX_DATABASE is not None:
        INFLUX_CLIENT = influxdb.InfluxDBClient(
            host=settings.INFLUX_URL,
            port=settings.INFLUX_PORT,
            database=settings.INFLUX_DATABASE,
            ssl=settings.INFLUX_PORT == 443,
        )
        # Ensure the database exists
        INFLUX_CLIENT.create_database(settings.INFLUX_DATABASE)
    return INFLUX_CLIENT


def prepare_metrics(preprocess: Callable[..., Optional[Metric]], **kwargs):
    """
    Compat method with the metrics lib
    Unpack the metric and send it without adding it to any queue
    """
    metric = preprocess(**kwargs)
    if metric is None:
        return
    _post_metrics(metric.table, metric.value, metric.tags)


def _post_metrics(measurement: str, value, tags: dict = None):
    """
    Sends the given k-v pair (measurement->value) to influx
    along with the given tags
    :param measurement: the key for the significant metric field
    :param value: the value for the significant metric field
    :param tags: the relevant tags
    """
    tags = tags or {}
    client = _get_influx_client()
    if client is None:
        return
    client.write_points(_generate_data_packet(measurement, {'value': value}, tags))
