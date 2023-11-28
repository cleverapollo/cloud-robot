# stdlib
import logging
# local
from tasks import ceph as ceph_tasks


class Ceph:
    """
    A class that handles 'dispatching' a Ceph to various services such as builders, scrubbers, etc.
    """

    # Network password used to log into the routers
    password: str

    def __init__(self, password: str):
        self.password = password

    def build(self, ceph_id: int):
        """
        Dispatches a celery task to build the specified Ceph drive
        :param ceph_id: The id of the Ceph drive to build
        """
        # log a message about the dispatch, and pass the request to celery
        logging.getLogger('robot.dispatchers.ceph.build').debug(f'Passing ceph #{ceph_id} to the build task queue.')
        ceph_tasks.build_ceph.delay(ceph_id)
