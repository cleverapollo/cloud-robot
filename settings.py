# General Settings
import os
# Import the specific settings
from settings_local import (
    CLOUDCIX_API_PASSWORD,
    CLOUDCIX_API_USERNAME,
    CLOUDCIX_EMAIL_PASSWORD,
    CLOUDCIX_EMAIL_USERNAME,
    REGION_NAME,
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
    'LOGSTASH_IP',
    'NETWORK_PASSWORD',
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
