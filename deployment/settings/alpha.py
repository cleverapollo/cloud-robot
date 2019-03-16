# Alpha Robot Settings
# Doesn't use base as it's fundamentally different

import os

__all__ = [
    'CLOUDCIX_API_KEY',
    'CLOUDCIX_API_PASSWORD',
    'CLOUDCIX_API_URL',
    'CLOUDCIX_API_USERNAME',
    'CLOUDCIX_API_VERSION',
    'CLOUDCIX_API_V2_URL',
    'CLOUDCIX_EMAIL_HOST',
    'CLOUDCIX_EMAIL_PASSWORD',
    'CLOUDCIX_EMAIL_USERNAME',
    'LOGSTASH_IP',
    'NETWORK_PASSWORD',
    'REGION_NAME',
    'ROBOT_ENV',
    'VRFS_ENABLED',
    'KVM_DRIVE_PATH',
    'HYV_DRIVE_PATH',
    'FREENAS_URL',
    'OS_TEMPLATE_MAP',
]

# Gov Robot Settings

# CloudCIX API Settings
# Member ID
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
# Login password
CLOUDCIX_API_PASSWORD = 'C1x@lphA'
# URL of the API
CLOUDCIX_API_URL = 'https://stageapi.cloudcix.com/'
# Login username
CLOUDCIX_API_USERNAME = 'robot@alpha.cloudcix.com'
# API V2 Stuff
CLOUDCIX_API_VERSION = 2
CLOUDCIX_API_V2_URL = 'https://stage.api.cloudcix.com/'

# Webmail settings
# Cloudcix email smtp server id with port
CLOUDCIX_EMAIL_HOST = 'webmail.cix.ie:587'
# Region's email password
CLOUDCIX_EMAIL_PASSWORD = 'AlphaC1xacc355'
# Region's email id
CLOUDCIX_EMAIL_USERNAME = 'alpha@cloudcix.com'

# Database in influx to send to
CLOUDCIX_INFLUX_DATABASE = 'robot'
# Port of influx endpoint
CLOUDCIX_INFLUX_PORT = 443
# Hostname of influx endpoint
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'

# IP Address of logstash for centralised logging
LOGSTASH_IP = '2a02:2078:0:cb00::f12'

# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'

# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')

# Logging Settings
# Name of region (used to tag data sent to influx)
REGION_NAME = 'alpha'

# Flag to state whether VRFs are enabled or not
VRFS_ENABLED = True

# Configuration settings
# KVM path
KVM_DRIVE_PATH = '/mnt/images/KVM'
# HyperV path
HYV_DRIVE_PATH = '/mnt/images/HyperV'
# FreeNas mount url
FREENAS_URL = f'\\\\{REGION_NAME}-freenas.cloudcix.com\\mnt\\volume\\{REGION_NAME}'
# Images dict
OS_TEMPLATE_MAP = {
    'Linux': {
        6: 'ubuntu',
        7: 'ubuntu',
        8: 'ubuntu',
        9: 'ubuntu',
        10: 'centos',
        11: 'centos',
        12: 'ubuntu',
    },
    'Windows': {
        3: 'windows2016',
    },
}
