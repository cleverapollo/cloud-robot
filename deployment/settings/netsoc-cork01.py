# CloudCIX NetSOC Cork01 Robot Settings
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
    'HYPERV_HOST_NETWORK_DRIVE_PATH',
    'HYPERV_ROBOT_NETWORK_DRIVE_PATH',
    'HYPERV_VMS_PATH',
    'IN_PRODUCTION',
    'INFLUX_DATABASE',
    'INFLUX_PORT',
    'INFLUX_URL',
    'KVM_HOST_NETWORK_DRIVE_PATH',
    'KVM_ROBOT_NETWORK_DRIVE_PATH',
    'KVM_VMS_PATH',
    'LOGSTASH_URL',
    'NETWORK_DRIVE_URL',
    'NETWORK_PASSWORD',
    'NOT_FOUND_STATUS_CODE',
    'PRIVATE_PORT',
    'PUBLIC_PORT',
    'REGION_NAME',
    'ROBOT_ENV',
    'SEND_TO_FAIL',
    'SUBJECT_PROJECT_FAIL',
    'SUBJECT_VM_FAIL',
    'SUBJECT_VM_SCHEDULE_DELETE',
    'SUBJECT_VM_SUCCESS',
    'SUBJECT_VPN_SUCCESS',
    'SUBJECT_VR_FAIL',
    'SUCCESS_STATUS_CODE',
    'UPDATE_STATUS_CODE',
    'VRS_ENABLED',
]

"""
Robot Settings
"""
# Celery host, IP of the machine where the MQ is running
CELERY_HOST = '2a02:2078:9::3'

# Flag stating whether a region is in production or not
IN_PRODUCTION = True

# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'

# Flag to state whether VRs are enabled or not
VRS_ENABLED = True

"""
CloudCIX API Settings
"""
# CloudCIX Member API Key
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'

# CloudCIX Login password
CLOUDCIX_API_PASSWORD = 'N3t50c#1'

# URL of the API
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'

# CLoudcIX Login username
CLOUDCIX_API_USERNAME = 'robot@netsoc-cork01.cloudcix.com'

# API V2
CLOUDCIX_API_VERSION = 2

# URL for CloudCIX API Version 2
CLOUDCIX_API_V2_URL = CLOUDCIX_API_URL

"""
Email settings
"""
# Compute UI URL - Required in Email Templates
COMPUTE_UI_URL = 'https://saas.cloudcix.com/compute/'

# Login Email Address
EMAIL_HOST_USER = 'notification@cloudcix.net'

# Login Password for EMAIL_HOST_USER
EMAIL_HOST_PASSWORD = 'C1xacc355'

# URL of Email Host
EMAIL_HOST = 'mail.cloudcix.net'

EMAIL_PORT = 25

# Reply-To Email Address
EMAIL_REPLY_TO = 'CloudCIX <no-reply@cloudcix.net>'

# Region's email id
EMAIL_USERNAME = 'Netsoc Cork01 <netsoc-cork01@cloudcix.net>'

# Email to send build fail emails to
SEND_TO_FAIL = 'developers@cloudcix.com'

# Subject for Project build fail Emails
SUBJECT_PROJECT_FAIL = '[CloudCIX] VM Failure Occurred!'

# Subject for VM build fail Emails
SUBJECT_VM_FAIL = '[CloudCIX] Your VM  has failed to build.'

# Subject for VM scheduled to be deleted
SUBJECT_VM_SCHEDULE_DELETE = '[CloudCIX] Your VM has been scheduled for deletion!'

# Subject for VM build success Emails
SUBJECT_VM_SUCCESS = '[CloudCIX] Your VM has been built successfully!'

# Subject for VPN tunnel build success Emails
SUBJECT_VPN_SUCCESS = '[CloudCIX] Your VPN Tunnel has been built successfully!'

# Subject for VR build fail Emails
SUBJECT_VR_FAIL = '[CloudCIX] VR Failure Occurred!'

"""
Logging Settings
"""
# Hostname of logstash for centralised logging
LOGSTASH_URL = 'logstash.cloudcix.com'

# Name of region (used to tag data sent to influx)
REGION_NAME = 'netsoc-cork01'

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
INFLUX_URL = 'influx.cloudcix.com'

"""
Configuration settings
"""
# KVM path
KVM_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/KVM'
KVM_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/KVM'
# KVM vms path
KVM_VMS_PATH = '/var/lib/libvirt/images/'
# HyperV path
HYPERV_ROBOT_NETWORK_DRIVE_PATH = '/mnt/images/HyperV'
HYPERV_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/HyperV'
# HyperV vms path
HYPERV_VMS_PATH = r'D:\HyperV\\'
# Nas drive mount url
NETWORK_DRIVE_URL = f'\\\\{REGION_NAME}-robothost.cloudcix.com\\var\\lib\\libvirt\\robot-drive'
# Api response code
NOT_FOUND_STATUS_CODE = 404
SUCCESS_STATUS_CODE = 200
UPDATE_STATUS_CODE = 204

"""
Router settings, are required if VRS_ENABLED is True
"""
# Public port e.g 'ge-0/0/0'
PUBLIC_PORT = 'ge-0/0/0'
# Private port e.g 'ge-0/0/0'
PRIVATE_PORT = 'ge-0/0/1'
