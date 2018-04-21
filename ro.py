######################################################
#                                                    #
#  ro.py is a central location for useful functions  #
#                                                    #
######################################################

# python
import os
from datetime import datetime

#libs
from cloudcix import api
from cloudcix.utils import get_admin_session

# locals
import utils

os.environ.setdefault("CLOUDCIX_SETTINGS_MODULE", 'settings')
TOKEN = get_admin_session().get_token()
robot_logger = utils.get_logger_for_name('robot')


def service_entity_create(service, entity, params):
    """
    Create given entity into a service with params
    :param service: string
    :param entity: string
    :param params: dict
    :return: list or empty string
    """
    entity_create = None
    service_to_call = getattr(api, service)
    # service_to_call = api.iaas  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call(), entity)
    # entity_to_call = api.iaas.image (e.g entity = 'image')
    response = entity_to_call.create(token=TOKEN, params=params)
    if response.status_code == 201:
        entity_create = response.json()['content']
    else:
        robot_logger.error("\033[91m An error occurred while creating %s "
                           "object in %s service with params: %s \033[00m"
                     % (entity.upper(), service.upper(), str(params)))
        robot_logger.error(response.status_code)
        return 0
    return entity_create


# Gets the list of given entity and params from given service
def service_entity_list(service, entity, params):
    entity_list = list()
    service_to_call = getattr(api, service)
    # service_to_call = api.iaas  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call(), entity)
    # entity_to_call = api.iaas.image (e.g entity = 'image')
    response = entity_to_call.list(token=TOKEN, params=params)
    if response.status_code == 200:
        entity_list.extend(response.json()['content'])
    else:
        robot_logger.error("\033[91m An error occurred while fetching %s "
                           "list from %s service with params %s\033[00m"
                     % (entity.upper(), service.upper(), str(params)))
        robot_logger.error(response.status_code)
        return 0
    if response.json()['_metadata']['totalRecords'] > 0:
        robot_logger.info("\033[92m %d %ss were found! \033[00m"
              % (len(entity_list), entity.upper()))
    else:
        robot_logger.info("No requested %ss were found!" % entity.upper())
    return entity_list


# Updates given entity and params from given service
def service_entity_update(service, entity, params):
    service_to_call = getattr(api, service)
    # service_to_call = api.iaas  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call(), entity)
    # entity_to_call = api.iaas.image (e.g entity = 'image')
    params['data']['updated'] = datetime.utcnow()
    response = entity_to_call.partial_update(
        pk=params['pk'], token=TOKEN, data=params['data'])
    # Checking just updation no return of data so 204 No content
    if response.status_code == 204:
        robot_logger.info(" Updated successfully %s with id:%d in %s"
                    %(entity, params['pk'], service))
        return 1
    else:
        robot_logger.error("An error occurred while updating %s in "
              "%s service \n %s" % (entity, service, response.content))
        return 0


# Reads given entity and params from given service
def service_entity_read(service, entity, params):
    entity_read = dict()
    service_to_call = getattr(api, service)
    # service_to_call = api.iaas  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call(), entity)
    # entity_to_call = api.iaas.image (e.g entity = 'image')
    response = entity_to_call.read(pk=params['pk'], token=TOKEN)
    if response.status_code == 200:
        entity_read = response.json()['content']
    else:
        robot_logger.error("\033[91m An error occurred while reading %s in "
              "%s service \033[00m" % (entity, service))
    return entity_read


# Gets the idrac ip address and password of the asset
#   given its location as argument
def get_idrac_details(location):
    location = location.replace(" ", "")  # Remove white spaces
    # Find the ipaddress
    if location[:5] == "CIX1A":
        ip = "10.253"
    elif location[:5] == "CIX1B":
        ip = "10.252"
    elif location[:5] == "CIX1C":
        ip = "10.251"
    else:
        ip = "Undefined"

    base = 0
    if ip != "Undefined":
        if location[5] in ["A", "G", "M"]:
            base = 0
        if location[5] in ["B", "H", "N"]:
            base = 20
        if location[5] in ["C", "I", "O"]:
            base = 40
        if location[5] in ["D", "J", "P"]:
            base = 60
        if location[5] in ["E", "K", "Q"]:
            base = 80
        if location[5] in ["F", "L", "R"]:
            base = 80
    rack = location.split(location[:5])[-1]
    ip += '.' + str(base + int(rack[1: 3]))
    ip += '.' + rack[rack.index('U') + 1:]

    # Get the password
    response = api.iaas.location_hasher.create(token=TOKEN,
                                               data={'location': location})
    password = ''
    if response.status_code in [200, 201]:
        password = response.json()['content']['hexadecimal']
    else:
        robot_logger.error("Error generating host password for location: %s"
                     %location)
    return ip, password


def ip_validations(address_range='', ip_address=""):
    params = dict()
    if address_range:
        params['address_range'] = address_range
    if ip_address:
        params['ip_address'] = ip_address
    try:
        response = api.iaas.ip_validator.list(token=TOKEN, params=params)
        try:
            if response.json()['response_code'] == 400:
                return False
        except Exception:
            return response.json()
    except Exception as err:
        robot_logger.error("Error occurred while requesting ip_validator "
                           "of iaas %s" %err)

#-------------------------------------------------------------------------
# winrm supporting function, dont make anychanges
def fix_run_ps(self, script):
    from base64 import b64encode
    encoded_ps = b64encode(script.encode('utf_16_le')).decode('ascii')
    rs = self.run_cmd('powershell -encodedcommand {0}'.format(encoded_ps))
    if len(rs.std_err):
        rs.std_err = self._clean_error_msg(rs.std_err.decode('utf-8'))
    return rs
#------------------------------------------------------------------------


