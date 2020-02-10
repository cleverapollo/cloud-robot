import os

__all__ = [
    'CELERY_HOST',
    'CLOUDCIX_API_KEY',
    'CLOUDCIX_API_PASSWORD',
    'CLOUDCIX_API_URL',
    'CLOUDCIX_API_USERNAME',
    'CLOUDCIX_API_VERSION',
    'CLOUDCIX_API_V2_URL',
    'CLOUDCIX_EMAIL_USERNAME',
    'CLOUDCIX_INFLUX_DATABASE',
    'CLOUDCIX_INFLUX_PORT',
    'CLOUDCIX_INFLUX_URL',
    'HYPERV_HOST_NETWORK_DRIVE_PATH',
    'HYPERV_ROBOT_NETWORK_DRIVE_PATH',
    'HYPERV_VMS_PATH',
    'IN_PRODUCTION',
    'KVM_HOST_NETWORK_DRIVE_PATH',
    'KVM_ROBOT_NETWORK_DRIVE_PATH',
    'KVM_VMS_PATH',
    'CLOUDCIX_LOGSTASH_URL',
    'NETWORK_DRIVE_URL',
    'NETWORK_PASSWORD',
    'NOT_FOUND_STATUS_CODE',
    'REGION_NAME',
    'ROBOT_ENV',
    'SUCCESS_STATUS_CODE',
    'UPDATE_STATUS_CODE',
    'VRS_ENABLED',
]

# Gov Robot Settings
# Celery host, IP of the machine where the MQ is running
CELERY_HOST = '10.13.1.3'

# CloudCIX API Settings
# Member ID
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
# Login password
CLOUDCIX_API_PASSWORD = 'C0rkG0vC1xacc355'
# URL of the API
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'
# Login username
CLOUDCIX_API_USERNAME = 'robot@cork.cloudcix.com'
# API V2 Stuff
CLOUDCIX_API_VERSION = 2
CLOUDCIX_API_V2_URL = CLOUDCIX_API_URL

# Webmail settings
# Region's email id
CLOUDCIX_EMAIL_USERNAME = 'cloud@cloudcix.net'

# Database in influx to send to
CLOUDCIX_INFLUX_DATABASE = 'robot'
# Port of influx endpoint
CLOUDCIX_INFLUX_PORT = 443
# Hostname of influx endpoint
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'

# Hostname of logstash for centralised logging
CLOUDCIX_LOGSTASH_URL = 'logstash.cloudcix.com'

# Flag stating whether a region is in production or not
IN_PRODUCTION = False

# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'

# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')

# Logging Settings
# Name of region (used to tag data sent to influx)
REGION_NAME = 'gov_cork'

# Disable VRs for the GovCloud Robots
VRS_ENABLED = False

# Configuration settings
# KVM path
KVM_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/KVM'
KVM_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/KVM'
# KVM vms path
KVM_VMS_PATH = '/var/lib/libvirt/images/'
# HyperV path
HYPERV_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/HyperV'
HYPERV_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/HyperV'
# HyperV vms path
HYPERV_VMS_PATH = 'D:\HyperV\\'
# Nas drive mount url
NETWORK_DRIVE_URL = f'\\\\{REGION_NAME}-robothost.cloudcix.com\\var\\lib\\libvirt\\robot-drive'
# Api response code
NOT_FOUND_STATUS_CODE = 404
SUCCESS_STATUS_CODE = 200
UPDATE_STATUS_CODE = 204
