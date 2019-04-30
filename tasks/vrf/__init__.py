"""
files containing tasks related to vrfs
"""
from .build import build_vrf
from .quiesce import quiesce_vrf
from .restart import restart_vrf
from .scrub import scrub_vrf
from .update import update_vrf

__all__ = [
    'build_vrf',
    'quiesce_vrf',
    'restart_vrf',
    'scrub_vrf',
    'update_vrf',
]
