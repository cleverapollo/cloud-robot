"""File containing some utility functions such as generating our logger"""
# python
import logging
import logging.handlers
import subprocess
from datetime import datetime
# libs
import jinja2
from cloudcix.auth import get_admin_token
from logstash_async.handler import AsynchronousLogstashHandler


__all__ = [
    'get_current_git_sha',
    'get_logger_for_name',
    'jinja_env',
    'setup_root_logger',
    'Token',
]

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('templates'),
    trim_blocks=True,
)


class Token:
    """Wrapper for CloudCIX token that renews itself when necessary"""

    THRESHOLD = 40  # Minutes a token has lived until we get a new one

    def __init__(self):
        self._token = get_admin_token()
        self._created = datetime.now()

    @property
    def token(self):
        """Ensures that the token is up to date"""
        if (datetime.now() - self._created).seconds / 60 > self.THRESHOLD:
            # We need to regenerate the token
            old_token = self._token
            self._token = get_admin_token()
            self._created = datetime.now()
            get_logger_for_name('utils.Token').info(
                f'Generated new token: {old_token} -> {self._token}',
            )
        return self._token


def setup_root_logger():
    """
    Called at startup.
    Sets up the proper handlers on the root logger which allows all other loggers to propogate messages to it
    instead of having that old bad system
    """
    logger = logging.getLogger()
    fmt = logging.Formatter(
        fmt='%(asctime)s - %(name)s: %(levelname)s: %(message)s',
        datefmt='%d/%m/%y @ %H:%M:%S',
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)
    logstash_handler = AsynchronousLogstashHandler('logstash.cloudcix.com', 5959, ':memory:')
    logstash_handler.setFormatter(fmt)
    logger.addHandler(logstash_handler)


def get_logger_for_name(name: str, level=logging.DEBUG) -> logging.Logger:
    """
    Generates logging.logger instance with a given name

    :param name: The name to be given to the logger instance
    :param level: The level of the logger. Defaults to `logging.INFO`
    :return: A logger than can be used to log out to stdout
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


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
