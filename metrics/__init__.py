from .heartbeat import heartbeat
from .misc import (
    current_commit,
)
from .virtual_router import (
    build_failure as virtual_router_build_failure,
    build_success as virtual_router_build_success,
    quiesce_failure as virtual_router_quiesce_failure,
    quiesce_success as virtual_router_quiesce_success,
    restart_failure as virtual_router_restart_failure,
    restart_success as virtual_router_restart_success,
    scrub_failure as virtual_router_scrub_failure,
    scrub_success as virtual_router_scrub_success,
    update_failure as virtual_router_update_failure,
    update_success as virtual_router_update_success,
)
from .vm import (
    build_failure as vm_build_failure,
    build_success as vm_build_success,
    quiesce_failure as vm_quiesce_failure,
    quiesce_success as vm_quiesce_success,
    restart_failure as vm_restart_failure,
    restart_success as vm_restart_success,
    scrub_failure as vm_scrub_failure,
    scrub_success as vm_scrub_success,
    update_failure as vm_update_failure,
    update_success as vm_update_success,
)

__all__ = [
    # metric methods
    'heartbeat',
    'current_commit',
    'virtual_router_build_failure',
    'virtual_router_build_success',
    'virtual_router_scrub_failure',
    'virtual_router_scrub_success',
    'virtual_router_update_failure',
    'virtual_router_update_success',
    'virtual_router_quiesce_failure',
    'virtual_router_quiesce_success',
    'virtual_router_restart_failure',
    'virtual_router_restart_success',
    'vm_build_failure',
    'vm_build_success',
    'vm_scrub_failure',
    'vm_scrub_success',
    'vm_update_failure',
    'vm_update_success',
    'vm_quiesce_failure',
    'vm_quiesce_success',
    'vm_restart_failure',
    'vm_restart_success',
]
