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
UPDATE = 10
UPDATING = 11
QUIESCING = 12
RESTARTING = 13
SCRUB_PREP = 14

# Define the filters for different states
BUILD_FILTERS = {'search[state]': REQUESTED}
QUIESCE_FILTERS = {'search[state__in]': [QUIESCE, SCRUB]}
RESTART_FILTERS = {'search[state]': RESTART}
UPDATE_FILTERS = {'search[state]': UPDATE}
IN_PROGRESS_FILTERS = {'search[state__in]': [BUILDING, UPDATING, QUIESCING, RESTARTING, SCRUB_PREP]}
