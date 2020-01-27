# General Settings
import os
# Import the specific settings
from settings_local import (
    CELERY_HOST,
    CLOUDCIX_API_PASSWORD,
    CLOUDCIX_API_USERNAME,
    CLOUDCIX_EMAIL_USERNAME,
    FREENAS_URL,
    HYPERV_HOST_NETWORK_DRIVE_PATH,
    IN_PRODUCTION,
    KVM_HOST_NETWORK_DRIVE_PATH,
    REGION_NAME,
)

__all__ = [
    'CELERY_HOST',
    'CLOUDCIX_API_KEY',
    'CLOUDCIX_API_PASSWORD',
    'CLOUDCIX_API_URL',
    'CLOUDCIX_API_USERNAME',
    'CLOUDCIX_API_VERSION',
    'CLOUDCIX_API_V2_URL',
    'CLOUDCIX_EMAIL_USERNAME',
    'FREENAS_URL',
    'HYPERV_HOST_NETWORK_DRIVE_PATH',
    'HYPERV_ROBOT_NETWORK_DRIVE_PATH',
    'IN_PRODUCTION',
    'KVM_HOST_NETWORK_DRIVE_PATH',
    'KVM_ROBOT_NETWORK_DRIVE_PATH',
    'CLOUDCIX_LOGSTASH_URL',
    'NETWORK_PASSWORD',
    'REGION_NAME',
    'ROBOT_ENV',
    'VRFS_ENABLED',
    'KVM_VMS_PATH',
    'HYPERV_VMS_PATH',
]

# Member ID
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
# URL of the API
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'
# API V2 Stuff
CLOUDCIX_API_VERSION = 2
CLOUDCIX_API_V2_URL = CLOUDCIX_API_URL
# Database in influx to send to
CLOUDCIX_INFLUX_DATABASE = 'robot'
# Port of influx endpoint
CLOUDCIX_INFLUX_PORT = 443
# Hostname of influx endpoint
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'
# Hostname of logstash for centralised logging
CLOUDCIX_LOGSTASH_URL = 'logstash.cloudcix.com'
# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'
# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')
# Flag to state whether VRFs are enabled or not
VRFS_ENABLED = True
# Configuration settings
# KVM path
KVM_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/KVM'
# KVM vms path
KVM_VMS_PATH = '/var/lib/libvirt/images/'
# HyperV path
HYPERV_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/HyperV'
# HyperV vms path
HYPERV_VMS_PATH = 'D:\HyperV\\'
