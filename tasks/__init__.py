"""
Module containing all of the non beat celery tasks

In this file, we define the robot based tasks that will be run by celery beat
"""
# stdlib
import logging
from datetime import datetime, timedelta
# lib
from cloudcix.api import IAAS
# local
import settings
import utils
from celery_app import app
from cloudcix_token import Token
from robot import Robot
from .vrf import debug_logs


@app.task
def mainloop():
    """
    Run one instance of the Robot mainloop if any changes in any Project of the region.
    """
    logger = logging.getLogger('tasks.mainloop')
    response = IAAS.run_robot.head(token=Token.get_instance().token)
    if response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to fetch run_robot _metadata;\n'
            f'Response Text: {response.content.decode()}',
        )
        return None
    run_robot = response.json()['_metadata']['run_robot']
    if run_robot:
        robot = Robot.get_instance()
        robot()


@app.task
def scrub():
    """
    Once per day, at midnight, call the robot scrub methods to delete hardware
    """
    # Add the Scrub timestamp when the region isn't Alpha
    timestamp = None
    if settings.IN_PRODUCTION:
        timestamp = (datetime.now() - timedelta(days=7)).isoformat()
    robot = Robot.get_instance()
    robot.scrub(timestamp)


@app.task
def debug(vrf_id: int):
    """
    Waits for 15 min from the time latest updated or created for Firewall rules to reset the debug_logging field
    for all firewall rules of a Virtual router
    """
    logging.getLogger('robot.tasks.debug').debug(
        f'Checking VRF #{vrf_id} to pass to the debug task queue',
    )
    virtual_router = utils.api_read(IAAS.vrf, vrf_id)
    if virtual_router is None:
        return
    firewall_rules = virtual_router['firewall_rules']
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
            f'Passing VRF #{vrf_id} to the debug_logs task queue',
        )
        debug_logs.delay(vrf_id)
