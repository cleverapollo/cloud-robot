"""
Celery main runner
"""
# lib
from celery import Celery
# local
import utils


__all__ = [
    'app',
]


app = Celery(
    'robot',
    broker='amqp://task-queue',
    include=['.tasks'],
)
# Optional config

# Run the app if this is the main script
if __name__ == '__main__':
    # Just ensure the root logger is set up
    utils.setup_root_logger()
    app.start()
