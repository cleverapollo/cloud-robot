"""
mixin class containing methods that are needed by linux vm task classes
methods included;
    - method to deploy a given command to a given host
    - a fixed method to run powershell commands
"""
# stdlib
import logging
from base64 import b64encode
# lib
from jaeger_client import Span
from winrm import Response, Session
# local
import settings
from celery_app import tracer


class WindowsMixin:
    logger: logging.Logger

    @classmethod
    def deploy(cls, cmd: str, management_ip: str) -> Response:
        """
        Deploy the given command to the specified Windows host.
        """
        cls.logger.debug(f'Deploying command to Windows Host {management_ip}\n{cmd}')
        session = Session(management_ip, auth=('administrator', settings.NETWORK_PASSWORD))
        encoded_cmd = b64encode(cmd.encode('utf_16_le')).decode('ascii')
        response = session.run_cmd(f'powershell -encodedcommand {encoded_cmd}')
        if len(response.std_err):
            response.std_err = session._clean_error_msg(response.std_err)

        # Decode out and err
        if hasattr(response.std_out, 'decode'):
            response.std_out = response.std_out.decode()
        if hasattr(response.std_err, 'decode'):
            response.std_err = response.std_err.decode()
        return response
