"""
mixin class containing methods that are needed by linux vm task classes
methods included;
    - method to deploy a given command to a given host
    - a helper method to fully retrieve the response from paramiko outputs
"""
# stdlib
import logging
from collections import deque
from typing import Deque, Tuple
# lib
import opentracing
from jaeger_client import Span
from paramiko import SSHClient
# local

__all__ = [
    'LinuxMixin',
]


class LinuxMixin:
    logger: logging.Logger

    @classmethod
    def deploy(cls, command: str, client: SSHClient, span: Span) -> Tuple[str, str]:
        """
        Deploy the given `command` to the Linux host accessible via the supplied `client`
        :param command: The command to run on the host
        :param client: A paramiko.Client instance that is connected to the host
            The client is passed instead of the host_ip so we can avoid having to open multiple connections
        :param span: The span used for tracing the task that's currently running
        :return: The messages retrieved from stdout and stderr of the command
        """
        hostname = client.get_transport().sock.getpeername()[0]
        cls.logger.debug(f'Executing command {command} to Linux Host {hostname}')

        # Run the command via the client
        child_span = opentracing.tracer.start_span('exec_command', child_of=span)
        _, stdout, stderr = client.exec_command(command)
        cls.logger.debug(f'Executed command to Linux Host {hostname}')
        child_span.finish()

        # Read from stdout and stderr, keep going until the connection is closed
        channel = stdout.channel
        output_fragments: Deque[str] = deque()
        error_fragments: Deque[str] = deque()
        child_span = opentracing.tracer.start_span('read_channel', child_of=span)
        while True:
            # Check the status of the connection, and read any remaining output
            closed = channel.closed
            while channel.recv_ready():
                output_fragments.append(stdout.read().decode())  # Read the entirety of stdout

            while channel.recv_stderr_ready():
                # error_fragments.append(stderr.read().decode())  # Read the entirety of stderr
                # temporarily adding stderr to output as stderr is not evaluated properly, need to be removed.
                output_fragments.append(stderr.read().decode())

            if closed:
                break
        cls.logger.debug(f'Completed read of stdout and stderr from Linux Host {hostname}')
        child_span.finish()

        # Sorting out the output and the error
        output = ''.join(output_fragments)
        error = ''.join(error_fragments)

        return output, error

    @classmethod
    def netplan_bridge_setup(cls, bridge: str, client: SSHClient, filename: str, requester: str, span: Span) -> bool:
        """
        1. Checks for filename at /etc/netplan/ dir
        2. If present: returns True
           Else:
           2.1 Creates a bridge yaml file at temporary location /tmp/
           2.2 Moves the file to /etc/netplan/filename
           2.3 Runs netplan apply command
        """
        success = True
        hostname = client.get_transport().sock.getpeername()[0]
        sftp = client.open_sftp()
        file_exists = True
        try:
            child_span = opentracing.tracer.start_span('netplan_bridge_check', child_of=span)
            sftp.open(filename, mode='r')
            child_span.finish()
        except IOError:
            file_exists = False

        if file_exists:
            return success

        cls.logger.debug(f'Requester #{requester} :Bridge file {filename} not found, so creating the bridge.')
        temp_file = f'/tmp/{filename}'
        try:
            with sftp.open(temp_file, mode='w', bufsize=1) as yaml:
                yaml.write(bridge)
            cls.logger.debug(
                f'Requester #{requester}: Successfully wrote file {temp_file} to target #{hostname}',
            )
            # move temp file to netplan dir and apply netplan changes
            netplan_cmd = f'sudo mv {temp_file} /etc/netplan/{filename} && sudo netplan apply'
            child_span = opentracing.tracer.start_span('netplan_bridge_create', child_of=span)
            stdout, stderr = cls.deploy(netplan_cmd, client, child_span)
            if stderr:
                cls.logger.error(
                    f'Requester #{requester}: Applying netplan to target #{hostname} generated stderr: \n{stderr}',
                )
            else:
                cls.logger.debug(
                    f'Requester #{requester}: Applying netplan to target #{hostname} generated stdout: \n{stdout}',
                )
        except IOError:
            cls.logger.error(
                f'Requester #{requester}: Failed to write {temp_file} to target #{hostname}',
                exc_info=True,
            )
            success = False
        return success
