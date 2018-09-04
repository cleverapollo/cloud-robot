"""File containing some utility functions such as generating our logger"""
# python
import influxdb
import logging
import logging.handlers
import subprocess
import sys
from datetime import datetime
from multiprocessing import Queue
from threading import Thread
from traceback import print_exc

# libs
import jinja2
from cloudcix.utils import get_admin_session


__all__ = [
    'jinja_env',
    'Token',
    'get_logger_for_name',
    'get_current_git_sha',
    'get_influx_client',
]


INFLUX_CLIENT = None

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('templates'),
    trim_blocks=True,
)

logger = None


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
                f'Generated new token: {old_token} -> {self._token}',
            )
        return self._token


class MultiprocessingHandler(logging.Handler):
    """
    Log handler capable of dealing with logging messages from different processes to the stdout of the parent process
    """

    def __init__(self):
        logging.Handler.__init__(self)

        # Keep an actual handler to log stuff out
        self._handler = logging.StreamHandler()
        self.queue = Queue(-1)

        # Create the thread that manages the multiprocessing stuff
        thread = Thread(target=self.receive)
        thread.daemon = True
        thread.start()

    def set_formatter(self, fmt: logging.Formatter):
        """
        Set the formatter for both this handler and the internal one
        """
        logging.Handler.setFormatter(self, fmt)
        self._handler.setFormatter(fmt)

    def receive(self):
        """
        Receive messages from the queue and emit them using the internal handler
        """
        while True:
            try:
                record = self.queue.get()
                self._handler.emit(record)
            except (KeyboardInterrupt, SystemExit):
                raise
            except EOFError:
                break
            except Exception:
                print_exc(file=sys.stderr)

    def send(self, s: logging.LogRecord):
        """
        Take in a log message and put it in the queue
        """
        self.queue.put_nowait(s)

    def _format_record(self, record: logging.LogRecord):
        """
        Format the message using the formatter for the handler
        """
        if record.args:
            record.msg = record.msg % record.args
            record.args = None
        if record.exc_info:
            self.format(record)
            record.exc_info = None
        return record

    def emit(self, record: logging.LogRecord):
        """
        Emit the record by formatting it and then adding it to the queue
        """
        try:
            self.send(self._format_record(record))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)

    def close(self):
        """
        Close the internal handler first before closing this one
        """
        self._handler.close()
        logging.Handler.close(self)


def get_logger_for_name(name: str, level=logging.DEBUG) -> logging.Logger:
    """
    Generates logging.logger instance with a given name

    :param name: The name to be given to the logger instance
    :param level: The level of the logger. Defaults to `logging.INFO`
    :return: A logger than can be used to log out to
             `/var/log/robot/robot.log`
    """
    global logger
    if logger is not None:
        return logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    fmt = logging.Formatter(
        fmt='%(asctime)s - %(name)s: %(levelname)s: %(message)s',
        datefmt='%d/%m/%y @ %H:%M:%S',
    )
    # handler = logging.handlers.RotatingFileHandler(
    #     f'/var/log/robot/robot.log',
    #     maxBytes=1024 ** 3,
    #     backupCount=7,
    # )
    handler = MultiprocessingHandler()
    handler.set_formatter(fmt)
    handlers_for_name[name] = handler
    logger.addHandler(handler)
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


def get_influx_client() -> influxdb.InfluxDBClient:
    """
    Lazy creates a client for connecting to our InfluxDB instance
    :return: An InfluxDBClient that can log metrics to our instance of Influx
    """
    global INFLUX_CLIENT
    if INFLUX_CLIENT is None:
        INFLUX_CLIENT = influxdb.InfluxDBClient(
            host='influx.cloudcix.com',
            port=80,
            database='robot',
        )
    return INFLUX_CLIENT
