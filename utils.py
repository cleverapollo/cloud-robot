"""File containing some utility functions such as generating our logger"""
# python
import logging
import logging.handlers
import subprocess
from datetime import datetime

# libs
import jinja2
from cloudcix.utils import get_admin_session

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('templates'),
    trim_blocks=True
)
# Maps names to a handler to prevent creating multiple handlers
handlers_for_name = {}


def get_logger_for_name(name: str, level=logging.INFO) -> logging.Logger:
    """
    Generates logging.logger instance with a given name

    :param name: The name to be given to the logger instance
    :param level: The level of the logger. Defaults to `logging.INFO`
    :returns: A logger than can be used to log out to
              `/var/log/robot/robot.log`
    """
    global handlers_for_name
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Get a file handler
    if name not in handlers_for_name:
        fmt = logging.Formatter(
            fmt='%(asctime)s - %(name)s: %(levelname)s: %(message)s',
            datefmt='%d/%m/%y @ %H:%M:%S'
        )
        handler = logging.handlers.RotatingFileHandler(
            '/var/log/robot/robot.log',
            maxBytes=1024 ** 3,
            backupCount=7
        )
        handler.setFormatter(fmt)
        handlers_for_name[name] = handler
    else:
        handler = handlers_for_name[name]
    logger.addHandler(handler)
    return logger


def get_current_git_sha() -> str:
    """
    Finds the current git commit sha and returns it
    """
    return subprocess.check_output(
        ['git', 'describe', '--always']
    ).strip().decode()


class Token:
    """Wrapper for CloudCIX token that renews itself when necessary"""

    THRESHOLD = 40  # Minutes a token has lived until we get a new one

    def __init__(self):
        self._token = get_admin_session().get_token()
        self._created = datetime.now()

    @property
    def token(self):
        """Ensures that the token is up to date"""
        if (datetime.now() - self._created).seconds / 60 > self.THRESHOLD:
            # We need to regenerate the token
            old_token = self._token
            self._token = get_admin_session().get_token()
            self._created = datetime.now()
            get_logger_for_name('utils.Token').info(
                f'Generated new token: {old_token} -> {self._token}'
            )
        return self._token
