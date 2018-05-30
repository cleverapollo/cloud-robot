# constants are defined in reference with Switch.
MIN_VLAN = 1000
MAX_VLAN = 1099


def is_valid_vlan(vlan: int) -> bool:
    """
    checks whether vlan is between MIN_VLAN and MAX_VLAN
    :param vlan: int
    :return: boolean
    """
    return MIN_VLAN <= vlan <= MAX_VLAN