######################################################
#                                                    #
#  ro.py is a central location for useful functions  #
#                                                    #
######################################################

# python
import random
import string

from typing import Optional, Tuple

# libs
from cloudcix import api

# locals
import utils

TOKEN_WRAPPER = utils.Token()


def service_entity_create(srv: str, ent: str, data: dict) -> Optional[dict]:
    """
    Generalised method for creation of an entity
    :param srv: The api service the entity belongs to
    :param ent: The entity to create an instance of
    :param data: The data to be used to create the entity instance
    :return: A dict containing the newly created instance's data, or None if
             nothing was created
    """
    logger = utils.get_logger_for_name('ro.service_entity_create')
    logger.info(
        f'Attempting to create an instance of {srv}.{ent} with the '
        f'following data: {data}',
    )
    entity_create = None
    service_to_call = getattr(api, srv)
    # service_to_call = api.IAAS  (e.g service = 'iaas')
    entity_to_call = getattr(service_to_call, ent)
    # entity_to_call = api.IAAS.image (e.g entity = 'image')
    response = entity_to_call.create(token=TOKEN_WRAPPER.token, data=data)
    if response.status_code == 201:
        entity_create = response.json()['content']
        logger.info(
            f'Successfully created an instance of {srv}.{ent} with '
            f'the following data: {data}',
        )
    else:
        logger.error(
            f'HTTP Error {response.status_code} occurred while trying to '
            f'create an instance of {srv}.{ent} with the following '
            f'data: {data}.\nResponse from API: {response.content.decode()}',
        )
    return entity_create


def service_entity_list(srv: str, ent: str, params: dict, **kwargs) -> list:
    """
    Retrieves a list of instances of a given entity in a service, which can
    be filtered
    :param srv: The api service the entity belongs to
    :param ent: The entity type to list instances of
    :param params: Search parameters to be passed to the list call
    :param kwargs: Any extra kwargs to pass to the call
    :return: A list of instances of service.entity
    """
    logger = utils.get_logger_for_name('ro.service_entity_list')
    logger.info(
        f'Attempting to retrieve a list of {srv}.{ent} records '
        f'with the following params : {params}',
    )
    service_to_call = getattr(api, srv)
    # service_to_call = api.IAAS  (e.g srv = 'iaas')
    entity_to_call = getattr(service_to_call, ent)
    # entity_to_call = api.IAAS.image (e.g ent = 'image')
    response = entity_to_call.list(
        token=TOKEN_WRAPPER.token,
        params=params,
        **kwargs,
    )
    if response.status_code != 200:
        logger.error(
            f'HTTP Error {response.status_code} occurred while trying to '
            f'list instances of {srv}.{ent} with the following params'
            f': {params}.\nResponse from API: {response.content.decode()}',
        )
        return []
    records_found = response.json()['_metadata']['totalRecords']
    plural = records_found != 1
    logger.info(
        f'Found {records_found} instance{"s" if plural else ""} of '
        f'{srv}.{ent} with the following params : {params}',
    )
    return response.json()['content']


def service_entity_update(srv: str, ent: str, pk: int, data: dict) -> bool:
    """
    Update an instance of service.entity with the specified pk using the
    supplied data
    :param srv: The api service the entity belongs to
    :param ent: The entity type to update
    :param pk: The id of the entity to update
    :param data: The data to use for updating the instance
    :return: Flag stating whether or not the update was successful
    """
    logger = utils.get_logger_for_name('ro.service_entity_update')
    logger.info(
        f'Attempting to update the {srv}.{ent} instance #{pk} '
        f'with the following data : {data}',
    )
    service_to_call = getattr(api, srv)
    # service_to_call = api.IAAS  (e.g srv = 'iaas')
    entity_to_call = getattr(service_to_call, ent)
    # entity_to_call = api.IAAS.image (e.g ent = 'image')
    response = entity_to_call.partial_update(
        pk=pk,
        token=TOKEN_WRAPPER.token,
        data=data,
    )
    # Checking just updation no return of data so 204 No content
    if response.status_code == 204:
        logger.info(
            f'Successfully updated {srv}.{ent} instance #{pk} '
            f'with the following data : {data}',
        )
        return True
    else:
        logger.error(
            f'HTTP Error {response.status_code} returned when attempting to '
            f'update {srv}.{ent} instance #{pk}\nResponse from API: '
            f'{response.content.decode()}',
        )
        return False


