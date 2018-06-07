from .heartbeat import heartbeat
from .vrf import (
    build_failure as vrf_failure,
    build_success as vrf_success,
)
from .vm import (
    build_failure as vm_failure,
    build_success as vm_success,
)

__all__ = [
    # metric methods
    'heartbeat',
    'vrf_failure',
    'vrf_success',
    'vm_failure',
    'vm_success',
]
