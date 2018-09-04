# General Settings
import os
# Import the specific settings
from settings_local import (
    CLOUDCIX_API_USERNAME,
    CLOUDCIX_API_PASSWORD,
    REGION_NAME,
    CLOUDCIX_EMAIL_USERNAME,
    CLOUDCIX_EMAIL_PASSWORD,
)

# CloudCIX API Settings
# URL of the API
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'
# Member ID
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
# Keystone URL
CLOUDCIX_AUTH_URL = 'https://keystone.cloudcix.com:5000/v3/'

# Password for connecting to routers and servers
NETWORK_PASSWORD = 'C1xacc355'

# Logging Settings
# Env (used in log messages and other things)
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')
# Database in influx to send to
CLOUDCIX_INFLUX_DATABASE = 'robot'
# Hostname of influx endpoint
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'
# Port of influx endpoint
CLOUDCIX_INFLUX_PORT = 80

# Webmail settings
# Cloudcix email smtp server id with port
CLOUDCIX_EMAIL_SMTP = 'webmail.cix.ie:587'
