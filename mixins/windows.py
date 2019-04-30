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
from winrm import Response, Session
# local
import settings


class WindowsMixin:
    logger: logging.Logger

    @classmethod
    def deploy(cls, cmd: str, management_ip: str) -> Response:
        """
        Deploy the given command to the specified Windows host.
        Contains a fix for running powershell scripts;
            - Powershell scripts will be encoded in UTF16 little-endian base64 before being sent to the host machine
            - Error messages are cleaned before being returned
        """
        cls.logger.debug(f'Deploying command to Windows Host {management_ip}\n{cmd}')
        session = Session(management_ip, auth=('administrator', settings.NETWORK_PASSWORD))
        # Encode the command in a base64 little endian format
        cmd = b64encode(cmd.encode('utf_16_le')).decode('ascii')
        response = session.run_cmd(f'powershell -encodedcommand {cmd}')
        # Check for and clean any error
        if len(response.std_err):
            response.std_err = session._clean_error_msg(response.std_err.decode('utf-8'))
        return response
