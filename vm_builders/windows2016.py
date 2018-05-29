# python
import winrm
import xmltodict
from collections import OrderedDict

# local
import utils

driver_logger = utils.get_logger_for_name('windows2016.vm_build')
# FREENAS mounted location in the host /mnt/images
freenas_path = 'alpha-freenas.cloudcix.com\\mnt\\volume\\alpha'
path = '/mnt/images/UnattendXMLfiles/'
os_name = 'WindowsServer2016x64'
xmlns_wcm = 'http://schemas.microsoft.com/WMIConfig/2002/State'
xmlns_xsi = 'http://www.w3.org/2001/XMLSchema-instance'


def unattend_xml(vm: dict) -> str:
    """
    Creates autounattend.xml file in 'path' for setting up a windows VM
    :param vm: Data for building the VM
    :return xml: XML file built from the supplied data
    """

    administrator_password = str(vm['r_passwd'])
    ip_address = str(vm['ip'])
    gateway = str(vm['gateway'])
    language = str(vm['lang'])
    time_zone = str(vm['tz'])
    dns_servers = vm['dns']
    user_account = {
        'username': str(vm['u_name']),
        'password': str(vm['u_passwd'])
    }

    data = {
        'unattend': OrderedDict([
            ('@xmlns', 'urn:schemas-microsoft-com:unattend'),
            ('settings', [
                OrderedDict([
                    ('@pass', 'specialize'),
                    ('component', [
                        OrderedDict([
                            ('@name', 'Microsoft-Windows-Shell-Setup'),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('TimeZone', time_zone)
                        ]),
                        OrderedDict([
                            ('@name', (
                                'Microsoft-Windows-TerminalServices'
                                '-LocalSessionManager'
                            )),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('fDenyTSConnections', 'false')
                        ]),
                        OrderedDict([
                            ('@name', (
                                'Microsoft-Windows-TerminalServices-RDP-'
                                'WinStationExtensions'
                            )),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('UserAuthentication', '0'),
                            ('SecurityLayer', '1')
                        ]),
                        OrderedDict([
                            ('@name', 'Networking-MPSSVC-Svc'),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('FirewallGroups', OrderedDict([
                                ('FirewallGroup', OrderedDict([
                                    ('@wcm:action', 'add'),
                                    ('@wcm:keyValue', 'EnableRemoteDesktop'),
                                    ('Active', 'true'),
                                    ('Group', 'Remote Desktop'),
                                    ('Profile', 'all')
                                ]))
                            ]))
                        ]),
                        OrderedDict([
                            ('@name', 'Microsoft-Windows-TCPIP'),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('Interfaces', OrderedDict([
                                ('Interface', OrderedDict([
                                    ('@wcm:action', 'add'),
                                    ('Ipv4Settings', OrderedDict([
                                        ('DhcpEnabled', 'false'),
                                        ('RouterDiscoveryEnabled', 'false')
                                    ])),
                                    ('Ipv6Settings', OrderedDict([
                                        ('DhcpEnabled', 'false'),
                                        ('RouterDiscoveryEnabled', 'false')
                                    ])),
                                    ('UnicastIpAddresses', OrderedDict([
                                        ('IpAddress', OrderedDict([
                                            ('@wcm:action', 'add'),
                                            ('@wcm:keyValue', '1'),
                                            ('#text', ip_address)
                                        ]))
                                    ])),
                                    ('Identifier', 'Ethernet'),
                                    ('Routes', OrderedDict([
                                        ('Route', OrderedDict([
                                            ('@wcm:action', 'add'),
                                            ('Identifier', '0'),
                                            ('NextHopAddress', gateway),
                                            ('Prefix', '0.0.0.0/0')
                                        ]))
                                    ]))
                                ]))
                            ]))
                        ]),
                        OrderedDict([
                            ('@name', 'Microsoft-Windows-DNS-Client'),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('Interfaces', OrderedDict([
                                ('Interface', OrderedDict([
                                    ('@wcm:action', 'add'),
                                    ('DNSServerSearchOrder', OrderedDict([
                                        ('IpAddress', [
                                            OrderedDict([
                                                ('@wcm:action', 'add'),
                                                ('@wcm:keyValue', str(i + 1)),
                                                ('#text', str(dns_servers[i]))
                                            ])
                                            for i in range(len(dns_servers))
                                        ])
                                    ])),
                                    ('Identifier', 'Ethernet'),
                                    ('DisableDynamicUpdate', 'false'),
                                    (
                                        'EnableAdapterDomainNameRegistration',
                                        'true'
                                    )
                                ]))
                            ]))
                        ])
                    ])
                ]),
                OrderedDict([
                    ('@pass', 'oobeSystem'),
                    ('component', [
                        OrderedDict([
                            ('@name', 'Microsoft-Windows-Shell-Setup'),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('OOBE', OrderedDict([
                                ('HideEULAPage', 'true'),
                                ('HideWirelessSetupInOOBE', 'true'),
                                ('NetworkLocation', 'Work'),
                                ('ProtectYourPC', '1')
                            ])),
                            ('UserAccounts', OrderedDict([
                                ('AdministratorPassword', OrderedDict([
                                    ('Value', administrator_password),
                                    ('PlainText', 'true')
                                ])),
                                ('LocalAccounts', OrderedDict([
                                    ('@wcm:action', 'add'),
                                    ('Password', OrderedDict([
                                        ('Value', user_account['password']),
                                        ('PlainText', 'true')
                                    ])),
                                    ('Description', 'User Account'),
                                    ('DisplayName', user_account['name']),
                                    ('Group', 'Administrators'),
                                    ('Name', user_account['name'])
                                ])),
                            ])),
                            ('TimeZone', time_zone),
                            ('FirstLogonCommands', OrderedDict([
                                ('SynchronousCommand', [
                                    OrderedDict([
                                        ('@wcm:action', 'add'),
                                        ('Order', '2'),
                                        ('RequiresUserInput', 'false'),
                                        ('Description', 'AVMA'),
                                        ('CommandLine', (
                                            'cscript //B %windir%/system32/'
                                            'slmgr.vbs /ipk '
                                            'C3RCX-M6NRP-6CXC9-TW2F2-4RHYD'
                                        ))
                                    ]),
                                    OrderedDict([
                                        ('@wcm:action', 'add'),
                                        ('Order', '1'),
                                        ('RequiresUserInput', 'false'),
                                        (
                                            'Description',
                                            'Enable Remote Desktop Firewall'
                                        ),
                                        ('CommandLine', (
                                            'Netsh advfirewall firewall set '
                                            'rule group="remote desktop" new '
                                            'enable=yes'
                                        ))
                                    ]),
                                    OrderedDict([
                                        ('@wcm:action', 'add'),
                                        ('Order', '3'),
                                        ('Description', 'Windows Updates'),
                                        ('RequiresUserInput', 'false'),
                                        ('CommandLine', (
                                            'Usoclient StartDownload '
                                            'StartInstall'
                                        ))
                                    ])
                                ])
                            ]))
                        ]),
                        OrderedDict([
                            ('@name', 'Microsoft-Windows-International-Core'),
                            ('@processorArchitecture', 'amd64'),
                            ('@publicKeyToken', '31bf3856ad364e35'),
                            ('@language', 'neutral'),
                            ('@versionScope', 'nonSxS'),
                            ('@xmlns:wcm', xmlns_wcm),
                            ('@xmlns:xsi', xmlns_xsi),
                            ('InputLocale', language),
                            ('SystemLocale', language),
                            ('UILanguage', language),
                            ('UILanguageFallback', language),
                            ('UserLocale', language)
                        ])
                    ])
                ])
            ])
        ])
    }

    return xmltodict.unparse(data, pretty=True)


