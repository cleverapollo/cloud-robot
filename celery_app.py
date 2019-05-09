"""
Celery main runner
"""
# stdlib
import atexit
from datetime import timedelta
# lib
from celery import Celery
from celery.schedules import crontab
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
        'schedule': timedelta(seconds=20),  # every 20 seconds
    },
}

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
    # Just ensure the root logger is set up
    utils.setup_root_logger()
    app.start()
