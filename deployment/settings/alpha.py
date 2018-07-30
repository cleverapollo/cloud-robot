"""python-cloudcix api settings"""
import os
# Alpha Robot Credentials

# LIVE SETTINGS
CLOUDCIX_API_URL = 'https://api.cloudcix.com/'
CLOUDCIX_API_USERNAME = 'robot@alpha.cloudcix.com'
CLOUDCIX_API_PASSWORD = 'C1x@lphA'
CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
CLOUDCIX_AUTH_URL = 'https://keystone.cloudcix.com:5000/v3/'
NETWORK_PASSWORD = 'C1xacc355'
REGION_NAME = 'alpha'
ROBOT_ENV = os.environ.get('ROBOT_ENV', 'dev')
CLOUDCIX_INFLUX_DATABASE = 'robot'
CLOUDCIX_INFLUX_URL = 'influx.cloudcix.com'
CLOUDCIX_INFLUX_PORT = 80


# # STAGE SETTINGS
# CLOUDCIX_API_URL = 'https://stageapi.cloudcix.com/'
# CLOUDCIX_AUTH_URL = 'https://stagekeystone.cloudcix.com:35357/v3/'
# CLOUDCIX_API_USERNAME = 'robot@alpha.cloudcix.com'
# CLOUDCIX_API_PASSWORD = 'C1x@lphA'
# CLOUDCIX_API_KEY = '3bc7cc2bddb34d78b31f1223d0a7408e'
# NETWORK_PASSWORD = 'C1xacc355'
