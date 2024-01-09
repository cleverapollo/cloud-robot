"""
builder class for ceph

- gathers template data
- generates bash script using template data
- executes bash script on Ceph monitors
"""

# stdlib
import logging
import socket
from typing import Any, Dict, Optional
# lib
import opentracing
from jaeger_client import Span
from paramiko import AutoAddPolicy, RSAKey, SSHClient, SSHException
# local
import settings
from mixins import LinuxMixin
from utils import (
    get_ceph_pool,
    JINJA_ENV,
)


__all__ = [
    'Ceph',
]

MB_PER_GB = 1024


class Ceph(LinuxMixin):
    """
    Class that handles the building of the specified ceph
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.ceph')
    # Keep track of the keys necessary for the template, so we can check all keys are present before building
    template_keys = {
        # The CIX name of the device, generated from its id
        'device_name',
        # The size of the Ceph drive in MB
        'device_size',
        # Network Host password
        'host_sudo_passwd',
        # The Ceph pool where the drive will be built
        'pool_name',
        # The message to display if the drive was created
        'success_msg',
    }

    @staticmethod
    def build(ceph_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the build of a ceph drive using the data read from the API
        :param ceph_data: The result of a read request for the specified ceph
        :param span: The tracing span in use for this build task
        :return: A flag stating if the build was successful
        """
        ceph_id = ceph_data['id']

        if len(settings.CEPH_MONITORS) == 0:
            Ceph.logger.error('Cannot build ceph drive, no CEPH_MONITORS set')
            return False

        # Start by generating the proper dict of data needed by the template
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Ceph._get_template_data(ceph_data, child_span)
        child_span.finish()

        # Check that the template data was successfully retrieved
        if template_data is None:
            error = f'Failed to retrieve template data for ceph #{ceph_id}.'
            Ceph.logger.error(error)
            ceph_data['errors'].append(error)
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all the necessary keys are present
        if not all(template_data[key] is not None for key in Ceph.template_keys):
            missing_keys = [f'"{key}"' for key in Ceph.template_keys if template_data[key] is None]
            error_msg = f'Template Data Error, the following keys were missing from the ceph build data:' \
                        f' {", ".join(missing_keys)}'
            Ceph.logger.error(error_msg)
            ceph_data['errors'].append(error_msg)
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # If everything is okay, commence building the ceph drive
        build_bash_script = JINJA_ENV.get_template('ceph/commands/build.j2').render(**template_data)
        Ceph.logger.debug(f'Generated build bash script for ceph #{ceph_id}\n{build_bash_script}')

        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        key = RSAKey.from_private_key_file('/root/.ssh/id_rsa')

        built = False
        for host_ip in settings.CEPH_MONITORS:
            span.set_tag('host', host_ip)

            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            try:
                # No need for password as it should have keys
                sock.connect((host_ip, 22))
                client.connect(hostname=host_ip, username='administrator', pkey=key, timeout=30, sock=sock)

                Ceph.logger.debug(f'Executing Ceph build commands for ceph #{ceph_id}')
                child_span = opentracing.tracer.start_span('build_ceph', child_of=span)
                stdout, stderr = Ceph.deploy(build_bash_script, client, child_span)
                child_span.finish()

                if stderr:
                    Ceph.logger.error(f'Build commands for ceph #{ceph_id} generated stderr.\n{stderr}')
                    ceph_data['errors'].append(stderr)
                if stdout:
                    Ceph.logger.debug(f'Build commands for ceph #{ceph_id} generated stdout.\n{stdout}')
                    built = template_data['success_msg'] in stdout

            except (OSError, SSHException, TimeoutError):
                error = f'Exception occurred while building ceph #{ceph_id} in {host_ip}'
                Ceph.logger.error(error, exc_info=True)
                ceph_data['errors'].append(error)
                span.set_tag('failed_reason', 'ssh_error')
            finally:
                client.close()

            if built:
                break

        return built

    @staticmethod
    def _get_template_data(ceph_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the ceph data from the API, create a dictionary that contains all the keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching all the
        data that it can.
        :param ceph_data: The data on the ceph that was retrieved from the API
        :param span: The tracing span in use for this task
        :returns: Constructed template data, or None if something went wrong
        """
        ceph_id = ceph_data['id']
        Ceph.logger.debug(f'Compiling template data for ceph #{ceph_id}')
        data: Dict[str, Any] = {key: None for key in Ceph.template_keys}

        project_id = ceph_data['project_id']
        data['device_name'] = f'{project_id}_{ceph_id}'
        data['success_msg'] = f'CephDrive#{ceph_id}IsBuilt'
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD

        for spec in ceph_data['specs']:
            if spec['sku'].startswith('CEPH_'):
                data['device_size'] = int(spec['quantity']) * MB_PER_GB
                data['pool_name'] = get_ceph_pool(spec['sku'])
                break

        return data