def vm_build(vm: dict, password: str) -> bool:
    """
    Prepares an answerfile in freenas, and creates a VM in HyperV using WinRM
    :param vm: Data about the VM to be built
    :param password: Password for the host
    :return: Flag stating whether or not the build was successful
    """
    vm_built = False
    xml = unattend_xml(vm)
    try:
        with open(f'{path}{vm["vmIdentifer"]}.xml', 'w') as file:
            file.write(xml)
    except Exception:
        driver_logger.exception(
            f'Failed to write answerfile to file for VM {vm["vmIdentifier"]}'
        )
        return vm_built
    try:
        session = winrm.Session(
            vm['host_name'],
            auth=('administrator', str(password))
        )

        cmd = (
            f'mount \\\\{freenas_path} Z: -o nolock & powershell -file '
            f'Z:\scripts\VMCreator.ps1 -VMName {vm["vmIdentifier"]} -Gen 1 '
            f'-OSName {os_name} -ProcessorCount {vm["cpu"]} -Dynamic 1 -Ram '
            f'{vm["ram"]} -Hdd {vm["hdd"]} -Flash {vm["flash"]} -VlanId '
            f'{vm["vlan"]} -Verbose'
        )

        run = session.run_cmd(cmd)
        if run.std_out:
            for line in run.std_out:
                driver_logger.info(line)
            vm_built = True
        elif run.std_err:
            driver_logger.error(run.std_err)
    except Exception:
        driver_logger.exception(
            f'Exception thrown when attempting to connect to {vm["host_name"]}'
            ' for WinRM'
        )
    return vm_built
