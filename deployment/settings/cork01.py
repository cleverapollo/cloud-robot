# Cork01 Robot Settings
# Celery host, IP of the machine where the MQ is running
CELERY_HOST = '2a02:2078:4::3'

# CloudCIX API Settings
# Login username
CLOUDCIX_API_USERNAME = 'robot@cork01.cloudcix.com'
# Login password
CLOUDCIX_API_PASSWORD = 'C1xC0rk01'

# Logging Settings
# Name of region (used to tag data sent to influx)
REGION_NAME = 'cork01'

# Webmail settings
# Region's email id
CLOUDCIX_EMAIL_USERNAME = 'CloudCIX Cork01 <cork01@cloudcix.net>'

# Flag stating whether a region is in production or not
IN_PRODUCTION = True

# Configuration settings
# KVM path
KVM_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/KVM'
# HyperV path
HYPERV_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/HyperV'
# FreeNas mount url
FREENAS_URL = f'\\\\{REGION_NAME}-robothost.cloudcix.com\\var\\lib\\libvirt\\robot-drive'
