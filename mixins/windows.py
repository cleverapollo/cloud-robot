"""
mixin class containing methods that are needed by linux vm task classes
methods included;
    - method to deploy a given command to a given host
    - a fixed method to run powershell commands
"""
# stdlib
import logging
# lib
from jaeger_client import Span
from winrm import Response, Session
# local
import settings
from celery_app import tracer


class WindowsMixin:
    logger: logging.Logger

    @classmethod
    def deploy(cls, cmd: str, management_ip: str, span: Span) -> Response:
        """
        Deploy the given command to the specified Windows host.
        Contains a fix for running powershell scripts;
            - Powershell scripts will be encoded in UTF16 little-endian base64 before being sent to the host machine
            - Error messages are cleaned before being returned
        :param span: The span used for tracing the task that's currently running
        """
        cls.logger.debug(f'Deploying command to Windows Host {management_ip}\n{cmd}')
        session = Session(management_ip, auth=('administrator', settings.NETWORK_PASSWORD))
        with tracer.start_span('run_ps', child_of=span):
            response = session.run_ps(cmd)
        # Decode out and err
        if hasattr(response.std_out, 'decode'):
            response.std_out = response.std_out.decode()
        if hasattr(response.std_err, 'decode'):
            response.std_err = response.std_err.decode()
        return response