def service_entity_read(srv: str, ent: str, pk: int) -> Optional[dict]:
    """
    Read an instance of service.entity with the specified pk and return it,
    using params to filter if necessary
    :param srv: The api service the entity belongs to
    :param ent: The entity type to read
    :param pk: The id of the entity to read
    :return: A dict containing the data of the read instance, or None if an
             error occurs
    """
    logger = utils.get_logger_for_name('ro.service_entity_read')
    logger.info(f'Attempting to read the {srv}.{ent} instance #{pk}')
    service_to_call = getattr(api, srv)
    # service_to_call = api.IAAS  (e.g srv = 'iaas')
    entity_to_call = getattr(service_to_call, ent)
    # entity_to_call = api.IAAS.image (e.g ent = 'image')
    response = entity_to_call.read(pk=pk, token=TOKEN_WRAPPER.token)
    if response.status_code == 200:
        logger.info(f'Successfully read {srv}.{ent} instance #{pk}')
        return response.json()['content']
    else:
        logger.error(
            f'HTTP Error {response.status_code} returned when attempting to '
            f'read {srv}.{ent} instance #{pk}\nResponse from API: '
            f'{response.content.decode()}',
        )
        return None


def get_idrac_details(location: str) -> Optional[Tuple[str, str]]:
    """
    Generate the ip address and password of the iDRAC interface of an asset,
    given its location
    :param location: string stating the location of the asset in CIX style
                     (eg "CIX1AGU12")
    :return: A tuple containing the ip_address and password for the interface,
             or None if an error occurs with the API
    """
    logger = utils.get_logger_for_name('ro.get_idrac_details')
    logger.info(f'Attempting to generate iDRAC info for location {location}')
    location = location.replace(' ', '')  # Remove white spaces
    # Find the ipaddress
    if location[:5] == 'CIX1A':
        ip = '10.253'
    elif location[:5] == 'CIX1B':
        ip = '10.252'
    elif location[:5] == 'CIX1C':
        ip = '10.251'
    else:
        # Undefined location, return error
        logger.error(
            f'Location {location} did not contain one of the valid room '
            f'identifiers (CIX1A, CIX1B, CIX1C)',
        )
        return

    if location[5] in ['A', 'G', 'M']:
        base = 0
    elif location[5] in ['B', 'H', 'N']:
        base = 20
    elif location[5] in ['C', 'I', 'O']:
        base = 40
    elif location[5] in ['D', 'J', 'P']:
        base = 60
    elif location[5] in ['E', 'K', 'Q']:
        base = 80
    elif location[5] in ['F', 'L', 'R']:
        base = 80
    else:
        logger.error(
            f'Location {location} did not contain one of the valid rack '
            f'identifiers (A-R)',
        )
        return
    rack = location.split(location[:5])[-1]
    ip += '.' + str(base + int(rack[1: 3]))
    ip += '.' + rack[rack.index('U') + 1:]

    # Get the password
    response = api.IAAS.location_hasher.create(
        token=TOKEN_WRAPPER.token,
        data={'location': location},
    )
    if response.status_code in [200, 201]:
        password = response.json()['content']['hexadecimal']
        logger.info(
            f'Successfully generated iDRAC details for location {location}',
        )
    else:
        logger.error(
            f'Error generating host password for location {location}\n'
            f'Response from location_hasher API: {response.content.decode()}',
        )
        return
    return ip, password


def ip_validator(ranges: str = '', ips: str = '') -> Optional[dict]:
    """
    This method acts as a wrapper around the api.IAAS.ip_validator endpoint.
    This endpoint validates one or more address ranges and ip addresses,
    which are passed in the form of a string where multiple addresses are
    comma separated
    :param ranges: optional string containing one or more addressRanges
    :param ips: optional string containing one or more ipAddresses
    :return: The response from the ip_validator API or None if an error occurs
    """
    logger = utils.get_logger_for_name('ro.ip_validations')
    logger.info(
        'Attempting to validate the following information: addressRanges:'
        f' {ranges}, ipAddresses: {ips}',
    )
    params = dict()
    if ranges:
        params['addressRanges'] = ranges
    if ips:
        params['ipAddresses'] = ips
    # Send a request to the API to validate the ipAddresses and addressRanges
    response = api.IAAS.ip_validator.list(
        token=TOKEN_WRAPPER.token,
        params=params,
    )
    if response.status_code == 200:
        logger.info(
            'Obtained a successful response from the API for the following '
            f'information: addressRanges: {ranges}, ipAddresses: '
            f'{ips}',
        )
        return response.json()['content']
    else:
        logger.error(
            f'HTTP ERROR {response.status_code} received when attempting to'
            f' validate the following information: addressRanges: '
            f'{ranges}, ipAddresses: {ips}',
        )


def password_generator(size: int = 8, chars: Optional[str] = None) -> str:
    """
    Returns a string of random characters, useful in generating temporary
    passwords for automated password resets.

    :param size: default=8; override to provide smaller/larger passwords
    :param chars: default=A-Za-z0-9; override to provide more/less diversity
    :return: A password of length 'size' generated randomly from 'chars'
    """
    if chars is None:
        chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(size))
