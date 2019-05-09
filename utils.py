"""
File containing some utility functions that wrap around various repeatedly used logic
"""
# stdlib
import atexit
import logging
import logging.handlers
import subprocess
from typing import Any, Dict, List, Optional
# lib
import jinja2
from cloudcix.api import IAAS
from cloudcix.client import Client
from jaeger_client import Span
from logstash_async.formatter import LogstashFormatter
from logstash_async.handler import AsynchronousLogstashHandler
# local
from cloudcix_token import Token
from settings import REGION_NAME, LOGSTASH_IP


__all__ = [
    'flush_logstash',
    'get_current_git_sha',
    'JINJA_ENV',
    'api_list',
    'project_delete',
    'api_read',
    'setup_root_logger',
]

JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader('templates'),
    trim_blocks=True,
)


def setup_root_logger():
    """
    Called at startup.
    Sets up the proper handlers on the root logger which allows all other loggers to propogate messages to it
    instead of having that old bad system
    :param level: The level at which to log messages
    """
    # Add null handler to root logger to avoid basicConfig from running
    logging.getLogger().handlers = []

    # Set up robot parent logger
    logger = logging.getLogger('robot')
    if len(logger.handlers) > 0:
        logger.debug('utils.setup_root_logger found handlers already in the root logger')
        return
    logger.setLevel(logging.DEBUG)

    # Stream Handler
    fmt = logging.Formatter(fmt='%(asctime)s - %(name)s: %(levelname)s: %(message)s', datefmt='%d/%m/%y @ %H:%M:%S')
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    stream_handler.setLevel(logging.DEBUG)
    logger.addHandler(stream_handler)

    # Logstash Handler
    logstash_fmt = LogstashFormatter(extra={'application': 'robot', 'region': REGION_NAME})
    logstash_handler = AsynchronousLogstashHandler(LOGSTASH_IP, 5959, 'log.db')
    logstash_handler.setFormatter(logstash_fmt)
    logstash_handler.setLevel(logging.INFO)
    logger.addHandler(logstash_handler)

    # At exit, flush all logs to logstash
    atexit.register(logstash_handler.flush)

    # Hide other logs


def get_current_git_sha() -> str:
    """
    Finds the current git commit sha and returns it
    :return: The sha of the current commit
    """
    return subprocess.check_output([
        'git',
        'describe',
        '--always',
    ]).strip().decode()


def flush_logstash():
    """
    helper method to flush the logstash handler
    """
    for handler in logging.getLogger('robot').handlers:
        if hasattr(handler, 'flush'):
            handler.flush()


def project_delete(project_id: int, span: Span):
    """
    Check if the specified project is ready to be deleted from the API, and delete it if it is
    :param span: The span currently tracing the job. Just passed into the API calls this function makes
    """
    logger = logging.getLogger('robot.utils.project_delete')
    # Check that list requests for VRF and VM both are empty, and if so, delete the project
    active_vrfs = len(api_list(IAAS.vrf, {'project': project_id}, span=span))
    active_vms = len(api_list(IAAS.vm, {'project': project_id}, span=span))
    if active_vms == 0 and active_vrfs == 0:
        logger.debug(f'Project #{project_id} is empty. Sending delete request.')
        response = IAAS.project.delete(token=Token.get_instance().token, pk=project_id, span=span)
        if response.status_code == 204:
            logger.info(f'Successfully deleted Project #{project_id} from the CMDB')
        else:
            logger.error(
                f'HTTP {response.status_code} error occurred when attempting to delete Project #{project_id};\n'
                f'Response Text: {response.content.decode()}',
            )
    else:
        logger.debug(f'Cannot delete Project #{project_id}. {active_vrfs} VRFs and {active_vms} VMs remain active.')


# Methods that wrap cloudcix clients to abstract retrieval and checking
# These methods replace the ones in ro.py
# However, we only replace the list and read method, since wrapping update and delete didn't really affect the code
# make request -> check status code / call ro.update -> check flag

def api_list(client: Client, params: Dict[str, Any], **kwargs) -> List[Any]:
    """
    Calls the list command on the supplied client, using the supplied parameters and kwargs and fetches all of the data
    that matches.
    :param client: The client to call the list method on
    :param params: List parameters to be sent in the request
    :param kwargs: Any extra kwargs to pass to the request (ie spans)
    :returns: A list of instances of the client, if the request is valid, else an empty list
    """
    logger = logging.getLogger('robot.utils.api_list')
    client_name = f'{client.application}.{client.service_uri}'
    logger.debug(
        f'Attempting to retrieve a list of {client_name} records with the following filters: {params}',
    )
    params['page'] = 0
    response = client.list(
        token=Token.get_instance().token,
        params=params,
        **kwargs,
    )
    if response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch {client_name} instances with '
            f'filters {params};\nResponse Text: {response.content.decode()}',
        )
        return []
    response_data = response.json()
    records_found: int
    if 'totalRecords' in response_data['_metadata']:
        records_found = response_data['_metadata']['totalRecords']
    else:
        records_found = response_data['_metadata']['total_records']
    logger.debug(
        f'{client_name}.list retrieved {records_found} records with the following filters: {params}',
    )
    objs = response_data['content']
    while len(objs) < records_found:
        params['page'] += 1
        response = client.list(
            token=Token.get_instance().token,
            params=params,
            **kwargs,
        )
        if response.status_code != 200:
            logger.error(
                f'HTTP {response.status_code} error occurred when attempting to fetch {client_name} instances with '
                f'filters {params};\nResponse Text: {response.content.decode()}',
            )
            return objs
        objs.extend(response.json()['content'])
    return objs


def api_read(client: Client, pk: int, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Calls the read command on the supplied client, using the supplied pk to make the request
    :param client: The client to call the read method on
    :param pk: The id of the object to read
    :param kwargs: Any extra kwargs to pass to the request (ie spans)
    :returns: The read instance, or None if an error occurs
    """
    logger = logging.getLogger('robot.utils.api_read')
    client_name = f'{client.application}.{client.service_uri}'
    logger.debug(f'Attempting to read {client_name} #{pk}')
    response = client.read(
        token=Token.get_instance().token,
        pk=pk,
        **kwargs,
    )
    if response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch {client_name} #{pk};\n'
            f'Response Text: {response.content.decode()}',
        )
        return None
    return response.json()['content']
