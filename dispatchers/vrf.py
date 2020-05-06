# stdlib
import logging
from datetime import datetime, timedelta
# local
import tasks
from tasks import vrf as vrf_tasks


class Vrf:
    """
    A class that handles 'dispatching' a VRF to various services such as builders, scrubbers, etc.
    """

    # Network password used to login to the routers
    password: str

    def __init__(self, password: str):
        self.password = password

    def build(self, vrf_id: int):
        """
        Dispatches a celery task to build the specified vrf
        :param vrf_id: The id of the VRF to build
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vrf.build').debug(
            f'Passing VRF #{vrf_id} to the build task queue',
        )
        vrf_tasks.build_vrf.delay(vrf_id)
        # Reset debug logs of firewall rules after 15min
        logging.getLogger('robot.dispatchers.vrf.debug_logging').debug(
            f'Passing VRF #{vrf_id} to the debug_logs task queue after vrf build',
        )
        tasks.debug.s(vrf_id).apply_async(eta=datetime.now() + timedelta(seconds=15 * 60))

    def quiesce(self, vrf_id: int):
        """
        Dispatches a celery task to quiesce the specified vrf
        :param vrf_id: The id of the VRF to quiesce
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vrf.quiesce').debug(
            f'Passing VRF #{vrf_id} to the quiesce task queue',
        )
        vrf_tasks.quiesce_vrf.delay(vrf_id)

    def restart(self, vrf_id: int):
        """
        Dispatches a celery task to restart the specified vrf
        :param vrf_id: The id of the VRF to restart
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vrf.restart').debug(
            f'Passing VRF #{vrf_id} to the restart task queue',
        )
        vrf_tasks.restart_vrf.delay(vrf_id)

    def scrub(self, vrf_id: int):
        """
        Dispatches a celery task to scrub the specified vrf
        :param vrf_id: The id of the VRF to scrub
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vrf.scrub').debug(
            f'Passing VRF #{vrf_id} to the scrub task queue',
        )
        vrf_tasks.scrub_vrf.delay(vrf_id)

    def update(self, vrf_id: int):
        """
        Dispatches a celery task to update the specified vrf
        :param vrf_id: The id of the VRF to update
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vrf.update').debug(
            f'Passing VRF #{vrf_id} to the update task queue',
        )
        vrf_tasks.update_vrf.delay(vrf_id)
        # Reset debug logs of firewall rules after 15min
        logging.getLogger('robot.dispatchers.vrf.debug_logging').debug(
            f'Passing VRF #{vrf_id} to the debug_logs task queue after vrf update',
        )
        tasks.debug.s(vrf_id).apply_async(eta=datetime.now() + timedelta(seconds=15 * 60))
