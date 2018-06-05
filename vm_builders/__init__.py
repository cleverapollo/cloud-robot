# local
from .windows2016 import vm_build as windows_2016_build
from .centos6_5 import vm_build as centOS_6_build
from .centos7 import vm_build as centOS_7_build
from .ubuntu1404x64 import vm_build as ubuntu_14_build
from .ubuntu1604x64 import vm_build as ubuntu_16_build


def vm_builder(vm: dict, password: str) -> bool:
    # get the reference value of IMAGEs from CMDG-IMAGE table
    builder = {
        '3': windows_2016_build,
        '6': ubuntu_16_build,
        '7': ubuntu_14_build,
        '10': centOS_6_build,
        '11': centOS_7_build,
    }
    return builder.get(
        vm['id_image'], lambda vm, password: False
    )(vm, password)
