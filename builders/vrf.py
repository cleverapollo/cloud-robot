# python
import time

# libs
from jnpr.junos import Device
from jnpr.junos.exception import CommitError, ConfigLoadError, ConnectError, LockError, UnlockError
from jnpr.junos.utils.config import Config

# locals
import utils


class Vrf:

    logger = utils.get_logger_for_name('builders.vrf')

    @staticmethod
    def build(vrf: dict, password: str) -> bool:
        """
        Using the JunOS python library, this method attempts to build a Virtual Router in a Physical Router using the
        config passed in from the dispatcher, and reports back to the dispatcher whether or not the build succeeded
        :param vrf: The VRF data generated by the dispatcher
        :param password: The network password for connecting to the router
        :return: A flag stating whether the build succeeded or not
        """
        Vrf.logger.info(f'Generating JunOS setconf for VRF for Project #{vrf["idProject"]}')
        conf = utils.jinja_env.get_template('srx_set_conf.j2').render(**vrf)
        # Log the setconf to Debug
        Vrf.logger.debug(f'Generated setconf for Project #{vrf["idProject"]}\n{conf}')
        # Deploy the generated config into the physical router
        return Vrf.deploy(conf, vrf['oob_ip'], password)

    @staticmethod
    def deploy(conf: str, ip: str, password: str) -> bool:
        """
        Deploy the configuration contained in 'conf' to the router at 'ip' and return a flag stating whether or not the
        deployment was successful
        :param conf: The configuration for the virtual router
        :param ip: The ip of the physical router to deploy to
        :param password: The password to connect to the router with
        :return: A flag stating whether or not the deployment was successful
        """
        # Connect to the Router
        Vrf.logger.info(f'Attempting to connect to Physical Router @ {ip}')
        dev = Device(host=ip, user='robot', password=password, port=22)
        cfg = Config(dev)
        try:
            dev.open()
            # Set the RPC timeout to be 2 minutes
            dev.timeout = 60 * 2
        except ConnectError:
            Vrf.logger.error(f'Unable to connect to router @ {ip}', exc_info=True)
            return False
        Vrf.logger.info(f'Successfully connected to router @ {ip}, now attempting to lock router')
        try:
            cfg.lock()
        except LockError:
            Vrf.logger.error(f'Unable to lock configuration in router @ {ip}', exc_info=True)
            return False
        Vrf.logger.info(f'Successfully locked config in router @ {ip}, now attempting to apply config')
        try:
            for cmd in conf.split('\n'):
                Vrf.logger.debug(f'Attempting to run "{cmd}" on router @ {ip}')
                cfg.load(cmd, format='set', merge=True)
        except ConfigLoadError:
            Vrf.logger.error(f'Unable to load configuration changes onto router @ {ip}', exc_info=True)
            # Try to unlock after failing to load
            Vrf.logger.info(f'Attempting to unlock configuration after error on router @ {ip}')
            try:
                cfg.unlock()
            except UnlockError:
                Vrf.logger.error(f'Unable to unlock configuration after error on router @ {ip}', exc_info=True)
            dev.close()
            return False

        # Attempt to commit
        Vrf.logger.info(f'All commands successfully loaded onto router @ {ip}, now attempting to commit changes')
        try:
            cfg.commit(comment=f'Loaded by robot at {time.asctime()}.')
        except CommitError:
            Vrf.logger.error(f'Unable to commit changes onto router @ {ip}', exc_info=True)
            return False
        except Exception:
            Vrf.logger.error(
                f'There is a non-critical exception arose during committing changes onto router @ {ip}',
                exc_info=True,
            )
        Vrf.logger.info(f'Changes successfully committed onto router @ {ip}, now attempting to unlock config')
        try:
            cfg.unlock()
        except UnlockError:
            Vrf.logger.error(f'Unable to unlock configuration after successful commit on router @ {ip}', exc_info=True)
            dev.close()
        return True
