"""
mixin class containing methods that are needed by vrf task classes
methods included;
    - method to get management ip and router model since they're not currently easy
    - method to get port data since that's not currently easy either
"""
# stdlib
import logging
from time import asctime, sleep
from typing import Dict, Optional, Union
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
from jnpr.junos import Device
from jnpr.junos.exception import CommitError, ConfigLoadError, ConnectError, LockError
from jnpr.junos.utils.config import Config
from netaddr import IPAddress
# local
import utils

__all__ = [
    'VrfMixin',
]
PortData = Optional[Dict[str, Union[list, dict]]]
RouterData = Optional[Dict[str, Optional[str]]]
MAX_ATTEMPTS = 10


class VrfMixin:
    logger: logging.Logger

    @classmethod
    def deploy(cls, setconf: str, management_ip: str, ignore_missing: bool = False) -> bool:
        """
        Deploy the generated configuration to the Router and return whether or not the deployment succeeded
        :param setconf: The configuration for the virtual router
        :param management_ip: The ip of the physical router to deploy to
        :param ignore_missing: Flag stating whether or not we should ignore the `statement not found` error
        :return: A flag stating whether or not the deployment was successful
        """
        cls.logger.debug(f'Attempting to connect to Router {management_ip} to deploy')
        try:
            # Using context managers for Router and Config will ensure everything is properly cleaned up when exiting
            # the function, regardless of how we exit the function
            with Device(host=management_ip, user='robot', port=22) as router:
                router.timeout = 2 * 60  # 2 minute timeout
                cls.logger.debug(f'Successfully connected to Router {management_ip}, now attempting to load config')

                for attempt in range(MAX_ATTEMPTS):
                    try:
                        return cls._configure(setconf, management_ip, router, ignore_missing)
                    except LockError:
                        cls.logger.warning(
                            f'Unable to lock config on Router {management_ip}. '
                            f'(Attempt #{attempt + 1} / {MAX_ATTEMPTS})',
                            exc_info=True,
                        )
                        sleep(30 + (6 * attempt))
                cls.logger.debug(
                    f'{MAX_ATTEMPTS} attempts to lock Router {management_ip} have failed. '
                    'This request is now considered a failure.',
                )
                return False
        except ConnectError:
            cls.logger.error(f'Unable to connect to Router {management_ip}', exc_info=True)
            return False

    @classmethod
    def _configure(cls, setconf: str, management_ip: str, router: Device, ignore_missing: bool) -> bool:
        """
        Open the configuration for the router and attempt to deploy to the router.
        This has been turned into a method to make it easier to repeat this function multiple times.
        :param setconf: The configuration for the virtual router
        :param management_ip: The ip of the physical router to deploy to
        :param router: A Device object representing the Router being configured.
        :param ignore_missing: Flag stating whether or not we should ignore the `statement not found` error
        :return: A flag stating whether or not the deployment was successful
        """
        with Config(router, mode='exclusive') as config:
            try:
                config.load(setconf, format='set', merge=True, ignore_warning=ignore_missing)
            except ConfigLoadError:
                cls.logger.error(
                    f'Unable to load configuration changes onto Router {management_ip}',
                    exc_info=True,
                )
                return False

            # Attempt to commit
            try:
                commit_msg = f'Loaded by robot at {asctime()}.'
                cls.logger.debug(
                    f'All commands successfully loaded onto Router {management_ip}, '
                    'now checking the commit status',
                )
                # Commit check either raises an error or returns True
                config.commit_check()
                cls.logger.debug(f'Commit check on Router {management_ip} successful, committing changes.')
                if not ignore_missing:
                    detail = config.commit(
                        comment=commit_msg,
                    )
                else:
                    detail = config.commit(
                        comment=commit_msg,
                        ignore_warning=['statement not found'],
                    )
                cls.logger.debug(f'Response from commit on Router {management_ip}\n{detail}')
            except CommitError:
                cls.logger.error(f'Unable to commit changes onto Router {management_ip}', exc_info=True)
                return False
            return True

    @classmethod
    def _get_router_ip(cls, router_id: int, span: Span) -> Optional[str]:
        """
        It fetches the Management port ip of the Router #router_id
        :param router_id:
        :return: : dict of vrf port details like Port name (xe-0/0/1 or ge-0/0/1 or etc)
        """
        port_data = cls._get_port_data(router_id=router_id, span=span)
        if port_data is not None:
            ports = port_data['ports']
            port_rmpf_pfs = port_data['port_rmpf_pfs']
        else:
            return None

        management_ip = None
        # collecting management ip
        for port in ports:
            if port_rmpf_pfs[port][1] == 'Management':

                # listing port_configs
                port_configs = utils.api_list(IAAS.port_config, {}, port_id=port, span=span)
                if len(port_configs) == 0:
                    return None

                for port_config in port_configs:
                    # Get the ip address details
                    ip = utils.api_read(IAAS.ipaddress, pk=port_config['port_ip_id'], span=span)
                    if ip is None:
                        return None
                    management_ip = str(ip['address'])
                    break

        if management_ip is not None:
            return management_ip
        else:
            cls.logger.error(
                f'Failed to get VRF router"s management ip for Router #{router_id}',
            )
            return None

    @classmethod
    def _get_router_data(cls, router_id: int, vrf_ip_subnet_id: int, span: Span) -> RouterData:
        """
        Collects the data such as private port name, public port name and address family of
        given vrf_ip_subnet_id
        :param router_id:
        :param vrf_ip_subnet_id :type int subnet id of vrf ip
        :param span:
        :return:
        """
        port_data = cls._get_port_data(router_id=router_id, span=span)
        if port_data is not None:
            ports = port_data['ports']
            port_rmpf_pfs = port_data['port_rmpf_pfs']
        else:
            return None

        private = None
        public = None
        address_family = None

        # collecting required data
        for port in ports:

            # Private port name
            if port_rmpf_pfs[port][1] == 'Private':
                private = port_rmpf_pfs[port][0]

            # public_port and address_family
            elif port_rmpf_pfs[port][1] == 'Floating':
                public = port_rmpf_pfs[port][0]

                port_configs = utils.api_list(IAAS.port_config, {}, port_id=port, span=span)
                for port_config in port_configs:
                    # Get the ip address details
                    ip = utils.api_read(IAAS.ipaddress, pk=port_config['port_ip_id'], span=span)
                    if ip is None:
                        return None
                    if str(ip['idSubnet']) == str(vrf_ip_subnet_id):
                        address_family = 'inet'
                        if IPAddress(ip['address']).version == 6:
                            address_family = 'inet6'
                        break
            if private is not None and public is not None and address_family is not None:
                break

        if private is not None and public is not None and address_family is not None:
            return {
                'private_port': private,
                'public_port': public,
                'address_family': address_family,
            }
        else:
            cls.logger.error(
                f'Failed to get VRF"s router details for Router #{router_id} and Subnet #{vrf_ip_subnet_id}',
            )
            return None

    @staticmethod
    def _get_port_data(router_id: int, span: Span) -> PortData:
        """
        Collects Port data for given router_id
        :param router_id: id of router to deal with
        :param span:
        :return: port_data: dict of port details like port name, port function
        """
        ports = None
        # listing ports
        ports = utils.api_list(IAAS.port, {}, router_id=router_id, span=span)
        if len(ports) == 0:
            # utils method does the logging for us
            return None

        # listing rmpfs
        rmpfs_params = {
            'model_port_id__in': [port['model_port_id'] for port in ports],
        }
        rmpfs = utils.api_list(IAAS.router_model_port_function, rmpfs_params, span=span)
        if len(rmpfs) == 0:
            return None

        # listing port_functions
        pfs_params = {
            'port_function_id__in': [rmpf['port_function_id'] for rmpf in rmpfs],
        }
        port_funcs = utils.api_list(IAAS.port_function, pfs_params, span=span)
        if len(port_funcs) == 0:
            return None

        # link port_id with [port name(ie 'xe-0/0/0' etc) and port_function(ie 'Private' etc)]
        port_rmpf_pfs = {}  # type: dict
        for port in ports:
            for rmpf in rmpfs:
                for port_func in port_funcs:
                    if port['model_port_id'] == rmpf['model_port_id'] and \
                            rmpf['port_function_id'] == port_func['port_function_id']:
                        port_rmpf_pfs[port['port_id']] = [rmpf['port_name'], port_func['function']]
                        break
        if ports is not None and port_rmpf_pfs is not None:
            return {
                'ports': [port['port_id'] for port in ports],
                'port_rmpf_pfs': port_rmpf_pfs,
            }
        else:
            return None
