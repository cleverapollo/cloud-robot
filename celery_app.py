"""
Celery main runner
"""
# stdlib
import atexit
# lib
from celery import Celery
from jaeger_client import Config
# local
import settings
import utils


__all__ = [
    'app',
    'tracer',
]


app = Celery(
    'robot',
    broker='amqp://task-queue',
    include=['.tasks'],
)
# Optional config

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
    # Just ensure the root logger is set up
    utils.setup_root_logger()
    app.start()
