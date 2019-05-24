"""
mixin classes that have functions that might be used in multiple places
"""
from .linux import LinuxMixin
from .vm import VmUpdateMixin
from .vrf import VrfMixin
from .windows import WindowsMixin

__all__ = [
    'LinuxMixin',
    'VmUpdateMixin',
    'VrfMixin',
    'WindowsMixin',
]
