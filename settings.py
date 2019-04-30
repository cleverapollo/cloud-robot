# General Settings
import os
# Import the specific settings
from settings_local import (
    CLOUDCIX_API_PASSWORD,
    CLOUDCIX_API_USERNAME,
    CLOUDCIX_EMAIL_PASSWORD,
    CLOUDCIX_EMAIL_USERNAME,
    REGION_NAME,
    FREENAS_URL,
    KVM_HOST_NETWORK_DRIVE_PATH,
    HYPERV_HOST_NETWORK_DRIVE_PATH,
)

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
    'FREENAS_URL',
    'HYPERV_HOST_NETWORK_DRIVE_PATH',
    'HYPERV_ROBOT_NETWORK_DRIVE_PATH',
    'KVM_HOST_NETWORK_DRIVE_PATH',
    'KVM_ROBOT_NETWORK_DRIVE_PATH',
    'LOGSTASH_IP',
    'NETWORK_PASSWORD',
    'OS_TEMPLATE_MAP',
    'REGION_NAME',
    'ROBOT_ENV',
    'VRFS_ENABLED',
]

# Member ID
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
# URL of the API
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'
# API V2 Stuff
CLOUDCIX_API_VERSION = 2
CLOUDCIX_API_V2_URL = CLOUDCIX_API_URL
# Cloudcix email smtp server id with port
CLOUDCIX_EMAIL_HOST = 'webmail.cix.ie:587'
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
# Flag to state whether VRFs are enabled or not
VRFS_ENABLED = True
# Configuration settings
# KVM path
KVM_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/KVM'
# HyperV path
HYPERV_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/HyperV'
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
        3: '2016',
    },
}
