def vmBuilder(vm, password):
    # get the reference value of IMAGEs from CMDG-IMAGE table
    if str(vm['image']) == '3':
        from .windowsSrv2016vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['image']) == '10':
        from .cenOS6vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['image']) == '11':
        from .cenOS7vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['image']) == '7':
        from .ubuntu1404x64vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['image']) == '6':
        from .ubuntu1604x64vmBuilder import vmBuild
        return vmBuild(vm, password)
    else:
        return False


