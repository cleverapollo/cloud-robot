import os

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
    'NETWORK_PASSWORD',
    'REGION_NAME',
    'ROBOT_ENV',
    'VRFS_ENABLED',
]

# Gov Robot Settings

# CloudCIX API Settings
# Member ID
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
# Login password
CLOUDCIX_API_PASSWORD = 'C0rkG0vC1xacc355'
# URL of the API
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'
# Login username
CLOUDCIX_API_USERNAME = 'robot@cork.cloudcix.com'
# API V2 Stuff
CLOUDCIX_API_VERSION = 2
CLOUDCIX_API_V2_URL = CLOUDCIX_API_URL

# Webmail settings
# Cloudcix email smtp server id with port
CLOUDCIX_EMAIL_HOST = 'webmail.cix.ie:587'
# Region's email password
CLOUDCIX_EMAIL_PASSWORD = 'C0rkG0vC1xacc355'
# Region's email id
CLOUDCIX_EMAIL_USERNAME = 'cloud@cloudcix.com'

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

# Logging Settings
# Name of region (used to tag data sent to influx)
REGION_NAME = 'gov_cork'

# Disable VRFs for the GovCloud Robots
VRFS_ENABLED = False