# stdlib
import logging
import time
# lib
from cloudcix.api.iaas import IAAS
from cloudcix_token import Token
# local
import metrics
from celery_app import setup_logger_and_tracer
from robot import Robot

__all__ = [
    'mainloop',
]


def run_robot_get():
    """
    Gets response from run robot get api request
    """
    logger = logging.getLogger('robot.mainloop.run_robot_get')
    # send run_robot list request
    try:
        response = IAAS.run_robot.list(token=Token.get_instance().token)
        # Token expire error "detail":"JWT token is expired. Please login again."
        if response.status_code == 401 and 'token is expired' in response.json()['detail']:
            run_robot_get()
        if response.status_code != 200:
            logger.error(
                f'HTTP {response.status_code} error occurred when attempting to fetch run_robot _metadata;\n'
                f'Response Text: {response.content.decode()}',
            )
            return None
        # 200, run_robot is True, call Robot
        # check for empty list right here
        project_ids = response.json()['content']['project_ids']
        if len(project_ids) > 0:
            logger.debug(
                f'HTTP {response.status_code}, There are changes in the region so call for Robot instance;\n',
            )
            return response.json()['content']
        else:
            return None
    except Exception:
        logger.error(f'Failed to make request to IAAS.run_robot.list service.', exc_info=True)
        return None


def run_robot_post(project_ids):
    """
    Sends project_ids list in request to run robot post api to reset run_robot.
    """
    logger = logging.getLogger('robot.mainloop.run_robot_post')
    # send run_robot post request
    data = {'project_ids': project_ids}
    response = IAAS.run_robot.create(token=Token.get_instance().token, data=data)
    # Token expire error "detail":"JWT token is expired. Please login again."
    if response.status_code == 401 and 'token is expired' in response.json()['detail']:
        run_robot_post(project_ids)
    if response.status_code != 200:
        logger.error(
            f'HTTP {response.status_code} error occurred when attempting to reset run_robot for project_ids '
            f'#{project_ids};\nResponse Text: {response.content.decode()}',
        )
    # 200, run_robot reset successful.
    logger.debug(f'HTTP {response.status_code}, Acknowledged to reset run_robot for project_ids # {project_ids}.')


def mainloop():
    """
    Run once 'while mainloop' at the start.
    """
    # setup logging and tracing
    setup_logger_and_tracer()

    while True:
        # Send info about up-time
        metrics.heartbeat()
        logger = logging.getLogger('robot.mainloop')
        logger.info('Mainloop check')
        logger.debug(f'Fetching the status of run_robot from api.')
        data = run_robot_get()
        if data is not None:
            project_ids = data['project_ids']
            virtual_routers = data['virtual_routers']
            vms = data['vms']

            # data found for Robot so is waking up and preparing for run.
            logger.debug(f'Robot so is waking up and preparing for run.')

            robot = Robot(virtual_routers, vms)
            robot()
            # Robot started run
            logger.debug(f'Initiating Robot for run.')

            run_robot_post(project_ids)
            # acknowledge run_robot to reset requested projects
            logger.debug(f'Acknowledged run_robot api that requested projects id # {project_ids} are dispatched.')
        else:
            logger.debug(f'No changes found for Robot so is going back to sleep for 60 seconds.')
            # No changes in region, Robot going to sleep for 1 min.
            time.sleep(60)


# mainloop starting point
if __name__ == '__main__':
    mainloop()
