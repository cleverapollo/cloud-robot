# python
import xmltodict
import winrm
from collections import OrderedDict

# local
import utils
from ro import fix_run_ps

winrm.Session.run_ps = fix_run_ps
driver_logger = utils.get_logger_for_name('windows2016.vm_build')
# FREENAS mounted location in the host /mnt/images
path = '/mnt/images/UnattendXMLfiles/'


def unattend_xml(vm: dict) -> str:
    """
    Creates autounattend.xml file in 'path'
    :param vm: dict object all fields are compulsory
    :return xml data:
    """

    AdministratorPassword = vm['r_passwd']
    IP = vm['ip']
    gateway = vm['gateway']
    InputLocale = vm['lang']
    SystemLocale = vm['lang']
    UILanguage = vm['lang']
    UILanguageFallback = vm['lang']
    UserLocale = vm['lang']
    TimeZone = vm['tz']
    DNSs = vm['dns']
    UserAccouts = [{'Name': str(vm['u_name']), 'Value': vm['u_passwd']}]

    data = {
        'unattend': OrderedDict(
            [('@xmlns', 'urn:schemas-microsoft-com:unattend'),
             ('settings',
              [OrderedDict(
                  [('@pass', 'specialize'),
                   ('component',
                    [OrderedDict(
                        [('@name', 'Microsoft-Windows-Shell-Setup'),
                         ('@processorArchitecture', 'amd64'),
                         ('@publicKeyToken', '31bf3856ad364e35'),
                         ('@language', 'neutral'),
                         ('@versionScope', 'nonSxS'),
                         ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                        'WMIConfig/2002/State'),
                         ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                        'XMLSchema-instance'),
                         ('TimeZone', str(TimeZone))
                         ]),
                     OrderedDict(
                         [('@name', 'Microsoft-Windows-TerminalServices-'
                                    'LocalSessionManager'),
                          ('@processorArchitecture', 'amd64'),
                          ('@publicKeyToken', '31bf3856ad364e35'),
                          ('@language', 'neutral'),
                          ('@versionScope', 'nonSxS'),
                          ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                         'WMIConfig/2002/State'),
                          ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                         'XMLSchema-instance'),
                          ('fDenyTSConnections', 'false')
                          ]),
                     OrderedDict(
                         [('@name', 'Microsoft-Windows-TerminalServices'
                                    '-RDP-WinStationExtensions'),
                          ('@processorArchitecture', 'amd64'),
                          ('@publicKeyToken', '31bf3856ad364e35'),
                          ('@language', 'neutral'),
                          ('@versionScope', 'nonSxS'),
                          ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                         'WMIConfig/2002/State'),
                          ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                         'XMLSchema-instance'),
                          ('UserAuthentication', '0'),
                          ('SecurityLayer', '1')
                          ]),
                     OrderedDict(
                         [('@name', 'Networking-MPSSVC-Svc'),
                          ('@processorArchitecture', 'amd64'),
                          ('@publicKeyToken', '31bf3856ad364e35'),
                          ('@language', 'neutral'),
                          ('@versionScope', 'nonSxS'),
                          ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                         'WMIConfig/2002/State'),
                          ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                         'XMLSchema-instance'),
                          ('FirewallGroups',
                           OrderedDict(
                               [('FirewallGroup',
                                 OrderedDict(
                                     [('@wcm:action', 'add'),
                                      ('@wcm:keyValue',
                                       'EnableRemoteDesktop'),
                                      ('Active', 'true'),
                                      ('Group', 'Remote Desktop'),
                                      ('Profile', 'all')
                                      ]))
                                ]))
                          ]),
                     OrderedDict(
                         [('@name', 'Microsoft-Windows-TCPIP'),
                          ('@processorArchitecture', 'amd64'),
                          ('@publicKeyToken', '31bf3856ad364e35'),
                          ('@language', 'neutral'),
                          ('@versionScope', 'nonSxS'),
                          ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                         'WMIConfig/2002/State'),
                          ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                         'XMLSchema-instance'),
                          ('Interfaces',
                           OrderedDict(
                               [('Interface',
                                 OrderedDict(
                                     [('@wcm:action', 'add'),
                                      ('Ipv4Settings',
                                       OrderedDict(
                                           [('DhcpEnabled', 'false'),
                                            ('RouterDiscoveryEnabled',
                                             'false')
                                            ])),
                                      ('Ipv6Settings',
                                       OrderedDict(
                                           [('DhcpEnabled', 'false'),
                                            ('RouterDiscoveryEnabled',
                                             'false')
                                            ])),
                                      ('UnicastIpAddresses',
                                       OrderedDict(
                                           [('IpAddress',
                                             OrderedDict(
                                                 [('@wcm:action', 'add'),
                                                  ('@wcm:keyValue', '1'),
                                                  ('#text', str(IP))
                                                  ]))
                                            ])),
                                      ('Identifier', 'Ethernet'),
                                      ('Routes',
                                       OrderedDict(
                                           [('Route',
                                             OrderedDict(
                                                 [('@wcm:action', 'add'),
                                                  ('Identifier', '0'),
                                                  ('NextHopAddress',
                                                   str(gateway)),
                                                  ('Prefix', '0.0.0.0/0')
                                                  ]))
                                            ]))
                                      ]))
                                ]))
                          ]),
                     OrderedDict(
                         [('@name', 'Microsoft-Windows-DNS-Client'),
                          ('@processorArchitecture', 'amd64'),
                          ('@publicKeyToken', '31bf3856ad364e35'),
                          ('@language', 'neutral'),
                          ('@versionScope', 'nonSxS'),
                          ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                         'WMIConfig/2002/State'),
                          ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                         'XMLSchema-instance'),
                          ('Interfaces',
                           OrderedDict(
                               [('Interface',
                                 OrderedDict(
                                     [('@wcm:action', 'add'),
                                      ('DNSServerSearchOrder',
                                       OrderedDict(
                                           [('IpAddress', list())
                                            ])),
                                      ('Identifier', 'Ethernet'),
                                      ('DisableDynamicUpdate', 'false'),
                                      ('EnableAdapterDomainNameRegistration',
                                       'true')
                                      ]))
                                ]))
                          ])])
                   ]),
               OrderedDict(
                   [('@pass', 'oobeSystem'),
                    ('component',
                     [OrderedDict(
                         [('@name', 'Microsoft-Windows-Shell-Setup'),
                          ('@processorArchitecture', 'amd64'),
                          ('@publicKeyToken', '31bf3856ad364e35'),
                          ('@language', 'neutral'),
                          ('@versionScope', 'nonSxS'),
                          ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                         'WMIConfig/2002/State'),
                          ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                         'XMLSchema-instance'),
                          ('OOBE',
                           OrderedDict(
                               [('HideEULAPage', 'true'),
                                ('HideWirelessSetupInOOBE', 'true'),
                                ('NetworkLocation', 'Work'),
                                ('ProtectYourPC', '1')
                                ])),
                          ('UserAccounts',
                           OrderedDict(
                               [('AdministratorPassword',
                                 OrderedDict(
                                     [('Value', AdministratorPassword),
                                      ('PlainText', 'true')
                                      ])),
                                ])),
                          ('TimeZone', str(TimeZone)),
                          ('FirstLogonCommands',
                           OrderedDict(
                               [('SynchronousCommand',
                                 [OrderedDict(
                                     [('@wcm:action', 'add'),
                                      ('Order', '2'),
                                      ('RequiresUserInput', 'false'),
                                      ('Description', 'AVMA'),
                                      ('CommandLine',
                                       'cscript //B %windir%/system32/'
                                       'slmgr.vbs /ipk '
                                       'C3RCX-M6NRP-6CXC9-TW2F2-4RHYD')
                                      ]),
                                  OrderedDict(
                                      [('@wcm:action', 'add'),
                                       ('Order', '1'),
                                       ('RequiresUserInput', 'false'),
                                       ('Description',
                                        'Enable Remote Desktop Firewall'),
                                       ('CommandLine',
                                        'Netsh advfirewall firewall set rule '
                                        'group="remote desktop" '
                                        'new enable=yes')
                                       ]),
                                  OrderedDict(
                                      [('@wcm:action', 'add'),
                                       ('Order', '3'),
                                       ('Description', 'Windows Updates'),
                                       ('RequiresUserInput', 'false'),
                                       ('CommandLine',
                                        'Usoclient StartDownload StartInsatll'
                                        )
                                       ])])
                                ]))
                          ]),
                      OrderedDict(
                          [('@name', 'Microsoft-Windows-International-Core'),
                           ('@processorArchitecture', 'amd64'),
                           ('@publicKeyToken', '31bf3856ad364e35'),
                           ('@language', 'neutral'),
                           ('@versionScope', 'nonSxS'),
                           ('@xmlns:wcm', 'http://schemas.microsoft.com/'
                                          'WMIConfig/2002/State'),
                           ('@xmlns:xsi', 'http://www.w3.org/2001/'
                                          'XMLSchema-instance'),
                           ('InputLocale', str(InputLocale)),
                           ('SystemLocale', str(SystemLocale)),
                           ('UILanguage', str(UILanguage)),
                           ('UILanguageFallback', str(UILanguageFallback)),
                           ('UserLocale', str(UserLocale))
                           ])])
                    ])])
             ])
    }

    for setting in data['unattend']['settings']:
        for component in setting['component']:
            if component['@name'] == 'Microsoft-Windows-DNS-Client':
                component['Interfaces']['Interface'][
                    'DNSServerSearchOrder']['IpAddress'] = list()
                for i in range(len(DNSs)):
                    component['Interfaces']['Interface'][
                        'DNSServerSearchOrder']['IpAddress'].append(
                        OrderedDict([('@wcm:action', 'add'),
                                     ('@wcm:keyValue', str(i + 1)),
                                     ('#text', str(DNSs[i]))]))
        if UserAccouts:
            if setting['@pass'] == 'oobeSystem':
                for component in setting['component']:
                    if component['@name'] == 'Microsoft-Windows-Shell-Setup':
                        component['UserAccounts']['LocalAccouts'] = \
                            OrderedDict(
                                [('LocalAccount',
                                  OrderedDict(
                                      [('@wcm:action', 'add'),
                                       ('Password',
                                        OrderedDict(
                                            [('Value',
                                              str(UserAccouts[0]['Value'])),
                                             ('PlainText', 'true')
                                             ])),
                                       ('Description', 'User Account'),
                                       ('DisplayName',
                                        str(UserAccouts[0]['Name'])),
                                       ('Group', 'Administrators'),
                                       ('Name',
                                        str(UserAccouts[0]['Name']))
                                       ]))
                                 ])

    return xmltodict.unparse(data, pretty=True)


