# python
import os

# libs
os.environ.setdefault('CLOUDCIX_SETTINGS_MODULE', "settings")
from cloudcix import api
from cloudcix.utils import get_admin_session

# local
import utils
# Important stuff
TOKEN = get_admin_session().get_token()


def vrf(state: int):
    """
    Finds the first VRF in the API with the given state

    :param state: The state for which to find a VRF
    :returns: A VRF instance or None
    """
    response = api.iaas.vrf.list(token=TOKEN, params={'state': state})
    if response.status_code == 200:
        data = response.json()
        if data['_metadata']['totalRecords'] > 0:
            return data['content'][0]['idVRF']
    else:
        utils.get_logger_for_name('state:vrf').error('({}): {}'.format(
            response.status_code,
            str(response.json())))
    return None


def vm(state: int):
    """
    Finds the first VM in the API with the given state

    :param state: The state for which to find a VM
    :returns: A VM instance or None
    """
    response = api.iaas.vm.list(token=TOKEN, params={'state': state})
    if response.status_code == 200:
        data = response.json()
        if data['_metadata']['totalRecords'] > 0:
            return data['content'][0]['idVM']
    else:
        utils.get_logger_for_name('state:vm').error('({}): {}'.format(
            response.status_code,
            str(response.json())))
    return None
