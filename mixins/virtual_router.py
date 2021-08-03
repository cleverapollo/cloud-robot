"""
mixin class containing methods that are needed by VirtualRouter task classes
methods included;
    - method to get management ip and router model since they're not currently easy
    - method to get port data since that's not currently easy either
"""
# stdlib
import logging
from time import asctime, sleep
from typing import List, Tuple
# lib
from jnpr.junos import Device
from jnpr.junos.exception import (
    CommitError,
    ConfigLoadError,
    ConnectError,
    LockError,
    RpcError,
    UnlockError,
)
from jnpr.junos.utils.config import Config


__all__ = [
    'VirtualRouterMixin',
]

MAX_ATTEMPTS = 10


class VirtualRouterMixin:
    logger: logging.Logger

    @classmethod
    def deploy(cls, setconf: str, management_ip: str, ignore_missing: bool = False) -> Tuple[bool, List[str]]:
        """
        Deploy the generated configuration to the Router and return whether or not the deployment succeeded
        :param setconf: The configuration for the virtual router
        :param management_ip: The ip of the physical router to deploy to
        :param ignore_missing: Flag stating whether or not we should ignore the `statement not found` error
        :return: A flag stating whether or not the deployment was successful
        :return errors: list of errors occurred while deploying config
        """
        cls.logger.debug(f'Attempting to connect to Router {management_ip} to deploy')
        errors: List[str] = []
        try:
            # Using context managers for Router and Config will ensure everything is properly cleaned up when exiting
            # the function, regardless of how we exit the function
            with Device(host=management_ip, user='robot', ssh_private_key_file='~/.ssh/id_rsa', port=22) as router:
                router.timeout = 15 * 60  # 15 minute timeout
                cls.logger.debug(f'Successfully connected to Router {management_ip}, now attempting to load config')
                # If a large commit is in process this can take close to 10 minutes to complete on some SRX's.
                # If a LockError is raised we will increase the sleep time each time.
                # Try to commit up to 10 times which will result in a max sleep time of 486 secs (8mins 6secs)
                for attempt in range(MAX_ATTEMPTS):
                    try:
                        return cls._configure(setconf, management_ip, router, ignore_missing)
                    except LockError:
                        cls.logger.warning(
                            f'Unable to lock config on Router {management_ip}. Attempt #{attempt + 1} / {MAX_ATTEMPTS}',
                            exc_info=True,
                        )
                        if attempt < MAX_ATTEMPTS - 1:
                            # Do not need to sleep after last attempt
                            sleep(30 + (6 * attempt))
                cls.logger.error(
                    f'{MAX_ATTEMPTS} attempts to lock Router {management_ip} have failed. This request is now '
                    'considered a failure.',
                )
                return False, errors
        except ConnectError as err:
            error = f'Unable to connect to Router {management_ip}.'
            errors.append(f'{error} Error: {err}')
            cls.logger.error(error, exc_info=True)
            return False, errors

    @classmethod
    def _configure(
            cls,
            setconf: str,
            management_ip: str,
            router: Device,
            ignore_missing: bool,
    ) -> Tuple[bool, List[str]]:
        """
        Open the configuration for the router and attempt to deploy to the router.
        This has been turned into a method to make it easier to repeat this function multiple times.
        :param setconf: The configuration for the virtual router
        :param management_ip: The ip of the physical router to deploy to
        :param router: A Device object representing the Router being configured.
        :param ignore_missing: Flag stating whether or not we should ignore the `statement not found` error
        :return: A flag stating whether or not the deployment was successful
        :return errors: list of errors occurred while deploying config
        """
        errors: List[str] = []
        with Config(router, mode='exclusive') as config:
            try:
                config.load(setconf, format='set', merge=True, ignore_warning=ignore_missing)
            except ConfigLoadError as err:
                # Reduce device timeout so we're not waiting forever for it to close config
                router.timeout = 2 * 60
                error = f'Unable to load configuration changes onto Router {management_ip}.'
                cls.logger.error(error, exc_info=True)
                errors.append(f'{error} Error: {err}')
                return False, errors

            # Attempt to commit
            try:
                commit_msg = f'Loaded by robot at {asctime()}.'
                cls.logger.debug(
                    f'All commands successfully loaded onto Router {management_ip}, now checking the commit status',
                )
                # Commit check either raises an error or returns True
                config.commit_check()
                cls.logger.debug(f'Commit check on Router {management_ip} successful, committing changes.')
                if not ignore_missing:
                    detail = config.commit(comment=commit_msg)
                else:
                    detail = config.commit(comment=commit_msg, ignore_warning=['statement not found'])
                cls.logger.debug(f'Response from commit on Router {management_ip}\n{detail}')
            except CommitError as err:
                error = f'Unable to commit changes onto Router {management_ip}.'
                cls.logger.error(error, exc_info=True)
                errors.append(f'{error} Error: {err}')

                # Rollback loaded changes, No need to commit.
                try:
                    config.rollback()
                    cls.logger.debug(f'Successfully rolled back the configuration on Router {management_ip}.')
                except RpcError as err:
                    error = f'Unable to rollback configuration changes onto Router {management_ip}, Please inform NOC.'
                    cls.logger.error(error, exc_info=True)
                    errors.append(f'{error} Error: {err}')

                # Unlock the Router
                try:
                    config.unlock()
                    cls.logger.debug(f'Successfully unlocked the Router {management_ip}.')
                except UnlockError as err:
                    error = f'Unable to unlock the Router {management_ip}, Please inform NOC.'
                    cls.logger.error(error, exc_info=True)
                    errors.append(f'{error} Error: {err}')

                # Reduce device timeout so we're not waiting forever for it to close config
                router.timeout = 2 * 60
                return False, errors
            return True, errors
