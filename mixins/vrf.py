"""
mixin class containing methods that are needed by vrf task classes
methods included;
    - method to get management ip and router model since they're not currently easy
    - method to get port data since that's not currently easy either
"""
# stdlib
import logging
from time import asctime
from typing import Dict, Optional, Union
# lib
from cloudcix.api import IAAS
from jaeger_client import Span
from jnpr.junos import Device
from jnpr.junos.exception import CommitError, ConfigLoadError, ConnectError
from jnpr.junos.utils.config import Config
from netaddr import IPAddress
# local
import utils

__all__ = [
    'VrfMixin',
]
PortData = Optional[Dict[str, Union[str, bool]]]
RouterData = Optional[Dict[str, Optional[str]]]


class VrfMixin:
    logger: logging.Logger

    @classmethod
    def deploy(cls, setconf: str, management_ip: str, scrub: bool = False) -> bool:
        """
        Deploy the generated configuration to the Router and return whether or not the deployment succeeded
        :param setconf: The configuration for the virtual router
        :param management_ip: The ip of the physical router to deploy to
        :param scrub: Flag stating whether or not we are scrubbing the Router. Used to ignore statement not found issues
        :return: A flag stating whether or not the deployment was successful
        """
        cls.logger.debug(f'Attempting to connect to Router {management_ip} to deploy')
        try:
            # Using context managers for Router and Config will ensure everything is properly cleaned up when exiting
            # the function, regardless of how we exit the function
            with Device(host=management_ip, user='robot', port=22) as router:
                router.timeout = 2 * 60
                cls.logger.debug(f'Successfully connected to Router {management_ip}, now attempting to load config')
                with Config(router, mode='batch') as config:
                    try:
                        for cmd in setconf.split('\n'):
                            config.load(cmd, format='set', merge=True, ignore_warning=scrub)
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
                        if not scrub:
                            config.commit(comment=commit_msg)
                        else:
                            config.commit(comment=commit_msg, ignore_warning=['statement not found'])
                    except CommitError:
                        cls.logger.error(f'Unable to commit changes onto Router {management_ip}', exc_info=True)
                        return False

                cls.logger.debug(f'Changes successfully committed onto Router {management_ip}')
                return True
        except ConnectError:
            cls.logger.error(f'Unable to connect to Router {management_ip}', exc_info=True)
            return False

    @classmethod
    def _get_router_data(cls, router_id: int, span: Span) -> RouterData:
        """
        TODO - Remove this once Compute in Python 3 fixes the mess that is Routers and Ports (if possible)
        This function is a goddamn mess
        """
        manage_ip = None
        router_model = None
        ports = utils.api_list(IAAS.port, {}, router_id=router_id, span=span)
        for port in ports:
            # Get the Port names ie xe-0/0/0 etc
            rmpf = utils.api_read(IAAS.router_model_port_function, pk=port['model_port_id'], span=span)
            if rmpf is None:
                # utils method does the logging for us
                return None
            # Get the router model
            router_model_response = utils.api_read(IAAS.router_model, pk=rmpf['router_model_id'], span=span)
            if router_model_response is None:
                return None
            router_model = str(router_model_response['model'])
            # Get the function names ie 'Management' etc
            port_func = utils.api_read(IAAS.port_function, pk=rmpf['port_function_id'], span=span)
            if port_func is None:
                return None
            if port_func['function'] == 'Management':
                port_configs = utils.api_list(IAAS.port_config, {}, port_id=port['port_id'], span=span)
                for port_config in port_configs:
                    # Get the ip address details
                    ip = utils.api_read(IAAS.ipaddress, pk=port_config['port_ip_id'], span=span)
                    if ip is None:
                        return None
                    manage_ip = str(ip['address'])
                    break
                break
        return {'management_ip': manage_ip, 'router_model': router_model}

    @classmethod
    def _get_vrf_port_data(cls, vrf_ip_subnet_id: int, router_id: int, span: Span) -> PortData:
        """
        TODO - Refactor (or hopefully remove) this method when we bring Compute to Python 3
        It takes vrf ip to find out whether IP belongs to Floating or Floating Pre Filtered so that
        vrf will be configured on the port corresponding to its nature using router
        :param vrf_ip_subnet_id :type int subnet id of vrf ip
        :param router_id:
        :return: vrf_port: dict of vrf port details like Port name (xe-0/0/1 or ge-0/0/1 or etc)
        """
        firewall = False
        interface = None
        private_port = None
        address_family = None
        # Get the Ports which are Floating and Floating Pre Filtered of Router
        for port in utils.api_list(IAAS.port, {}, router_id=router_id, span=span):
            # Get the Port names ie xe-0/0/0 etc
            rmpf = utils.api_read(IAAS.router_model_port_function, pk=port['model_port_id'], span=span)
            if rmpf is None:
                # utils method handles the error logging
                return None
            # Get the function names ie 'Management' etc
            port_func = utils.api_read(IAAS.port_function, pk=rmpf['port_function_id'], span=span)
            if port_func is None:
                return None
            if port_func['function'] == 'Private':
                private_port = rmpf['port_name']
            elif port_func['function'] == 'Floating Pre Filtered':
                port_configs = utils.api_list(IAAS.port_config, {}, port_id=port['port_id'], span=span)
                for port_config in port_configs:
                    # Get the ip address details
                    ip = utils.api_read(IAAS.ipaddress, pk=port_config['port_ip_id'], span=span)
                    if ip is None:
                        return None
                    if str(ip['idSubnet']) == str(vrf_ip_subnet_id):
                        firewall = True
                        interface = rmpf['port_name']
                        address_family = 'inet'
                        if IPAddress(ip['address']).version == 6:
                            address_family = 'inet6'
                        break
            if firewall and interface is not None and private_port is not None:
                break  # just exit for loop as we got required data
            elif port_func['function'] == 'Floating':
                port_configs = utils.api_list(IAAS.port_config, {}, port_id=port['port_id'], span=span)
                for port_config in port_configs:
                    # Get the ip address details
                    ip = utils.api_read(IAAS.ipaddress, pk=port_config['port_ip_id'], span=span)
                    if ip is None:
                        return None
                    if str(ip['idSubnet']) == str(vrf_ip_subnet_id):
                        firewall = False
                        interface = rmpf['port_name']
                        address_family = 'inet'
                        if IPAddress(ip['address']).version == 6:
                            address_family = 'inet6'
                        break
            if not firewall and interface is not None and private_port is not None:
                break  # just exit for loop as we got required data
        if interface is not None and private_port is not None and address_family is not None:
            return {
                'address_family': address_family,
                'has_firewall': firewall,
                'private_port': private_port,
                'public_port': interface,
            }
        else:
            cls.logger.error(
                f'Failed to get VRF Port details for Router #{router_id} and Subnet #{vrf_ip_subnet_id}',
            )
            return None
