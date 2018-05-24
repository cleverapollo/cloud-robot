def vmBuilder(vm, password):
    # get the reference value of IMAGEs from CMDG-IMAGE table
    if str(vm['idImage']) == '3':
        from .windowsSrv2016vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['idImage']) == '10':
        from .cenOS6vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['idImage']) == '11':
        from .cenOS7vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['idImage']) == '7':
        from .ubuntu1404x64vmBuilder import vmBuild
        return vmBuild(vm, password)
    elif str(vm['idImage']) == '6':
        from .ubuntu1604x64vmBuilder import vmBuild
        return vmBuild(vm, password)
    else:
        return False
