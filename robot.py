import os
os.environ.setdefault('CLOUDCIX_SETTINGS_MODULE', "settings")
from cloudcix import api
from cloudcix.utils import get_admin_session
TOKEN = get_admin_session().get_token()
import time
import logging
import logging.handlers


last = time.time()

fmt = logging.Formatter(fmt="%(asctime)s - %(name)s: %(levelname)s: %(message)s", datefmt="%d/%m/%y @ %H:%M:%S")
robot_logger = logging.getLogger('robot')
robot_logger.setLevel(logging.INFO)
# Get a file handler
handler = logging.handlers.RotatingFileHandler('/var/log/robot/robot.log', maxBytes=4096, backupCount=7)
handler.setFormatter(fmt)
robot_logger.addHandler(handler)


def vrfState(state):
    response = api.iaas.vrf.list(token=TOKEN, params={'state': state})
    if response.status_code == 200 and response.json()['_metadata']['totalRecords'] > 0:
        content=response.json()['content']
        return (content[0]['idVRF'])
    else:
        return(None)

def vmState(state):
    response = api.iaas.vm.list(token=TOKEN, params={'state': state})
    if response.status_code == 200 and response.json()['_metadata']['totalRecords'] > 0:
        content=response.json()['content']
        return (content['idVM'])
    else:
        return(None)

while True:
    idVRF = vrfState(1)
    # idVRF = vrfState(1)
    if idVRF != None:
        robot_logger.info('Building idVRF %i' % idVRF)
        # vrfBuilder(idVRF)
        pass
    else:
        robot_logger.info('No VRF in "Requested" state.')
    idVM = vmState(1)
    if idVM != None:
        robot_logger.info('Building idVM %i' % idVM)
        # vmBuild(idVM)
        pass
    else:
        robot_logger.info('No VM in "Requested" state. ')

    while last > time.time() - 20:
        time.sleep(1)
    last = time.time()
