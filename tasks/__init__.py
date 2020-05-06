"""
Module containing all of the non beat celery tasks

In this file, we define the robot based tasks that will be run by celery beat
"""
# stdlib
from datetime import datetime, timedelta
# lib
from cloudcix.api import IAAS
# local
import settings
import utils
from celery_app import app
from robot import Robot
from .vrf import debug_logs_task


@app.task
def mainloop():
    """
    Run one instance of the Robot mainloop
    """
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
def debug_logs(vrf_id: int):
    """
    Waits for 15 min from the time latest updated or created for Firewall rules to reset the debug_logging field
    for all firewall rules of a Virtual router
    """
    virtual_router = utils.api_read(IAAS.vrf, vrf_id)
    if virtual_router is None:
        return
    firewall_rules = virtual_router['firewall_rules']
    if len(firewall_rules) == 0:
        return
    list_updated = [firewall_rule['updated'] for firewall_rule in firewall_rules]
    # Find the latest updated firewall
    now = datetime.now()
    latest = max(list_updated)
    # compare with 15 min
    delta = now - latest
    if delta >= timedelta(minutes=15):
        debug_logs_task.delay(vrf_id)
