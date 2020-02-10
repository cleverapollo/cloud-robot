# stdlib
import logging
# local
from tasks import vr as vr_tasks


class Vr:
    """
    A class that handles 'dispatching' a VR to various services such as builders, scrubbers, etc.
    """

    # Network password used to login to the routers
    password: str

    def __init__(self, password: str):
        self.password = password

    def build(self, vr_id: int):
        """
        Dispatches a celery task to build the specified vr
        :param vr_id: The id of the VR to build
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vr.build').debug(
            f'Passing VR #{vr_id} to the build task queue',
        )
        vr_tasks.build_vr.delay(vr_id)

    def quiesce(self, vr_id: int):
        """
        Dispatches a celery task to quiesce the specified vr
        :param vr_id: The id of the VR to quiesce
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vr.quiesce').debug(
            f'Passing VR #{vr_id} to the quiesce task queue',
        )
        vr_tasks.quiesce_vr.delay(vr_id)

    def restart(self, vr_id: int):
        """
        Dispatches a celery task to restart the specified vr
        :param vr_id: The id of the VR to restart
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vr.restart').debug(
            f'Passing VR #{vr_id} to the restart task queue',
        )
        vr_tasks.restart_vr.delay(vr_id)

    def scrub(self, vr_id: int):
        """
        Dispatches a celery task to scrub the specified vr
        :param vr_id: The id of the VR to scrub
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vr.scrub').debug(
            f'Passing VR #{vr_id} to the scrub task queue',
        )
        vr_tasks.scrub_vr.delay(vr_id)

    def update(self, vr_id: int):
        """
        Dispatches a celery task to update the specified vr
        :param vr_id: The id of the VR to update
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.vr.update').debug(
            f'Passing VR #{vr_id} to the update task queue',
        )
        vr_tasks.update_vr.delay(vr_id)