def vm_build(vm: dict, password: str) -> bool:
    """
    Makes ready answerfile(unattend.xml) in freenas,
    Winrms into host and creates a VM in HyperV
    :param vm: dict object
    :param password: string
    :return:
    """
    vm_built = False
    xml = unattend_xml(vm)
    try:
        with open(path + str(vm['vmname']) + '.xml', 'w') as file:
            file.write(xml)
    except Exception as err:
        driver_logger.error(
            f"Falied to create a answerfile for {vm['vmname']} VM. "
            f"Error:{err}"
        )
        return vm_built
    try:
        session = winrm.Session(vm['hostname'],
                                auth=('administrator', str(password)))

        cmd = "mount \\\\alpha-freenas.cloudcix.com\\mnt\\volume\\" \
              "alpha Z: -o nolock & powershell -file " \
              "Z:\scripts\VMCreator.ps1 -VMName " + vm['vmname'] + \
              " -Gen 1 -OSName WindowsServer2016x64 "\
              "-ProcessorCount " + str(vm['cpu']) + \
              "-Dynamic 1 " + \
              "-Ram " + str(vm['ram']) + \
              " -Hdd " + str(vm['hdd']) + \
              " -Flash " + str(vm['flash']) + \
              " -VlanId " + str(vm['vlan']) + " -Verbose"

        run = session.run_cmd(cmd)
        if run.std_out:
            for line in run.std_out:
                driver_logger.info(line)
            vm_built = True
        elif run.std_err:
            driver_logger.error(run.std_err)
    except Exception as err:
        driver_logger.error(err)

    return vm_built
