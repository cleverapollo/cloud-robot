import time
from utils import get_logger_for_name
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.exception import LockError, UnlockError, ConfigLoadError, \
    CommitError

robot_logger = get_logger_for_name('vrfBuilder')

# TODO not yet fixed

def vrfBuild(VRF, passwd):
    """
    Builds Virtual Routing and Forwarding (VRF) in corresponding Router,
    so it first prepares set commands and paramikos into router and executes
    the set commands, so replies True on success or False on Failure.
    :param VRF: dict object
    :param passwd: string
    :return: Boolean
    """

    idProject = VRF['idProject']
    vLANs = VRF['vLANs']
    # proxyIP is used to create proxy-arp NAT with customers
    # public IP addresses
    proxyIPs = VRF['proxyIPs']
    # privatNATips address to wich all inbound traffic will be NATed
    privateNATips = VRF['privateNATips']
    # publicIP add.ress used for NAT pool and as IKE gateway
    publicIP = VRF['publicIP']
    # oobIP = "10.252.14.32"
    oobIP = VRF['oobIP']
    setconf = ''

    # Routing Instances
    # Create vrf
    setconf += 'set routing-instances vrf-' + str(idProject) + \
               ' instance-type virtual-router\n'

    # Create southbound sub interface and gateway for each VLAN and
    # attach to vrf
    for vLAN in vLANs:
        setconf += 'set routing-instances vrf-' + str(idProject) + \
                   ' interface ge-0/0/1.' + str(vLAN[0]) + '\n'

    # Create a northbound route
    setconf += 'set routing-instances vrf-' + str(idProject)
    setconf += ' routing-options static route 0.0.0.0/0 next-table ' \
               'PUBLIC.inet.0\n'

    # Configure sub-interfaces
    for vLAN in vLANs:
        setconf += 'set interfaces ge-0/0/1 unit ' + str(vLAN[0]) + \
                   ' description '
        setconf += str(idProject) + '-' + str(vLAN[0]) + ' vlan-id ' \
            + str(vLAN[0])
        setconf += ' family inet address ' + str(vLAN[1]) + '\n'

    # Create private zones
    for vLAN in vLANs:
        setconf += 'set security zones security-zone ' + str(vLAN[0]) + \
                   '.private interfaces ge-0/0/1.' + str(vLAN[0])
        setconf += ' host-inbound-traffic system-services ping\n'

    # Source (outbound) NAT
    setconf += 'set security nat source rule-set ' + str(idProject) + \
               '-outbound description '
    setconf += str(idProject) + '-outbound-nat\n'
    setconf += 'set security nat source pool ' + str(idProject) + \
               '-public routing-instance vrf-' + str(idProject) + '\n'
    setconf += 'set security nat source pool ' + str(idProject) + \
               '-public address ' + str(publicIP[0]) + '\n'
    for vLAN in vLANs:
        setconf += 'set security nat source rule-set ' + str(idProject) + \
                   '-outbound from zone '
        setconf += str(vLAN[0]) + '.private\n'
        setconf += 'set security nat source rule-set ' + str(idProject) + \
                   '-outbound rule '
        setconf += str(vLAN[0]) + '-outbound match source-address ' + \
            str(vLAN[1]) + '\n'
        setconf += 'set security nat source rule-set ' + str(idProject) + \
                   '-outbound rule '
        setconf += str(vLAN[0]) + '-outbound then source-nat pool ' + \
            str(idProject) + '-public\n'
    setconf += 'set security nat source rule-set ' + str(idProject) + \
               '-outbound to zone PUBLIC\n'

    # Create proxy-arp on specific interface with predefined IP addresses
    for proxyIP in proxyIPs:
        setconf += 'set security nat proxy-arp interface ge-0/0/0.0 address '\
                   + str(proxyIP) + '\n'

    # Create NAT static rule-set inbound
    i = 0
    for vLAN in vLANs:
        setconf += 'set security nat static rule-set inbound-static from ' \
                   'zone ' + str(vLAN[0]) + '.private\n'
        ruleName = str(proxyIPs[i]).split("/")[0]
        # ruleNames in Junos cannot contain /
        ruleName = ruleName.replace(".", "-")
        # ruleNames in Junos cannot contain .
        setconf += 'set security nat static rule-set inbound-static rule ' \
                   + ruleName
        setconf += ' match destination-address ' + str(proxyIPs[i]) + '\n'
        setconf += 'set security nat static rule-set inbound-static rule ' \
                   + ruleName
        setconf += ' then static-nat prefix ' + str(privateNATips[i]) + '\n'
        setconf += 'set security nat static rule-set inbound-static rule ' \
                   + ruleName
        setconf += ' then static-nat prefix routing-instance vrf-' + \
                   str(idProject) + '\n'
        i += 1
    # Create IKE
    # Create IKE proposal
    setconf += 'set security ike proposal ike-' + \
               str(idProject) + '-' + str(vLAN[0])
    setconf += '-proposal authentication-method pre-shared-keys\n'
    setconf += 'set security ike proposal ike-' + \
               str(idProject) + '-' + str(vLAN[0]) + \
               '-proposal dh-group group2\n'
    setconf += 'set security ike proposal ike-' + \
               str(idProject) + '-' + str(vLAN[0])
    setconf += '-proposal authentication-algorithm sha1\n'
    setconf += 'set security ike proposal ike-' + \
               str(idProject) + '-' + str(vLAN[0])
    setconf += '-proposal encryption-algorithm aes-128-cbc\n'

    # Create IKE policy
    setconf += 'set security ike policy ' + \
               str(idProject) + '-' + str(vLAN[0]) + '-ikepolicy mode main\n'
    setconf += 'set security ike policy ' + \
               str(idProject) + '-' + str(vLAN[0])
    setconf += '-ikepolicy proposals ike-' + \
               str(idProject) + '-' + str(vLAN[0]) + '-proposal\n'
    setconf += 'set security ike policy ' + str(idProject) + '-' + \
               str(vLAN[0]) + '-ikepolicy pre-shared-key '
    setconf += 'ascii-text "abcdefgh01234"\n'

    # Configure IKE gateway
    setconf += 'set security ike gateway ' + \
               str(idProject) + '-' + str(vLAN[0]) + '-gw ike-policy '
    setconf += str(idProject) + '-' + str(vLAN[0]) + '-ikepolicy\n'
    setconf += 'set security ike gateway ' + \
               str(idProject) + '-' + str(vLAN[0]) + '-gw address 1.2.3.4\n'
    setconf += 'set security ike gateway ' + str(idProject) + '-' + \
               str(vLAN[0]) + '-gw external-interface ge-0/0/0.0\n'
    setconf += 'set security ike gateway ' + str(idProject) + '-' + \
               str(vLAN[0]) + '-gw local-address ' + str(publicIP[0]) + '\n'

    # Create ipsec VPN
    # Configure st interface
    setconf += 'set interfaces st0 unit ' + str(vLAN[0]) + '\n'
    setconf += 'set security ipsec vpn ' + str(idProject) + '-' + \
               str(vLAN[0]) + '-vpn bind-interface st0.'
    setconf += str(vLAN[0]) + '\n'
    setconf += 'set security ipsec vpn ' + str(idProject) + '-' + \
               str(vLAN[0]) + '-vpn ike gateway '
    setconf += str(idProject) + '-' + str(vLAN[0]) + '-gw\n'

    # Add configured st interfaces to security zone
    setconf += 'set routing-instances vrf-' + str(idProject) + \
               ' interface st0.' + str(vLAN[0]) + '\n'
    setconf += 'set security zones security-zone ' + str(vLAN[0]) + \
               '.private interfaces st0.' + str(vLAN[0]) + '\n'

    # Create ipsec proposal
    setconf += 'set security ipsec proposal ipsec-' + str(idProject) + '-' \
               + str(vLAN[0]) + '-proposal protocol esp\n'
    setconf += 'set security ipsec proposal ipsec-' + str(idProject) + '-' \
               + str(vLAN[0])
    setconf += '-proposal authentication-algorithm hmac-sha1-96\n'
    setconf += 'set security ipsec proposal ipsec-' + str(idProject) + '-' \
               + str(vLAN[0])
    setconf += '-proposal encryption-algorithm aes-128-cbc\n'

    # Create ipsec policy
    setconf += 'set security ipsec policy vpn-' + str(idProject) + '-' + \
               str(vLAN[0]) + ' perfect-forward-secrecy keys group2\n'
    setconf += 'set security ipsec policy vpn-' + str(idProject) + '-' + \
               str(vLAN[0])
    setconf += ' proposals ipsec-' + str(idProject) + '-' + str(vLAN[0]) + \
               '-proposal\n'
    setconf += 'set security ipsec vpn ' + str(idProject) + '-' + str(vLAN[0])
    setconf += '-vpn ike ipsec-policy vpn-' + str(idProject) + '-' + \
               str(vLAN[0]) + '\n'

    password = passwd
    vrf_status = deploy_setconf(setconf, oobIP, password)
    return vrf_status


