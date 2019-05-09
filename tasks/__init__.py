"""
Module containing all of the non beat celery tasks

In this file, we define the robot based tasks that will be run by celery beat
"""
# stdlib
from datetime import datetime, timedelta
# local
import settings
from celery_app import app
from robot import Robot


@app.task
def mainloop():
    """
    Run one instance of the Robot mainloop
    """
    robot = Robot.get_instance()
    robot()


@app.task
def scrub_loop():
    """
    Once per day, at midnight, call the robot scrub methods to delete hardware
    """
    robot.logger.info('Commencing scrub task')
    # Add the Scrub timestamp when the region isn't Alpha
    timestamp = None
    # if settings.REGION_NAME != 'alpha':
    #     timestamp = (datetime.now() - timedelta(days=30)).isoformat()
    robot = Robot.get_instance()
    robot.vrf_scrub(timestamp)
    robot.vm_scrub(timestamp)
