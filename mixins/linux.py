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
from paramiko import Channel, SSHClient
# local

__all__ = [
    'LinuxMixin',
]


class LinuxMixin:
    logger: logging.Logger

    @staticmethod
    def get_full_response(channel: Channel, read_size: int = 1476) -> str:
        """
        Get the full response from the specified paramiko channel, waiting a given number of seconds before trying to
        read from it each time.
        :param channel: The channel to be read from
        :param read_size: How many bytes to be read from the channel each time
        :return: The full output from the channel, or as much as can be read given the parameters.
        """
        fragments: Deque[str] = deque()
        while channel.recv_ready():
            fragments.append(channel.recv(read_size).decode())
        return ''.join(fragments)

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
        cls.logger.debug(f'Deploying command {command} to Linux Host {hostname}')

        # Run the command via the client
        child_span = opentracing.tracer.start_span('exec_command', child_of=span)
        _, stdout, stderr = client.exec_command(command)
        # Block until command finishes
        stdout.channel.recv_exit_status()
        stderr.channel.recv_exit_status()
        cls.logger.debug(f'Deployed command to Linux Host {hostname}')
        child_span.finish()

        # Read the full response from both channels
        child_span = opentracing.tracer.start_span('read_stdout', child_of=span)
        output = cls.get_full_response(stdout.channel)
        cls.logger.debug(f'Completed read of output from Linux Host {hostname}')
        child_span.finish()

        child_span = opentracing.tracer.start_span('read_stderr', child_of=span)
        error = cls.get_full_response(stderr.channel)
        child_span.finish()
        cls.logger.debug(f'Completed read of error from Linux Host {hostname}')
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
