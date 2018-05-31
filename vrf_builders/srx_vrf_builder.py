import time
from jnpr.junos import Device
from jnpr.junos.exception import (
    CommitError,
    ConfigLoadError,
    LockError,
    UnlockError,
)
from jnpr.junos.utils.config import Config
from utils import get_logger_for_name

driver_logger = get_logger_for_name('srx_vrf_builder.deploy_setconf')

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
    id_project = str(vrf['idProject'])
    driver_logger.info(
        f'Generating configuration for project #{id_project}'
    )
    # vlans is used to create interfaces and sub-interfaces
    vlans = vrf['vLANs']
    # nats is used to create proxy-arp NAT with customers
    nats = vrf['NATs']
    # out_bound_ip address used for NAT pool and as IKE gateway
    out_bound_ip = str(vrf['outBoundIP'])
    # vpns for IPSec VPN
    # vpns = vrf['VPNs']
    # oobIP = "10.252.14.32"
    oob_ip = str(vrf['oobIP'])

    # Routing Instances
    # Create vrf
    conf = (
        f'set groups {id_project} routing-instances vrf-{id_project} '
        f'instance-type virtual-router\n'
    )
    # Create southbound sub interface and gateway for each VLAN and
    # attach to vrf
    for vlan in vlans:
        conf += (
            f'set groups {id_project} routing-instances vrf-{id_project} '
            f'interface ge-0/0/1.{vlan["vLAN"]}\n'
        )

    # Create a northbound route
    conf += (
        f'set groups {id_project} routing-instances vrf-{id_project} '
        f'routing-options static route 0.0.0.0/0 next-table PUBLIC.inet.0\n'
    )

    # Configure sub-interfaces
    for vlan in vlans:
        vlan['vLAN'] = str(vlan['vLAN'])
        conf += (
            f'set groups {id_project} interfaces ge-0/0/1 unit {vlan["vLAN"]} '
            f'description {id_project}-{vlan["vLAN"]} vlan-id {vlan["vLAN"]} '
            f'family inet address {vlan["subnet"]}\n'
        )

    # Create private zones
    for vlan in vlans:
        conf += (
            f'set groups {id_project} security zones security-zone '
            f'{id_project} interfaces ge-0/0/1.{str(vlan["vLAN"])} '
            f'host-inbound-traffic system-services ping\n'
        )

    # Source (outbound) NAT
    conf += (
        f'set groups {id_project} security nat source rule-set '
        f'{id_project}-outbound description {id_project}-outbound-nat\n'
        f'set groups {id_project} security nat source pool '
        f'{id_project}-public routing-instance vrf-{id_project}\n'
        f'set groups {id_project} security nat source pool '
        f'{id_project}-public address {out_bound_ip}\n'
        f'set groups {id_project} security nat source rule-set '
        f'{id_project}-outbound from zone {id_project}\n'
        f'set groups {id_project} security nat source rule-set '
        f'{id_project}-outbound to zone PUBLIC'
    )
    for vlan in vlans:
        conf += (
            f'set groups {id_project} security nat source rule-set '
            f'{id_project}-outbound rule {vlan["vLAN"]}-outbound match '
            f'source-address {vlan["subnet"]}\n'
            f'set groups {id_project} security nat source rule-set '
            f'{id_project}-outbound rule {vlan["vLAN"]}-outbound then '
            f'source-nat pool {id_project}-public\n'
        )

    # Create proxy-arp on specific interface with predefined IP addresses
    for nat in nats:
        conf += (
            f'set groups {id_project} security nat proxy-arp interface '
            f'ge-0/0/0.0 address {str(nat["fIP"])}\n'
        )

    # Create NAT static rule-set inbound
    for nat in nats:
        conf += (f'set groups {id_project} security nat static rule-set '
                 f'{id_project} inbound-static from zone PUBLIC\n')
        rule_name = str(nat['fIP']).split('/')[0]
        # ruleNames in Junos cannot contain /
        rule_name = rule_name.replace('.', '-')
        # ruleNames in Junos cannot contain .
        conf += (f'set groups {id_project} security nat static rule-set '
                 f'{id_project}-inbound-static rule {rule_name} '
                 f'match destination-address {str(nat["fIP"])}\n'
                 f'set groups {id_project} security nat static rule-set '
                 f'{id_project}-inbound-static rule {rule_name} '
                 f'then static-nat prefix {str(nat["pIP"])}\n'
                 f'set groups {id_project} security nat static rule-set '
                 f'{id_project}-inbound-static rule {rule_name} '
                 f'then static-nat prefix routing-instance '
                 f'vrf-{id_project}\n')

    # IKE VPNs TODO

    vrf_status = deploy_setconf(conf, oob_ip, password)
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
    dev = Device(host=ip, user='robot', password=password, port=22)
    cu = Config(dev)
    try:
        dev.open()
    except Exception:
        driver_logger.exception(
            f'Unable to connect to router @ {ip}'
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
        driver_logger.exception(
            f'Unable to lock router @ {ip}'
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
        driver_logger.exception(
            f'Unable to load configuration changes on router @ {ip}.'
        )
        driver_logger.info(
            f'Attempting to unlock configuration on router @ {ip} '
            f'after exception'
        )
        try:
            cu.unlock()
        except UnlockError:
            driver_logger.exception(
                f'Unable to unlock configuration on router @ {ip}'
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
        driver_logger.exception(
            f'Unable to commit changes onto router @ {ip}'
        )
        return success
    driver_logger.info(
        f'Attempting to unlock configuration on router @ {ip}'
    )
    try:
        cu.unlock()
    except UnlockError:
        driver_logger.exception(
            f'Unable to unlock configuration on router @ {ip}'
        )
        dev.close()
    return success
