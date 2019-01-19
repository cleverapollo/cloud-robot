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
    'CLOUDCIX_EMAIL_HOST',
    'CLOUDCIX_EMAIL_PASSWORD',
    'CLOUDCIX_EMAIL_USERNAME',
    'NETWORK_PASSWORD',
    'REGION_NAME',
    'ROBOT_ENV',
]

# Member ID
CLOUDCIX_API_ID_MEMBER = '3bc7cc2bddb34d78b31f1223d0a7408e'
# URL of the API
CLOUDCIX_SERVER_URL= 'https://api.cloudcix.com/'
# Cloudcix email smtp server id with port
CLOUDCIX_EMAIL_HOST = 'webmail.cix.ie:587'
# Database in influx to send to
CLOUDCIX_INFLUX_DATABASE = 'robot'
# Port of influx endpoint
CLOUDCIX_INFLUX_PORT = 443
# Hostname of influx endpoint
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'
# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'
# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')
