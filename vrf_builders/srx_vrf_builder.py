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
    id_project = vrf['idProject']
    driver_logger.info(
        f'Generating configuration for project #{id_project}'
    )
    vlans = vrf['vLANs']
    # proxyIP is used to create proxy-arp NAT with customers
    # public IP addresses
    proxy_ips = vrf['proxyIPs']
    # privatNATips address to wich all inbound traffic will be NATed
    private_nat_ips = vrf['privateNATips']
    # publicIP add.ress used for NAT pool and as IKE gateway
    public_ip = vrf['publicIP']
    # oobIP = "10.252.14.32"
    oob_ip = vrf['oobIP']

    # Routing Instances
    # Create vrf
    conf = (
        f'set routing-instances vrf-{id_project} instance-type virtual-router'
        '\n'
    )
    # Create southbound sub interface and gateway for each VLAN and
    # attach to vrf
    for vlan in vlans:
        conf += (
            f'set routing-instances vrf-{id_project} interface ge-0/0/1.'
            f'{vlan[0]}\n'
        )

    # Create a northbound route
    conf += (
        f'set routing-instances vrf-{id_project} routing-options static route '
        '0.0.0.0/0 next-table PUBLIC.inet.0\n'
    )

    # Configure sub-interfaces
    for vlan in vlans:
        conf += (
            f'set interfaces ge-0/0/1 unit {vlan[0]} description {id_project}-'
            f'{vlan[0]} vlan-id {vlan[0]} family inet address {vlan[1]}\n'
        )

    # Create private zones
    for vlan in vlans:
        conf += (
            f'set security zones security-zone {vlan[0]}.private interfaces '
            f'ge-0/0/1.{vlan[0]} host-inbound-traffic system-services ping\n'
        )

    # Source (outbound) NAT
    conf += (
        f'set security nat source rule-set {id_project}-outbound description '
        f'{id_project}-outbound-nat\n'
        f'set security nat source pool {id_project}-public routing-instance '
        f'vrf-{id_project}\n'
        f'set security nat source pool {id_project}-public address '
        f'{public_ip[0]}\n'
    )
    for vlan in vlans:
        conf += (
            f'set security nat source rule-set {id_project}-outbound from zone'
            f' {vlan[0]}.private\n'
            f'set security nat source rule-set {id_project}-outbound rule '
            f'{vlan[0]}-outbound match source-address {vlan[1]}\n'
            f'set security nat source rule-set {id_project}-outbound rule '
            f'{vlan[0]}-outbound then source-nat pool {id_project}-public\n'
        )
    conf += (
        f'set security nat source rule-set {id_project}-outbound to zone '
        'PUBLIC'
    )

    # Create proxy-arp on specific interface with predefined IP addresses
    for proxy in proxy_ips:
        conf += (
            f'set security nat proxy-arp interface ge-0/0/0.0 address {proxy}'
            '\n'
        )

    # Create NAT static rule-set inbound
    for i, vlan in enumerate(vlans):
        conf += (
            'set security nat static rule-set inbound-static from zone '
            f'{vlan[0]}.private\n'
        )
        rule_name = str(proxy_ips[i]).split('/')[0]
        # rule names in Junos cannot contain /
        rule_name = rule_name.replace('.', '-')
        # rule names in Junos cannot contain .
        conf += (
            f'set security nat static rule-set inbound-static rule {rule_name}'
            f' match destination-address {proxy_ips[i]}\n'
            f'set security nat static rule-set inbound-static rule {rule_name}'
            f' then static-nat prefix {private_nat_ips[i]}\n'
            f'set security nat static rule-set inbound-static rule {rule_name}'
            f' then static-nat prefix routing-instance vrf-{id_project}\n'
        )
    # Create IKE
    for vlan in vlans:
        conf += (
            # Create IKE proposal
            f'set security ike proposal ike-{id_project}-{vlan[0]}-proposal '
            'authentication-method pre-shared-keys\n'
            f'set security ike proposal ike-{id_project}-{vlan[0]}-proposal '
            'dh-group group2\n'
            f'set security ike proposal ike-{id_project}-{vlan[0]}-proposal '
            'authentication-algorithm sha1\n'
            f'set security ike proposal ike-{id_project}-{vlan[0]}-proposal '
            'encryption-algorithm aes-128-cbc\n'

            # Create IKE policy
            f'sec security ike policy {id_project}-{vlan[0]}-ikepolicy mode '
            'main\n'
            f'set security ike policy {id_project}-{vlan[0]}-ikepolicy '
            f'proposals ike-{id_project}-{vlan[0]}-proposal\n'
            f'set security ike policy {id_project}-{vlan[0]}-ikepolicy '
            'pre-shared-key ascii-text "abcdefgh01234"\n'

            # Configure IKE gateway
            f'set security ike gateway {id_project}-{vlan[0]}-gw ike-policy '
            f'{id_project}-{vlan[0]}-ikepolicy\n'
            f'set security ike gateway {id_project}-{vlan[0]}-gw address '
            '1.2.3.4\n'
            f'set security ike gateway {id_project}-{vlan[0]}-gw '
            'external-interface ge-0/0/0.0\n'
            f'set security ike gateway {id_project}-{vlan[0]}-gw local-address'
            f' {public_ip[0]}\n'

            # Create ipsec VPN
            # Configure st interface
            f'set interfaces st0 unit {vlan[0]}\n'
            f'set security ipsec vpn {id_project}-{vlan[0]}-vpn bind-interface'
            f' st0.{vlan[0]}\n'
            f'set security ipsec vpn {id_project}-{vlan[0]}-vpn ike gateway '
            f'{id_project}-{vlan[0]}-gw\n'

            # Add configured st interfaces to security zone
            f'set routing-instances vrf-{id_project} interface st0.{vlan[0]}\n'
            f'set security zones security-zone {vlan[0]}.private interfaces '
            f'st0.{vlan[0]}\n'

            # Create ipsec proposal
            f'set security ipsec proposal ipsec-{id_project}-{vlan[0]}'
            '-proposal protocol esp\n'
            f'set security ipsec proposal ipsec-{id_project}-{vlan[0]}'
            '-proposal authentication-algorithm hmac-sha-96\n'
            f'set security ipsec proposal ipsec-{id_project}-{vlan[0]}'
            '-proposal encryption-algorithm aes-128-cbc\n'

            # Create ipsec policy
            f'set security ipsec policy vpn-{id_project}-{vlan[0]} '
            'perfect-forward-secrecy keys group2\n'
            f'set security ipsec policy vpn-{id_project}-{vlan[0]} proposals '
            f'ipsec-{id_project}-{vlan[0]}-proposal\n'
            f'set security ipsec vpn {id_project}-{vlan[0]}-vpn ike '
            f'ipsec-policy vpn-{id_project}-{vlan[0]}\n'
        )
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
