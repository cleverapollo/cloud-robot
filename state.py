# local
from ro import *


def vrf(state: int):
    """
    Finds the first VRF in the API with the given state

    :param state: The state for which to find a VRF
    :returns: A VRF instance or None
    """
    vrf = None
    vrfs = service_entity_list('iaas', 'vrf', params={'state': state})
    if vrfs:
        vrf = vrfs[0]
    return vrf


def vm(state: int):
    """
    Finds the first VM in the API with the given state

    :param state: The state for which to find a VM
    :returns: A VM instance or None
    """
    VM = None
    VMs = service_entity_list('iaas', 'vm', params={'state': state})
    if VMs:
        VM = VMs[0]
    return VM

