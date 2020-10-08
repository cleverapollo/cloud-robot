"""
Module containing all of the non beat celery tasks

In this file, we define the robot based tasks that will be run by celery beat
"""
# stdlib
import logging
from datetime import datetime, timedelta
# lib
from cloudcix.api.iaas import IAAS
# local
import metrics
import utils
from celery_app import app
from cloudcix_token import Token
from robot import Robot
from settings import IN_PRODUCTION
from .virtual_router import debug_logs


@app.task
def mainloop():
    """
    Run one instance of the Robot mainloop
    """
    # Send info about uptime
    metrics.heartbeat()
    logger = logging.getLogger('robot.tasks.mainloop')
    logger.info('Mainloop task check')
    logger.debug(
        f'Fetching the status of run_robot from api.',
    )
    response = IAAS.run_robot.head(token=Token.get_instance().token)
    if response.status_code == 404:
        logger.debug(
            f'HTTP {response.status_code}, No Project has changed in region so Robot is sleeping.',
        )
        # 404, run_robot is False so nothing to do.
        return None
    if response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch run_robot _metadata;\n'
            f'Response Text: {response.content.decode()}',
        )
        return None
    # 200, run_robot is True
    logger.debug(
        f'HTTP {response.status_code}, There are changes in the region so calling Robot instance.',
    )
    robot = Robot.get_instance()
    robot()


@app.task
def scrub():
    """
    Once per day, at midnight, call the robot scrub methods to delete hardware
    """
    # Add the Scrub timestamp when the region isn't Alpha
    timestamp = None
    if IN_PRODUCTION:
        timestamp = (datetime.now() - timedelta(days=7)).isoformat()
    robot = Robot.get_instance()
    robot.scrub(timestamp)


@app.task
def debug(virtual_router_id: int):
    """
    Waits for 15 min from the time latest updated or created for Firewall rules to reset the debug_logging field
    for all firewall rules of a Virtual router
    """
    logging.getLogger('robot.tasks.debug').debug(
        f'Checking Virtual Router #{virtual_router_id} to pass to the debug task queue',
    )
    virtual_router_data = utils.api_read(IAAS.virtual_router, virtual_router_id)
    if virtual_router_data is None:
        return
    firewall_rules = virtual_router_data['firewall_rules']
    if len(firewall_rules) == 0:
        return
    list_updated = [firewall_rule['updated'] for firewall_rule in firewall_rules]
    # Find the latest updated firewall
    latest = max(list_updated)
    # format latest string and convert to a datetime
    latest = latest.split('+')[0]  # removing timezone info
    '2020-04-30T08:51:04.454033'
    latest_dt = datetime.strptime(latest, '%Y-%m-%dT%H:%M:%S.%f')
    # compare with 15 min from utc now time
    utc_now = datetime.utcnow()
    delta = utc_now - latest_dt
    if delta >= timedelta(minutes=15):
        logging.getLogger('robot.tasks.debug').debug(
            f'Passing virtual_router #{virtual_router_id} to the debug_logs task queue',
        )
        debug_logs.delay(virtual_router_id)
