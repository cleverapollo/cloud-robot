"""File containing some utility functions such as generating our logger"""
# python
import logging
import logging.handlers
import subprocess
# libs
# local


def get_logger_for_name(name: str, level=logging.INFO) -> logging.Logger:
    """
    Generates logging.logger instance with a given name

    :param name: The name to be given to the logger instance
    :param level: The level of the logger. Defaults to `logging.INFO`
    :returns: A logger than can be used to log out to
              `/var/log/robot/robot.log`
    """
    fmt = logging.Formatter(
        fmt="%(asctime)s - %(name)s: %(levelname)s: %(message)s",
        datefmt="%d/%m/%y @ %H:%M:%S"
    )
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # Get a file handler
    handler = logging.handlers.RotatingFileHandler(
        '/var/log/robot/robot.log',
        maxBytes=4096,
        backupCount=7
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger


def get_current_git_sha() -> str:
    """
    Finds the current git commit sha and returns it
    """
    return subprocess.check_output(
        ['git', 'describe', '--always']
    ).strip().decode()
