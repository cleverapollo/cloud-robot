"""
files containing tasks related to vrs
"""
from .build import build_vr
from .quiesce import quiesce_vr
from .restart import restart_vr
from .scrub import scrub_vr
from .update import update_vr

__all__ = [
    'build_vr',
    'quiesce_vr',
    'restart_vr',
    'scrub_vr',
    'update_vr',
]
