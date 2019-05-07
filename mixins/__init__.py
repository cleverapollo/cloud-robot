"""
mixin classes that have functions that might be used in multiple places
"""
from .linux import LinuxMixin
from .vrf import VrfMixin
from .windows import WindowsMixin

__all__ = [
    'LinuxMixin',
    'VrfMixin',
    'WindowsMixin',
]
