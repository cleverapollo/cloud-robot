# CloudCIX Alpha Robot Settings
import os

__all__ = [
    'CELERY_HOST',
    'CLOUDCIX_API_KEY',
    'CLOUDCIX_API_PASSWORD',
    'CLOUDCIX_API_URL',
    'CLOUDCIX_API_USERNAME',
    'CLOUDCIX_API_VERSION',
    'CLOUDCIX_API_V2_URL',
    'CLOUDCIX_INFLUX_DATABASE',
    'CLOUDCIX_INFLUX_PORT',
    'CLOUDCIX_INFLUX_URL',
    'COMPUTE_UI_URL',
    'EMAIL_HOST_USER',
    'EMAIL_HOST_PASSWORD',
    'EMAIL_HOST',
    'EMAIL_PORT',
    'EMAIL_REPLY_TO',
    'HYPERV_HOST_NETWORK_DRIVE_PATH',
    'HYPERV_ROBOT_NETWORK_DRIVE_PATH',
    'HYPERV_VMS_PATH',
    'IN_PRODUCTION',
    'KVM_HOST_NETWORK_DRIVE_PATH',
    'KVM_ROBOT_NETWORK_DRIVE_PATH',
    'KVM_VMS_PATH',
    'LOGSTASH_ENABLE',
    'LOGSTASH_PORT',
    'LOGSTASH_URL',
    'NETWORK_DRIVE_URL',
    'NETWORK_PASSWORD',
    'REGION_NAME',
    'ROBOT_ENV',
    'SEND_TO_FAIL',
    'SUBJECT_PROJECT_FAIL',
    'SUBJECT_SNAPSHOT_BUILD_FAIL',
    'SUBJECT_SNAPSHOT_FAIL',
    'SUBJECT_VM_FAIL',
    'SUBJECT_VM_SCHEDULE_DELETE',
    'SUBJECT_VM_SUCCESS',
    'SUBJECT_VPN_BUILD_SUCCESS',
    'SUBJECT_VPN_UPDATE_SUCCESS',
    'SUBJECT_VIRTUAL_ROUTER_FAIL',
    'SRX_GATEWAY',
    'VIRTUAL_ROUTERS_ENABLED',
]

"""
Robot Settings
"""
# Celery host, IP of the machine where the MQ is running
CELERY_HOST = '2a02:2078:3::3'

# Flag stating whether a region is in production or not
IN_PRODUCTION = False  # Alpha should never have this set to True

# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'

"""
CloudCIX API Settings
"""
# CloudCIX Member API Key
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'

# CloudCIX Login password
CLOUDCIX_API_PASSWORD = 'asdf1234'

# URL of the API
CLOUDCIX_API_URL = 'https://stageapi.cloudcix.com/'

# CLoudcIX Login username
CLOUDCIX_API_USERNAME = 'robot@alpha.cloudcix.com'

# API V2
CLOUDCIX_API_VERSION = 2

CLOUDCIX_API_V2_URL = 'https://stage.api.cloudcix.com/'

"""
Email settings
"""
# Compute UI URL - Required in Email Templates
COMPUTE_UI_URL = f'https://stagesaas.cloudcix.com/compute/'

# Login Email Address to
EMAIL_HOST_USER = 'alpha@cloudcix.net'

# Login Password for EMAIL_HOST_USER
EMAIL_HOST_PASSWORD = 'AlphaC1xacc355'

# URL of Email Host
EMAIL_HOST = 'mail.cloudcix.net'

EMAIL_PORT = 25

# Reply-To Email Address
EMAIL_REPLY_TO = 'CloudCIX <no-reply@cloudcix.net>'

# Email to send build fail emails to
SEND_TO_FAIL = 'developers@cloudcix.com'

# Subject for Project build fail Emails
SUBJECT_PROJECT_FAIL = '[CloudCIX] VM Failure Occurred!'

# Subject for Snapshot build fail Emails
SUBJECT_SNAPSHOT_BUILD_FAIL = f'[CloudCIX] Your Snapshot has failed to build.'

# Subject for Snapshot fail Emails
SUBJECT_SNAPSHOT_FAIL = f'[CloudCIX] Snapshot Failure Occurred!'

# Subject for VM build fail Emails
SUBJECT_VM_FAIL = '[CloudCIX] Your VM  has failed to build.'

# Subject for VM scheduled to be deleted
SUBJECT_VM_SCHEDULE_DELETE = '[CloudCIX] Your VM has been scheduled for deletion!'

# Subject for VM build success Emails
SUBJECT_VM_SUCCESS = '[CloudCIX] Your VM has been built successfully!'

# Subject for VPN tunnel build success Emails
SUBJECT_VPN_BUILD_SUCCESS = '[CloudCIX] Your VPN Tunnel has been built successfully!'

# Subject for VPN tunnel update success Emails
SUBJECT_VPN_UPDATE_SUCCESS = '[CloudCIX] Your VPN Tunnel has been updated successfully!'

# Subject for VIRTUAL_ROUTER build fail Emails
SUBJECT_VIRTUAL_ROUTER_FAIL = '[CloudCIX] Virtual Router Failure Occurred!'

"""
Logging Settings
"""
LOGSTASH_ENABLE = True
LOGSTASH_PORT = 5959
# Hostname of logstash for centralised logging
LOGSTASH_URL = 'logstash.cloudcix.com'

# Name of region (used to tag data sent to influx)
REGION_NAME = 'alpha'

# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')

"""
 Real Time Monitoring Settings
 """
# Database in influx to send to
CLOUDCIX_INFLUX_DATABASE = 'robot'

# Flag to state whether VIRTUAL_ROUTERs are enabled or not
VIRTUAL_ROUTERS_ENABLED = True

# Port of influx endpoint
CLOUDCIX_INFLUX_PORT = 443

# Hostname of influx endpoint
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'

"""
Configuration settings
"""
# KVM path
KVM_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/KVM'
KVM_HOST_NETWORK_DRIVE_PATH = KVM_ROBOT_NETWORK_DRIVE_PATH
# KVM vms path
KVM_VMS_PATH = '/var/lib/libvirt/images/'
# HyperV path
HYPERV_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/HyperV'
HYPERV_HOST_NETWORK_DRIVE_PATH = HYPERV_ROBOT_NETWORK_DRIVE_PATH
# HyperV vms path
HYPERV_VMS_PATH = r'D:\HyperV\\'
# Nas drive mount url
NETWORK_DRIVE_URL = f'\\\\{REGION_NAME}-freenas.cloudcix.com\\mnt\\volume\\{REGION_NAME}'

# SRX Gateway address or dns name
SRX_GATEWAY = '185.49.62.254'
