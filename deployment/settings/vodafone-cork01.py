# Vodafone Robot Settings
# Celery host, IP of the machine where the MQ is running
CELERY_HOST = '2a02:2078:11::3'

# CloudCIX API Settings
# Login username
CLOUDCIX_API_USERNAME = 'robot@vodafone-cork01.cloudcix.com'
# Login password
CLOUDCIX_API_PASSWORD = 'vxD12x!?3E'

# Logging Settings
# Name of region (used to tag data sent to influx)
REGION_NAME = 'vodafone-cork01'

# Webmail settings
# Region's email id
CLOUDCIX_EMAIL_USERNAME = 'Vodafone Cork01 <vodafone-cork01@cloudcix.net>'

# Flag stating whether a region is in production or not
IN_PRODUCTION = True

# Configuration settings
# KVM path
KVM_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/KVM'
# HyperV path
HYPERV_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/HyperV'
# Nas drive mount url
NETWORK_DRIVE_URL = f'\\\\{REGION_NAME}-robothost.cloudcix.com\\var\\lib\\libvirt\\robot-drive'