#########################################################
#   Deploy setconf to Router                            #
#########################################################
def deploy_setconf(setconf, ip, password):
    success = False
    # Open Router
    dev = Device(host=ip, user="robot", password=password, port=22)
    cu = Config(dev)
    try:
        dev.open()
    except Exception as err:
        robot_logger.error("Unable to open host {}, {}".format(ip, err))
        return success
    # Lock Router
    robot_logger.info("Locking the Router with ip: {0} configuration."
                      .format(ip))
    try:
        cu.lock()
    except LockError as err:
        robot_logger.error("Unable to lock configuration: {0}".format(err))
        dev.close()
        return success

    # Load Configuration
    robot_logger.info("Loading configuration changes")
    try:
        for cmd in setconf.split('\n'):
            robot_logger.info(cmd)
            cu.load(cmd, format="set", merge=True)
    except (ConfigLoadError, Exception) as err:
        robot_logger.error("Unable to load configuration changes: {0}"
                           .format(err))
        robot_logger.error("Unlocking the configuration")
        try:
            cu.unlock()
        except UnlockError:
            robot_logger.error("Unable to unlock configuration: {0}"
                               .format(err))
        dev.close()
        return success

    # Commit Configuration
    robot_logger.info("Committing the configuration")
    try:
        cu.commit(comment='Loaded by robot at {0}.'.format(time.clock()))
        success = True
    except CommitError as err:
        robot_logger.error("Unable to commit configuration: {0}".format(err))
        robot_logger.info("Unlocking the configuration")
        return success
    try:
        cu.unlock()
    except UnlockError as err:
        robot_logger.error("Unable to unlock configuration: {0}".format(err))
        dev.close()
    return success
