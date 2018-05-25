######################################################
#                                                    #
#  ro.py is a central location for useful functions  #
#                                                    #
######################################################

# python
import string
import random
from datetime import datetime

# libs
from cloudcix import api

# locals
import utils

TOKEN = utils.Token().token
robot_logger = utils.get_logger_for_name('ro_logger')


def service_entity_create(service: str, entity: str, params: dict) \
        -> [list, None]:
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
        robot_logger.error(
            f"An error occurred while creating {entity.upper()} "
            f"object in {service.upper()} service with params: {str(params)},"
            f" response code={response.status_code}"
        )
    return entity_create


def service_entity_list(service: str, entity: str, params: dict) -> list:
    """
    Gets the list of given entity and params from given service
    :param service: string
    :param entity: string
    :param params: dict
    :return: list
    """
    entity_list = list()
    service_to_call = getattr(api, service)
    # service_to_call = api.iaas  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call(), entity)
    # entity_to_call = api.iaas.image (e.g entity = 'image')
    response = entity_to_call.list(token=TOKEN, params=params)
    if response.status_code == 200:
        entity_list.extend(response.json()['content'])
    else:
        robot_logger.error(
            f"An error occurred while fetching {entity.upper()} "
            f"list from {service.upper()} service with params {str(params)},"
            f" response code={response.status_code}"
        )
    if response.json()['_metadata']['totalRecords'] > 0:
        robot_logger.info(
            f"{len(entity_list)} {entity.upper()}s were found!"
        )
    else:
        robot_logger.info(f"No requested {entity.upper()}s were found!")
    return entity_list


def service_entity_update(service: str, entity: str, params: dict) -> [1, 0]:
    """
    Updates given entity and params from given service
    :param service: string
    :param entity: string
    :param params: dict
    :return: 1 or 0
    """
    service_to_call = getattr(api, service)
    # service_to_call = api.iaas  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call(), entity)
    # entity_to_call = api.iaas.image (e.g entity = 'image')
    params['data']['updated'] = datetime.utcnow()
    response = entity_to_call.partial_update(
        pk=params['pk'], token=TOKEN, data=params['data'])
    # Checking just updation no return of data so 204 No content
    if response.status_code == 204:
        robot_logger.info(
            f"Updated successfully {entity} with id:{params['pk']} "
            f"in {service}"
        )
        return 1
    else:
        robot_logger.error(
            f"An error occurred while updating {entity} in "
            f"{service} service \n {response.content}"
        )
        return 0


def service_entity_read(service: str, entity: str, params: dict) -> dict:
    """
    Reads given entity and params from given service
    :param service: string
    :param entity: string
    :param params: dict
    :return: dict
    """
    entity_read = dict()
    service_to_call = getattr(api, service)
    # service_to_call = api.iaas  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call(), entity)
    # entity_to_call = api.iaas.image (e.g entity = 'image')
    response = entity_to_call.read(pk=params['pk'], token=TOKEN)
    if response.status_code == 200:
        entity_read = response.json()['content']
    else:
        robot_logger.error(
            f"An error occurred while reading {entity} in {service} service"
        )
    return entity_read


def get_idrac_details(location: str) -> tuple:
    """
    Gets the idrac ip address and password of the asset
    given its location as argument
    :param location: string eg "CIX1AGU12"
    :return: ip: ipaddress(string) and password: string
    """
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
        robot_logger.error(
            f"Error generating host password for location: {location}"
        )
    return ip, password


def ip_validations(address_range: str, ip_address: str) -> object:
    """
    This method is used to validate either address_range given in string,
    and separated by commas, if two or more addresses ranges to be validated
    in one request.
    also validates ipaddress given in string,
    and separated by commas, if two or more ipaddresses to be validated in
    one request.
    :param address_range: string
    :param ip_address:string
    :return:dict
    """
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
        except Exception as error:
            robot_logger.info(error)
            return response.json()
    except Exception as err:
        robot_logger.error(
            f"Error occurred while requesting ip_validator of iaas {err}"
        )
    return 0


def fix_run_ps(self, script):
    """
    winrm supporting function, dont make anychanges
    :param self:
    :param script:
    :return:
    """
    from base64 import b64encode
    encoded_ps = b64encode(script.encode('utf_16_le')).decode('ascii')
    rs = self.run_cmd('powershell -encodedcommand {0}'.format(encoded_ps))
    if len(rs.std_err):
        rs.std_err = self._clean_error_msg(rs.std_err.decode('utf-8'))
    return rs


def password_generator(size=8, chars=string.ascii_letters + string.digits):
    """
    Returns a string of random characters, useful in generating temporary
    passwords for automated password resets.

    size: default=8; override to provide smaller/larger passwords
    chars: default=A-Za-z0-9; override to provide more/less diversity
    """
    return ''.join(random.choice(chars) for i in range(size))
