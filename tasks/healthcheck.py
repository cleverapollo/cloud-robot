"""
File containing methods for monitoring if Robot is running as intended
"""

# stdlib
import logging
from datetime import datetime, timedelta
from dateutil.parser import isoparse
from typing import Any, Dict

# lib
from cloudcix.api import IAAS, Support
# local
import state
import utils
from cloudcix_token import Token

INFRASTRUCTURE_DELAY = 5
VM_BUILD_DELAY = 15
WARRANTOR_TICKET_TYPE = 40000

__all__ = [
    'find_stuck_infra',
]


LOGGER = logging.getLogger('robot.tasks.healthcheck')


def find_stuck_infra(interval_mins: int):

    logging.getLogger('robot.tasks.healthcheck').info('Running healthcheck')
    vms = _find_stuck_vms(interval_mins)
    vrfs = _find_stuck_virtual_routers(interval_mins)

    if len(vms) == 0 and len(vrfs) == 0:
        LOGGER.info('Healthcheck passed')
        return
    LOGGER.warning('Infrastructure was found stuck in an unstable state')

    # Create a ticket if required
    for item in (*vms, *vrfs):
        if 'name' in item:
            label = f'VM #{item["id"]}'
        else:
            label = f'Virtual Router #{item["id"]}'

        warrantor_reference = _create_warrantor_reference(label, item['state'])
        client = item['project']['reseller_id']
        warrantor = item['project']['region_id']
        ticket = _find_warrantor_ticket(warrantor_reference, warrantor, client)
        if ticket is not None:
            LOGGER.info(f'{label} already has a ticket. Skipping.')
            continue

        LOGGER.info(f'Creating ticket for {label} in state {item["state"]}')
        _create_warrantor_ticket({
            'client': client,
            'label': label,
            'warrantor_reference': warrantor_reference,
            'state_name': state.STATE_NAMES[item['state']],
            'updated': item['updated'],
            'warrantor': warrantor,
        })


def _find_stuck_vms(interval_mins: int):
    """
    Get all VMs that have been in unstable states for too long
    """

    # VM build takes longer than other tasks. Search for this state separately
    start_time = (datetime.utcnow() - timedelta(minutes=VM_BUILD_DELAY + interval_mins)).isoformat()
    end_time = (datetime.utcnow() - timedelta(minutes=VM_BUILD_DELAY)).isoformat()

    params = {
        'search[updated__gt]': start_time,
        'search[updated__lt]': end_time,
        'search[state]': state.BUILDING,
    }
    vms = utils.api_list(IAAS.vm, params)

    start_time = (datetime.utcnow() - timedelta(minutes=INFRASTRUCTURE_DELAY + interval_mins)).isoformat()
    end_time = (datetime.utcnow() - timedelta(minutes=INFRASTRUCTURE_DELAY)).isoformat()
    params = {
        'search[updated__gt]': start_time,
        'search[updated__lt]': end_time,
        'exclude[state__in]': [*state.STABLE_STATES, state.BUILDING],
        'order': 'state',
    }
    vms.extend(utils.api_list(IAAS.vm, params))
    return vms


def _find_stuck_virtual_routers(interval_mins: int):
    start_time = (datetime.utcnow() - timedelta(minutes=INFRASTRUCTURE_DELAY + interval_mins)).isoformat()
    end_time = (datetime.utcnow() - timedelta(minutes=INFRASTRUCTURE_DELAY)).isoformat()

    params = {
        'search[updated__gt]': start_time,
        'search[updated__lt]': end_time,
        'exclude[state__in]': state.STABLE_STATES,
        'order': 'state',
    }
    return utils.api_list(IAAS.virtual_router, params)


def _create_warrantor_reference(identifier: str, state_id: int):
    identifier = identifier.lower().replace(' ', '_')
    return f'{identifier}-{state.STATE_NAMES[state_id]}'


def _find_warrantor_ticket(reference: str, warrantor: int, client: int):
    """
    Search for any issued tickets that have the given warrantor reference
    """
    params = {
        'search[warrantor_reference]': reference,
        'search[warrantor_status__name__icontains]': 'issued',
        'search[warrantor_address_id]': warrantor,
        'search[client_address_id]': client,
    }
    tickets = utils.api_list(Support.ticket, params, transaction_type_id=WARRANTOR_TICKET_TYPE)
    if len(tickets) == 0:
        return None
    return tickets[0]


def _create_warrantor_ticket(item: Dict[str, Any]):
    updated = isoparse(item['updated']).strftime('%H:%M UTC %B %d'),
    data = {
        'warrantor_address_id': item['warrantor'],
        'warrantor_reference': item['warrantor_reference'],
        'client_address_id': item['client'],
        'date_of_issue': datetime.utcnow().isoformat(),
        'processing_instruction': (
            f'{item["label"]} entered state {item["state_name"]} at {updated} and has not completed.'
        ),
    }
    response = Support.ticket.create(
        token=Token.get_instance().token,
        transaction_type_id=WARRANTOR_TICKET_TYPE,
        data=data,
    )
    if response.status_code == 201:
        LOGGER.warning(f'Successfully created ticket for {item["label"]}')
    else:
        LOGGER.warning(f'Failed to create ticket for {item["label"]}')
