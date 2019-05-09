"""
Celery main runner
"""
# stdlib
import atexit
import time
# lib
from celery import Celery
from celery.schedules import crontab
from celery.signals import task_prerun, task_postrun
from jaeger_client import Config
# local
import metrics
import settings
import utils

__all__ = [
    'app',
    'tracer',
]


app = Celery(
    'robot',
    broker=f'amqp://[{settings.CELERY_HOST}]:5672',
    include=['tasks'],
)
# Optional config
app.conf.timezone = 'Europe/Dublin'

# Add cron based jobs
app.conf.beat_schedule = {
    'scrub-at-midnight': {
        'task': 'tasks.scrub_loop',
        'schedule': crontab(minute=0, hour=0),  # daily at midnight, like Jerry asked
    },
    'mainloop': {
        'task': 'tasks.mainloop',
        'schedule': crontab(),  # every minute
    },
}

# Ensure the loggers are set up before each task is run
@task_prerun.connect
def setup_logger(*args, **kwargs):
    """
    Set up the logger before each task is run, in the hopes that it will fix our logging issue
    """
    # Just ensure the root logger is set up
    utils.setup_root_logger()

# Sleep after each task to try and flush spans
@task_postrun.connect
def sleep_to_flush_spans(*args, **kwargs):
    """
    Flush spans by passing to IO loop, just to be safe
    """
    time.sleep(5)

# Jaeger tracer
tracer = Config(
    config={
        'logging': True,
        'sampler': {
            'type': 'const',
            'param': 1,
        },
    },
    service_name=f'robot_{settings.REGION_NAME}',
    validate=True,
).initialize_tracer()
# Close the tracer at exit
atexit.register(tracer.close)

# Run the app if this is the main script
if __name__ == '__main__':
    if settings.ROBOT_ENV != 'dev':
        metrics.current_commit()
    app.start()
