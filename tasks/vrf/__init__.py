"""
files containing tasks related to vrfs
"""
from .build import build_vrf
from .debug import debug_logs
from .quiesce import quiesce_vrf
from .restart import restart_vrf
from .scrub import scrub_vrf
from .update import update_vrf

__all__ = [
    'build_vrf',
    'debug_logs',
    'quiesce_vrf',
    'restart_vrf',
    'scrub_vrf',
    'update_vrf',
]
