import time
import utils
from jnpr.junos import Device
from jnpr.junos.exception import (
    CommitError,
    ConfigLoadError,
    LockError,
    UnlockError,
)
from jnpr.junos.utils.config import Config

driver_logger = utils.get_logger_for_name('srx_vrf_builder.deploy_setconf')

# TODO not yet fixed


def vrf_build(vrf: dict, password: str) -> bool:
    """
    Builds Virtual Routing and Forwarding (VRF) in corresponding Router,
    so it first prepares set commands and paramiko-s into router and executes
    the set commands
    :param vrf: Information used to build the VRF
    :param password: Password for the robot user in the physical router
    :return: Flag stating whether or not the build was successful
    """
    driver_logger.info(
        f'Generating configuration for project #{vrf["idProject"]}'
    )
    template = utils.jinja_env.get_template('srx_set_conf.j2')
    conf = template.render(**vrf)

    # IKE VPNs TODO

    vrf_status = deploy_setconf(conf, vrf['oobIP'], password)
    return vrf_status


#########################################################
#   Deploy setconf to Router                            #
#########################################################
def deploy_setconf(setconf: str, ip: str, password: str) -> bool:
    """
    Deploy the configuration generated by vrf_build to the actual router
    :param setconf: The configuration generated by vrf_build
    :param ip: The ip_address of the router to install the conf on
    :param password: The password for the 'robot' user of the router
    :return: Flag stating whether or not the build was successful
    """
    success = False
    # Open Router
    driver_logger.info(
        f'Attempting to connect to router @ {ip}'
    )
    dev = Device(host=ip, user='robot', password=password, port=22)
    cu = Config(dev)
    try:
        dev.open()
    except Exception:
        driver_logger.error(
            f'Unable to connect to router @ {ip}',
            exc_info=True
        )
        return success
    # Lock Router
    driver_logger.info(
        f'Successfully connected to router @ {ip}.'
        f' Attempting to lock router to apply configuration'
    )
    try:
        cu.lock()
    except LockError:
        driver_logger.error(
            f'Unable to lock router @ {ip}',
            exc_info=True,
        )
        dev.close()
        return success

    # Load Configuration
    driver_logger.info(
        f'Successfully locked router @ {ip}. '
        f'Now attempting to apply configuration.'
    )
    try:
        for cmd in setconf.split('\n'):
            driver_logger.debug(
                f'Attempting to run "{cmd}" on the router.'
            )
            cu.load(cmd, format='set', merge=True)
    except (ConfigLoadError, Exception):
        driver_logger.error(
            f'Unable to load configuration changes on router @ {ip}.',
            exc_info=True
        )
        driver_logger.info(
            f'Attempting to unlock configuration on router @ {ip} '
            f'after exception'
        )
        try:
            cu.unlock()
        except UnlockError:
            driver_logger.error(
                f'Unable to unlock configuration on router @ {ip}',
                exc_info=True
            )
        dev.close()
        return success

    # Commit Configuration
    driver_logger.info(
        f'All commands loaded successfully onto router @ {ip}. '
        f'Attempting to commit the changes'
    )
    try:
        cu.commit(comment=f'Loaded by robot at {time.asctime()}.')
        success = True
    except CommitError:
        driver_logger.error(
            f'Unable to commit changes onto router @ {ip}',
            exc_info=True
        )
        return success
    driver_logger.info(
        f'Attempting to unlock configuration on router @ {ip}'
    )
    try:
        cu.unlock()
    except UnlockError:
        driver_logger.error(
            f'Unable to unlock configuration on router @ {ip}',
            exc_info=True
        )
        dev.close()
    return success
