# CloudCIX Region_N+1 Robot Settings
import os

__all__ = [
    'CELERY_HOST',
    'CLOUDCIX_API_KEY',
    'CLOUDCIX_API_PASSWORD',
    'CLOUDCIX_API_URL',
    'CLOUDCIX_API_USERNAME',
    'CLOUDCIX_API_VERSION',
    'CLOUDCIX_API_V2_URL',
    'COMPUTE_UI_URL',
    'EMAIL_HOST_USER',
    'EMAIL_HOST_PASSWORD',
    'EMAIL_HOST',
    'EMAIL_PORT',
    'EMAIL_REPLY_TO',
    'EMAIL_USERNAME',
    'FREENAS_URL',
    'HYPERV_HOST_NETWORK_DRIVE_PATH',
    'HYPERV_ROBOT_NETWORK_DRIVE_PATH',
    'IN_PRODUCTION',
    'INFLUX_DATABASE',
    'INFLUX_PORT',
    'INFLUX_URL',
    'KVM_HOST_NETWORK_DRIVE_PATH',
    'KVM_ROBOT_NETWORK_DRIVE_PATH',
    'LOGSTASH_URL',
    'NETWORK_PASSWORD',
    'OS_TEMPLATE_MAP',
    'REGION_NAME',
    'ROBOT_ENV',
    'SEND_TO_FAIL',
    'SUBJECT_PROJECT_FAIL',
    'SUBJECT_VM_FAIL',
    'SUBJECT_VM_SCHEDULE_DELETE',
    'SUBJECT_VM_SUCCESS',
    'SUBJECT_VPN_SUCCESS',
    'SUBJECT_VRF_FAIL',
    'VRFS_ENABLED',
]

"""
Robot Settings
"""
# Celery host, IP of the machine where the MQ is running
CELERY_HOST = ''

# Flag stating whether a region is in production or not
IN_PRODUCTION = False

# Password for connecting to routers and servers
NETWORK_PASSWORD = ''

# Flag to state whether VRFs are enabled or not
VRFS_ENABLED = True

"""
CloudCIX API Settings
"""
# CloudCIX Member API Key
CLOUDCIX_API_KEY = ''

# CloudCIX Login password
CLOUDCIX_API_PASSWORD = ''

# URL of the API
CLOUDCIX_API_URL = ''

# API V2
CLOUDCIX_API_VERSION = 2

# API V2 URL
CLOUDCIX_API_V2_URL = ''

# CLoudcIX Login username
CLOUDCIX_API_USERNAME = ''

"""
Email settings
"""
# Compute UI URL
COMPUTE_UI_URL = ''

# Login Email Address
EMAIL_HOST_USER = ''

# Login Password for EMAIL_HOST_USER
EMAIL_HOST_PASSWORD = ''

# URL of Email Host
EMAIL_HOST = ''

EMAIL_PORT = 25

# Reply-To Email Address
EMAIL_REPLY_TO = ''

# Region's email id
EMAIL_USERNAME = ''

# Email to send build fail emails to
SEND_TO_FAIL = ''

# Subject for Project build fail Emails
SUBJECT_PROJECT_FAIL = ''

# Subject for VM build fail Emails
SUBJECT_VM_FAIL = ''

# Subject for VM scheduled to be deleted
SUBJECT_VM_SCHEDULE_DELETE = ''

# Subject for VM build success Emails
SUBJECT_VM_SUCCESS = ''

# Subject for VPN tunnel build success Emails
SUBJECT_VPN_SUCCESS = ''

# Subject for VRF build fail Emails
SUBJECT_VRF_FAIL = ''

"""
Logging Settings
"""
# Hostname of logstash for centralised logging
LOGSTASH_URL = ''

# Name of region (used to tag data sent to influx)
REGION_NAME = ''

# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')

"""
 Real Time Monitoring Settings
 """
# Database in influx to send to
INFLUX_DATABASE = 'robot'

# Port of influx endpoint
INFLUX_PORT = 443

# Hostname of influx endpoint
INFLUX_URL = ''

"""
Configuration settings
"""
# KVM path
KVM_ROBOT_NETWORK_DRIVE_PATH = ''
KVM_HOST_NETWORK_DRIVE_PATH = ''

# HyperV path
HYPERV_ROBOT_NETWORK_DRIVE_PATH = ''
HYPERV_HOST_NETWORK_DRIVE_PATH = ''

# FreeNas mount url
FREENAS_URL = ''

# Images Dictionary e.g 'Linux: {image_id: 'image_type'} e.g. Linux: {1: 'ubntu', 2: 'centos'}
OS_TEMPLATE_MAP = {
    'Linux': {},
    'Windows': {},
    'Phantom': {},
}
