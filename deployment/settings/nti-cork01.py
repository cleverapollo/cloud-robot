# CloudCIX NTI-Cork01 Robot Settings
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
    'SUBJECT_BACKUP_BUILD_FAIL',
    'SUBJECT_BACKUP_FAIL',
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
CELERY_HOST = '2a02:2078:8::3'

# Flag stating whether a region is in production or not
IN_PRODUCTION = True

# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'

# Flag to state whether VIRTUAL_ROUTERs are enabled or not
VIRTUAL_ROUTERS_ENABLED = True

"""
CloudCIX API Settings
"""
# CloudCIX Member API Key
CLOUDCIX_API_KEY = 'e4aaf6e65eda03cc8aac20a26ea52c1d69cc904fe3cc2f296b9a6aefb84318d9'

# CloudCIX Login password
CLOUDCIX_API_PASSWORD = 'NT1C0rk01C1xacc355'

# URL of the API
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'

# CLoudcIX Login username
CLOUDCIX_API_USERNAME = 'robot@nti-cork01.cloudcix.com'

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
EMAIL_HOST_USER = 'nti-cork01@cloudcix.net'

# Login Password for EMAIL_HOST_USER
EMAIL_HOST_PASSWORD = 'Nt1R3g10n!'

# URL of Email Host
EMAIL_HOST = 'mail.cloudcix.net'

EMAIL_PORT = 25

# Reply-To Email Address
EMAIL_REPLY_TO = 'CloudCIX <no-reply@cloudcix.net>'

# Email to send build fail emails to
SEND_TO_FAIL = 'developers@cloudcix.com,noc@cix.ie'

# Subject for Backups build fails
SUBJECT_BACKUP_BUILD_FAIL = f'[CloudCIX] Your Backup has failed to build.'

# Subject for Backup fails
SUBJECT_BACKUP_FAIL = f'[CloudCIX] Backup Failure Occurred!'

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
REGION_NAME = 'nti-cork01'

# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')

"""
 Real Time Monitoring Settings
 """
# Database in influx to send to
CLOUDCIX_INFLUX_DATABASE = 'robot'

# Port of influx endpoint
CLOUDCIX_INFLUX_PORT = 443

# Hostname of influx endpoint
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'

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

# SRX Gateway address or dns name
SRX_GATEWAY = '91.103.1.62'

"""
Backup Settings
"""
# HyperV primary backup location
HYPERV_PRIMARY_BACKUP_STORAGE_PATH = 'P:\\'
# HyperV secondary backup location
HYPERV_SECONDARY_BACKUP_STORAGE_PATH = 'S:\\'
# KVM primary backup location
KVM_PRIMARY_BACKUP_STORAGE_PATH = '/mnt/backup-p/'
# KVM secondary backup location
KVM_SECONDARY_BACKUP_STORAGE_PATH = '/mnt/backup-s/'
