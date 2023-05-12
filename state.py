"""
Constants for the different states in the CloudCIX system
"""

IGNORE = 0
REQUESTED = 1
BUILDING = 2
UNRESOURCED = 3
RUNNING = 4
QUIESCE = 5
QUIESCED = 6
RESTART = 7
SCRUB = 8
SCRUB_QUEUE = 9
RUNNING_UPDATE = 10
RUNNING_UPDATING = 11
QUIESCING = 12
RESTARTING = 13
SCRUB_PREP = 14
QUIESCED_UPDATE = 15
QUIESCED_UPDATING = 16
SCRUBBING = 17
CLOSED = 99

# Define the filters for different states
BUILD_FILTERS = [REQUESTED]
IN_PROGRESS_FILTERS = [BUILDING, QUIESCING, RESTARTING, SCRUB_PREP, RUNNING_UPDATING, QUIESCED_UPDATING]
QUIESCE_FILTERS = [QUIESCE, SCRUB]
RESTART_FILTERS = [RESTART]
SCRUB_FILTERS = [SCRUB]
UPDATE_FILTERS = [RUNNING_UPDATE, QUIESCED_UPDATE]
STABLE_STATES = [RUNNING, QUIESCED, SCRUB_QUEUE, CLOSED]

STATE_NAMES = {
    0: 'ignore',
    1: 'requested',
    2: 'building',
    3: 'unresourced',
    4: 'running',
    5: 'quiesce',
    6: 'quiesced',
    7: 'restart',
    8: 'scrub',
    9: 'scrub_queue',
    10: 'running_update',
    11: 'running_updating',
    12: 'quiescing',
    13: 'restarting',
    14: 'scrub_prep',
    15: 'quiesced_update',
    16: 'quiesced_updating',
    17: 'scrubbing',
    99: 'closed',
}
