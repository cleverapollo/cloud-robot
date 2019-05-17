# Toronto01 Robot Settings
# Celery host, IP of the machine where the MQ is running
CELERY_HOST = '2a02:2078:5::3'

# CloudCIX API Settings
# Login username
CLOUDCIX_API_USERNAME = 'robot@toronto01.cloudcix.com'
# Login password
CLOUDCIX_API_PASSWORD = 'T0roN7@C1x'

# Logging Settings
# Name of region (used to tag data sent to influx)
REGION_NAME = 'toronto01'

# Webmail settings
# Region's email id
CLOUDCIX_EMAIL_USERNAME = 'toronto01@cloudcix.com'
# Region's email password
CLOUDCIX_EMAIL_PASSWORD = 'T0ronto01C1xacc355'

# Configuration settings
# KVM path
KVM_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/KVM'
# HyperV path
HYPERV_HOST_NETWORK_DRIVE_PATH = '/var/lib/libvirt/ISOs/HyperV'
# FreeNas mount url
FREENAS_URL = f'\\\\{REGION_NAME}-robothost.cloudcix.com\\var\\lib\\libvirt'
