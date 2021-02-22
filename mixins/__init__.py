"""
mixin classes that have functions that might be used in multiple places
"""
from .linux import LinuxMixin
from .virtual_router import VirtualRouterMixin
from .vm import VmImageMixin, VmUpdateMixin
from .windows import WindowsMixin

__all__ = [
    'LinuxMixin',
    'VirtualRouterMixin',
    'VmImageMixin',
    'VmUpdateMixin',
    'WindowsMixin',
]
