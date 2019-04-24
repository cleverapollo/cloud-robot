# python
import netaddr
import time
from crypt import crypt, mksalt, METHOD_SHA512
from datetime import datetime, timedelta

# locals
import email_notifier
import metrics
import ro
import utils
from builders import Linux as LinuxBuilder, Windows as WindowsBuilder
from scrubbers import Linux as LinuxScrubber, Windows as WindowsScrubber
from quiescers import Linux as LinuxQuiescer, Windows as WindowsQuiescer
from updaters import Linux as LinuxUpdater, Windows as WindowsUpdater
from restarters import Linux as LinuxRestarter, Windows as WindowsRestarter

EMAIL_BUILD_SUCCESS_SUBJECT = 'Your VM "{name}" has been built successfully!'
EMAIL_BUILD_FAILURE_SUBJECT = 'Your VM "{name}" has failed to build!'
EMAIL_SCRUB_SUCCESS_SUBJECT = 'Your VM "{name}" has been deleted successfully!'
EMAIL_QUIESCE_SUCCESS_SUBJECT = 'Your VM "{name}" has been shutdown successfully!'
EMAIL_UPDATE_SUCCESS_SUBJECT = 'Your VM "{name}" has been updated successfully!'
EMAIL_UPDATE_FAILURE_SUBJECT = 'Your VM "{name}" has been failed to update!'
EMAIL_RESTART_SUCCESS_SUBJECT = 'Your VM "{name}" has been restarted successfully!'
EMAIL_RESTART_FAILURE_SUBJECT = 'Your VM "{name}" has been failed to restart!'
EMAIL_DELETE_REQUEST_SUBJECT = 'The request to delete the VM "{name}" has been received successfully!'


class Vm:
    """
    A class that handles 'dispatching' a VM to various services such as builders, scrubbers, etc.
    """

    # Network password used to login to the host servers
    password: str

    def __init__(self, password: str):
        self.password = password

    @staticmethod
    def ntw_address(address_range):
        """
        it will set the address range to first ip ie if address range is 10.1.0.0/24
        then the out put will be 10.1.0.1/24
        :param address_range: ip address network (ipv4/ipv6)
        :return: string of network address
        """
        ip_addr = str(address_range).split('/')
        ntw_addr = ip_addr[0]
        # find the ip type
        response = ro.api.IAAS.ip_validator.list(
            token=ro.TOKEN_WRAPPER.token,
            params={'ipAddresses': ntw_addr},
        )
        result = response.json()['ipAddresses'][ntw_addr]['result']
        if result['ipv4']:
            li = ip_addr[0].split('.')
            # set the octet to 1 if it is 0
            if li[-1] == '0':
                li[-1] = '1'
            # rearrange subnet
            ntw_addr = '.'.join(f'{i}' for i in li)
        elif result['ipv6']:
            li = ip_addr[0].split(':')
            # set the octet to 1 if it is 0
            if li[-1] == '0':
                li[-1] = '1'
            # rearrange subnet
            ntw_addr = ':'.join(f'{i}' for i in li)
        return str(netaddr.IPNetwork(f'{ntw_addr}/{ip_addr[1]}'))

    def build(self, vm: dict):
        """
        Takes VM data from the CloudCIX API, adds any additional data needed for building it and requests to build it
        in the assigned host server.
        :param vm: The VM data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vm.build')
        vm_id = vm['idVM']
        logger.info(f'Commencing build dispatch of VM #{vm_id}')
        # Change the state of the VM to Building (2)
        ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 2})

        # Get the image data and add extra data to the supplied dict
        image = ro.service_entity_read('IAAS', 'image', vm['idImage'])
        vm['vm_identifier'] = f'{vm["idProject"]}_{vm["idVM"]}'
        vm['image'] = image['filename']
        vm['ram'] *= 1024  # ram must be multiple of 1024 as the builders takes in MBytes
        vm['idHypervisor'] = image['idHypervisor']
        vm['admin_password'] = ro.password_generator(size=8)
        # Considering only primary as hdd/ssd drives and rest as drives

        # Get the storage type and storage
        storages = ro.service_entity_list('IAAS', 'storage', {}, vm_id=vm['idVM'])
        vm['drives'] = list()
        for storage in storages:
            st_type = ro.service_entity_read(
                'IAAS',
                'storage_type',
                storage['idStorageType'],
            )
            if storage['primary'] is True:
                if st_type['storage_type'] == 'HDD':
                    vm['hdd'] = f'{storage["idStorage"]}:{storage["gb"]}'
                    vm['ssd'] = 0
                elif st_type['storage_type'] == 'SSD':
                    vm['hdd'] = 0
                    vm['ssd'] = f'{storage["idStorage"]}:{storage["gb"]}'
            else:
                vm['drives'].append(
                    {'st_id': storage['idStorage'],
                     'type': st_type['storage_type'],
                     'size': storage['gb'],
                     },
                )
        # Get ip address and subnet details
        for ip in ro.service_entity_list('IAAS', 'ipaddress', {'vm': vm['idVM']}):
            if netaddr.IPAddress(ip['address']).is_private():
                vm['ip'] = ip['address']
                # Get the subnet of this IP
                subnet = ro.service_entity_read('IAAS', 'subnet', ip['idSubnet'])
                vm['gateway'], vm['netmask'] = self.ntw_address(subnet['addressRange']).split('/')
                vm['netmask_ip'] = netaddr.IPNetwork(subnet['addressRange']).netmask
                vm['vlan'] = subnet['vLAN']
                # Get user email to notify the user
                vm['email'] = ro.service_entity_read('Membership', 'user', subnet['modifiedBy'])['username']
        vm['lang'] = 'en_IE'
        vm['keyboard'] = 'ie'
        vm['tz'] = 'Ireland/Dublin'
        # Get the server details for sshing into the host
        for mac in ro.service_entity_list('IAAS', 'macaddress', {}, server_id=vm['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                try:
                    vm['host_ip'] = str(netaddr.IPAddress(mac['ip']))
                    vm['host_name'] = mac['dnsName']
                    break
                except netaddr.AddrFormatError:
                    logger.error(
                        f'Error occurred when trying to read host ip address from mac record '
                        f'#{mac["idMacAddress"]}. Putting VM #{vm_id} into Unresourced state.',
                        exc_info=True,
                    )
                    ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})
                    metrics.vm_build_failure()
                    return

        # TODO - Add data/ip validations to vm dispatcher

        # CHECK IF VRF IS BUILT OR NOT
        # Get the vrf via idProject which is common for both VM and VRF
        vrf_request_data = {'project': vm['idProject']}
        vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)
        while vm_vrf[0]['state'] != 4:
            logger.warn(
                f'VM #{vm_id} waiting on VRF #{vm_vrf[0]["idVRF"]} to be state 4. '
                f'Currently: {vm_vrf[0]["state"]}',
            )
            if vm_vrf[0]['state'] == 3:
                logger.error('Cannot build VM #{vm_id} as its VRF is Unresourced.')
                ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})
                metrics.vm_build_failure()
                return
            time.sleep(5)
            vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)

        # Attempt to build the VM
        success: bool
        if vm['idHypervisor'] == 1:  # HyperV -> Windows
            # sending multiple drives as string format ie 'gb1,gb2,gb3,...' only sizes
            md = ','.join(f'{drive["st_id"]}:{drive["size"]}' for drive in vm['drives'])
            if md:
                vm['mul_drives'] = md
            else:
                vm['mul_drives'] = 0
            vm['dns'] = vm['dns'].split(',')
            vm['tz'] = 'GMT Standard Time'
            success = WindowsBuilder.build(vm, self.password)
        elif vm['idHypervisor'] == 2:  # KVM -> Linux
            # Encrypt the password
            vm['crypted_admin_password'] = str(crypt(vm['admin_password'], mksalt(METHOD_SHA512)))
            # Create a crypted root password for CentOS
            vm['crypted_root_password'] = str(crypt(ro.password_generator(size=128), mksalt(METHOD_SHA512)))
            success = LinuxBuilder.build(vm, self.password)
        else:
            logger.error(f'Unsupported idHypervisor ({vm["idHypervisor"]}). VM #{vm_id} cannot be built')
            success = False

        if success:
            logger.info(f'VM #{vm_id} successfully built in Server #{vm["idServer"]}')
            # Change the state of the VM to Built (4) and log a success in Influx
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 4})
            metrics.vm_build_success()
            # Email the user
            email_notifier.vm_email_notifier(
                EMAIL_BUILD_SUCCESS_SUBJECT.format(name=vm['name']),
                vm,
                'emails/build_success.j2',
            )
        else:
            logger.info(f'VM #{vm_id} failed to build so it is being moved to Unresourced (3). Check log for details.')
            # Change the state of the VM to Unresourced (3) and log a failure in Influx
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})
            metrics.vm_build_failure()
            # Email the User
            email_notifier.vm_email_notifier(
                EMAIL_BUILD_FAILURE_SUBJECT.format(name=vm['name']),
                vm,
                'emails/build_error.j2',
            )

    def quiesce(self, vm: dict):
        """
        Takes the VM (to be quiesced )data from CloudCix API and sends the request to concern quiescer.
        :param vm: The VM data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vm.quiesce')
        vm_id = vm['idVM']
        logger.info(f'Commencing quiesce dispatch of VM #{vm_id}')
        vm['vm_identifier'] = f'{vm["idProject"]}_{vm["idVM"]}'
        # Get the type of VM ie idHypervisor
        vm['idHypervisor'] = ro.service_entity_read('IAAS', 'image', vm['idImage'])['idHypervisor']
        # Get the server details for sshing into the host
        for mac in ro.service_entity_list('IAAS', 'macaddress', {}, server_id=vm['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                try:
                    vm['host_ip'] = str(netaddr.IPAddress(mac['ip']))
                    vm['host_name'] = mac['dnsName']
                    break
                except netaddr.AddrFormatError:
                    logger.error(
                        f'Error occurred when trying to read host ip address from mac record '
                        f'#{mac["idMacAddress"]}.',
                        exc_info=True,
                    )
                    metrics.vm_quiesce_failure()
                    return
        # Get vlan and email id of user via ip address and subnet details
        for ip in ro.service_entity_list('IAAS', 'ipaddress', {'vm': vm['idVM']}):
            if netaddr.IPAddress(ip['address']).is_private():
                # Get the subnet of this IP
                subnet = ro.service_entity_read('IAAS', 'subnet', ip['idSubnet'])
                vm['vlan'] = subnet['vLAN']
                # Get user email to notify the user
                vm['email'] = ro.service_entity_read('Membership', 'user', subnet['modifiedBy'])['username']

        # Attempt to shutdown/quiesce the VM
        success: bool
        if vm['idHypervisor'] == 1:  # HyperV -> Windows
            success = WindowsQuiescer.quiesce(vm, self.password)
        elif vm['idHypervisor'] == 2:  # KVM -> Linux
            success = LinuxQuiescer.quiesce(vm, self.password)
        else:
            logger.error(
                f'Unsupported idHypervisor ({vm["idHypervisor"]}). VM #{vm_id} cannot be shutdown',
            )
            success = False

        if success:
            logger.info(f'VM #{vm_id} successfully quiesced from Server #{vm["idServer"]}')
            # Change the state of the VM to:
            #  1. Quiesced (6) if the existing state is Quiescing (5)
            #  2. Deleted (9) if the existing state is Scheduled for Deletion (8)
            # And log a success in Influx
            if vm['state'] == 5:
                ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 6})
                # Email the user
                email_notifier.vm_email_notifier(
                    EMAIL_QUIESCE_SUCCESS_SUBJECT.format(name=vm['name']),
                    vm,
                    'emails/quiesce_success.j2',
                )
            if vm['state'] == 8:
                ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 9})
                # Add a deletion date in the format 'Monday September 30 2013'
                vm['deletion_date'] = (datetime.now().date() + timedelta(days=30)).strftime('%A %B %d, %Y')
                # Email the user
                email_notifier.vm_email_notifier(
                    EMAIL_DELETE_REQUEST_SUBJECT.format(name=vm['name']),
                    vm,
                    'emails/scheduled_delete_success.j2',
                )
            metrics.vm_quiesce_success()
        else:
            logger.info(f'VM #{vm_id} failed to shutdown . Check log for details.')
            metrics.vm_quiesce_failure()
            # We don't need to email the user if it failed to shutdown

    def scrub(self, vm: dict):
        """
        Takes the VM (to be deleted )data from CloudCix API and sends the request to concern scrubber.
        :param vm: The VM data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vm.scrub')
        vm_id = vm['idVM']
        logger.info(f'Commencing scrub dispatch of VM #{vm_id}')
        vm['vm_identifier'] = f'{vm["idProject"]}_{vm["idVM"]}'
        # Get the type of VM ie idHypervisor
        vm['idHypervisor'] = ro.service_entity_read('IAAS', 'image', vm['idImage'])['idHypervisor']
        # Get the server details for sshing into the host
        for mac in ro.service_entity_list('IAAS', 'macaddress', {}, server_id=vm['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                try:
                    vm['host_ip'] = str(netaddr.IPAddress(mac['ip']))
                    vm['host_name'] = mac['dnsName']
                    break
                except netaddr.AddrFormatError:
                    logger.error(
                        f'Error occurred when trying to read host ip address from mac record '
                        f'#{mac["idMacAddress"]}.',
                        exc_info=True,
                    )
                    metrics.vm_scrub_failure()
                    return

        # Get the storage type and storage
        storages = ro.service_entity_list('IAAS', 'storage', {}, vm_id=vm['idVM'])
        vm['drives'] = list()
        for storage in storages:
            st_type = ro.service_entity_read(
                'IAAS',
                'storage_type',
                storage['idStorageType'],
            )
            if storage['primary'] is True:
                if st_type['storage_type'] == 'HDD':
                    vm['hdd'] = f'{storage["idStorage"]}:{storage["gb"]}'
                    vm['ssd'] = 0
                elif st_type['storage_type'] == 'SSD':
                    vm['hdd'] = 0
                    vm['ssd'] = f'{storage["idStorage"]}:{storage["gb"]}'
            else:
                vm['drives'].append(
                    {'st_id': storage['idStorage'],
                     'type': st_type['storage_type'],
                     'size': storage['gb'],
                     },
                )

        # Get vlan and email id of user via ip address and subnet details
        for ip in ro.service_entity_list('IAAS', 'ipaddress', {'vm': vm['idVM']}):
            if netaddr.IPAddress(ip['address']).is_private():
                # Get the subnet of this IP
                subnet = ro.service_entity_read('IAAS', 'subnet', ip['idSubnet'])
                vm['vlan'] = subnet['vLAN']
                # Get user email to notify the user
                vm['email'] = ro.service_entity_read('Membership', 'user', subnet['modifiedBy'])['username']

        # Attempt to scrub the VM
        success: bool
        if vm['idHypervisor'] == 1:  # HyperV -> Windows
            success = WindowsScrubber.scrub(vm, self.password)
        elif vm['idHypervisor'] == 2:  # KVM -> Linux
            # ---------------------------------------------------------------------------------------------
            # To delete the bridge interface on host, there must be no VM connected to the bridge
            # So get all the VMs with state not equal to 9 (deleted), and the list of VMs must be only one in
            # number as current VM yet to be deleted. otherwise do not delete the bridge.
            vm['bridge_delete'] = False
            params = {
                'project': vm['idProject'],
                'exclude__state': 9,
            }
            vlan_vms = ro.service_entity_list('IAAS', 'vm', params=params)
            existing_vms_count = 0
            if len(vlan_vms) == 1 and vlan_vms[0]['idVM'] == vm['idVM']:
                vm['bridge_delete'] = True
            else:
                for vlan_vm in vlan_vms:
                    vlan_vm['idHypervisor'] = ro.service_entity_read(
                        'IAAS',
                        'image',
                        vlan_vm['idImage'],
                    )['idHypervisor']
                    if vlan_vm['idVM'] != vm['idVM'] and vlan_vm['idHypervisor'] == 2:
                        for ip in ro.service_entity_list('IAAS', 'ipaddress', {'vm': vlan_vm['idVM']}):
                            if netaddr.IPAddress(ip['address']).is_private():
                                # Get the subnet of this IP
                                subnet = ro.service_entity_read('IAAS', 'subnet', ip['idSubnet'])
                                # check if the VM is in the same subnet of current scrubbing VM
                                if subnet['vLAN'] == vm['vlan']:
                                    existing_vms_count += 1
                if not existing_vms_count > 0:
                    vm['bridge_delete'] = True
            # ---------------------------------------------------------------------------------------------
            success = LinuxScrubber.scrub(vm, self.password)
        else:
            logger.error(f'Unsupported idHypervisor ({vm["idHypervisor"]}). VM #{vm_id} cannot be scrubbed')
            success = False

        if success:
            logger.info(f'VM #{vm_id} successfully scrubbed from Server #{vm["idServer"]}')
            metrics.vm_scrub_success()

            # Delete the VM from the DB
            if ro.service_entity_delete('IAAS', 'vm', vm_id):
                logger.info(f'VM #{vm_id} successfully deleted from the API')
            else:
                logger.error(f'VM #{vm_id} API deletion failed. Check log for details')

            # Check that list requests for VRF and VM both are empty, and if so, delete the project
            project_id = vm['idProject']
            active_vrfs = len(ro.service_entity_list('IAAS', 'vrf', {'project': project_id}))
            active_vms = len(ro.service_entity_list('IAAS', 'vm', {'project': project_id}))
            if active_vms == 0 and active_vrfs == 0:
                logger.info('Project is empty. Sending delete request.')
                if ro.service_entity_delete('IAAS', 'project', project_id):
                    logger.info(f'Project #{project_id} successfully deleted from the API')
                else:
                    logger.error(f'Project #{project_id} API deletion failed. Check log for details')
            else:
                logger.info(f'Not deleting project. {active_vrfs} VRFs and {active_vms} VMs remain active.')

        else:
            logger.info(f'VM #{vm_id} failed to scrub. Check log for details.')
            metrics.vm_scrub_failure()

    def update(self, vm: dict):
        """
        Takes VM data from the CloudCIX API, adds any additional data needed for updating it and requests to update it
        in the assigned host server.
        :param vm: The VM data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vm.update')
        vm_id = vm['idVM']
        logger.info(f'Commencing update dispatch of VM #{vm_id}')
        # Change the state of the VM to Updating (11)
        ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 11})

        # Get the image data and add extra data to the supplied dict
        image = ro.service_entity_read('IAAS', 'image', vm['idImage'])
        vm['vm_identifier'] = f'{vm["idProject"]}_{vm["idVM"]}'
        vm['image'] = image['filename']
        vm['ram'] *= 1024  # ram must be multiple of 1024 as the builders takes in MBytes
        vm['idHypervisor'] = image['idHypervisor']

        # Get the storage type and storage
        storages = vm['changes_this_month'][0]['details']['storages']
        vm['drives'] = list()
        for storage in storages:
            st = ro.service_entity_read(
                'IAAS',
                'storage',
                int(storage),
            )
            st_type = ro.service_entity_read(
                'IAAS',
                'storage_type',
                st['idStorageType'],
            )
            if st['primary'] is True:
                if st_type['storage_type'] == 'HDD':
                    vm['hdd'] = f'{st["idStorage"]}:{storage["new_value"]}:{storage["old_value"]}'
                    vm['ssd'] = 0
                elif st_type['storage_type'] == 'SSD':
                    vm['hdd'] = 0
                    vm['ssd'] = f'{st["idStorage"]}:{storage["new_value"]}:{storage["old_value"]}'
            else:
                vm['drives'].append(
                    {'st_id': st['idStorage'],
                     'type': st_type['storage_type'],
                     'new_size': storage['new_value'],
                     'old_size': storage['old_value'],
                     },
                )

        # Get ip address and subnet details
        for ip in ro.service_entity_list('IAAS', 'ipaddress', {'vm': vm['idVM']}):
            if netaddr.IPAddress(ip['address']).is_private():
                vm['ip'] = ip['address']
                # Get the subnet of this IP
                subnet = ro.service_entity_read('IAAS', 'subnet', ip['idSubnet'])
                vm['gateway'], vm['netmask'] = self.ntw_address(subnet['addressRange']).split('/')
                vm['netmask_ip'] = netaddr.IPNetwork(subnet['addressRange']).netmask
                vm['vlan'] = subnet['vLAN']
                # Get user email to notify the user
                vm['email'] = ro.service_entity_read('Membership', 'user', subnet['modifiedBy'])['username']
        # Get the server details for sshing into the host
        for mac in ro.service_entity_list('IAAS', 'macaddress', {}, server_id=vm['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                try:
                    vm['host_ip'] = str(netaddr.IPAddress(mac['ip']))
                    vm['host_name'] = mac['dnsName']
                    break
                except netaddr.AddrFormatError:
                    logger.error(
                        f'Error occurred when trying to read host ip address from mac record '
                        f'#{mac["idMacAddress"]}. Putting VM #{vm_id} into Unresourced state.',
                        exc_info=True,
                    )
                    ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})
                    metrics.vm_build_failure()
                    return

        # TODO - Add data/ip validations to vm dispatcher

        # CHECK IF VRF IS UPDATED(in state BUILT 4) OR NOT
        # Get the vrf via idProject which is common for both VM and VRF
        vrf_request_data = {'project': vm['idProject']}
        vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)
        while vm_vrf[0]['state'] != 4:
            logger.warn(
                f'VM #{vm_id} waiting on VRF #{vm_vrf[0]["idVRF"]} to be state 4. '
                f'Currently: {vm_vrf[0]["state"]}',
            )
            if vm_vrf[0]['state'] == 3:
                logger.error('Cannot update VM #{vm_id} as its VRF is Unresourced.')
            time.sleep(5)
            vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)

        # Attempt to update the VM
        success: bool
        # Change the state of the VM to Building (2).
        ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 2})
        if vm['idHypervisor'] == 1:  # HyperV -> Windows
            vm['dns'] = vm['dns'].replace(',', '", "')
            success = WindowsUpdater.update(vm, self.password)
        elif vm['idHypervisor'] == 2:  # KVM -> Linux
            success = LinuxUpdater.update(vm, self.password)
        else:
            logger.error(f'Unsupported idHypervisor ({vm["idHypervisor"]}). VM #{vm_id} cannot be updated')
            success = False
        if success:
            logger.info(f'VM #{vm_id} successfully updated in Server #{vm["idServer"]}')
            # Change the state of the VM to Built (4) and log a success in Influx
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 4})
            metrics.vm_update_success()
            # Email the user
            email_notifier.vm_email_notifier(
                EMAIL_UPDATE_SUCCESS_SUBJECT.format(name=vm['name']),
                vm,
                'emails/update_success.j2',
            )
        else:
            logger.info(f'VM #{vm_id} failed to update so it is being moved to Unresourced (3). Check log for details.')
            # Change the state of the VM to Unresourced (3) and log a failure in Influx
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})
            metrics.vm_update_failure()
            # Email the User
            email_notifier.vm_email_notifier(
                EMAIL_UPDATE_FAILURE_SUBJECT.format(name=vm['name']),
                vm,
                'emails/update_error.j2',
            )

    def restart(self, vm: dict):
        """
        Takes the VM (to be restarted )data from CloudCix API and sends the request to concern restarter.
        :param vm: The VM data from the CloudCIX API
        """
        logger = utils.get_logger_for_name('dispatchers.vm.restart')
        vm_id = vm['idVM']
        logger.info(f'Commencing restart dispatch of VM #{vm_id}')
        vm['vm_identifier'] = f'{vm["idProject"]}_{vm["idVM"]}'
        # Get the type of VM ie idHypervisor
        vm['idHypervisor'] = ro.service_entity_read('IAAS', 'image', vm['idImage'])['idHypervisor']
        # Get the server details for sshing into the host
        for mac in ro.service_entity_list('IAAS', 'macaddress', {}, server_id=vm['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                try:
                    vm['host_ip'] = str(netaddr.IPAddress(mac['ip']))
                    vm['host_name'] = mac['dnsName']
                    break
                except netaddr.AddrFormatError:
                    logger.error(
                        f'Error occurred when trying to read host ip address from mac record '
                        f'#{mac["idMacAddress"]}.',
                        exc_info=True,
                    )
                    metrics.vm_restart_failure()
                    return
        # Get email id of user via ip address and subnet details
        for ip in ro.service_entity_list('IAAS', 'ipaddress', {'vm': vm['idVM']}):
            if netaddr.IPAddress(ip['address']).is_private():
                # Get the subnet of this IP
                subnet = ro.service_entity_read('IAAS', 'subnet', ip['idSubnet'])
                # Get user email to notify the user
                vm['email'] = ro.service_entity_read('Membership', 'user', subnet['modifiedBy'])['username']

        # Attempt to restart the VM
        success: bool
        if vm['idHypervisor'] == 1:  # HyperV -> Windows
            success = WindowsRestarter.restart(vm, self.password)
        elif vm['idHypervisor'] == 2:  # KVM -> Linux
            success = LinuxRestarter.restart(vm, self.password)
        else:
            logger.error(
                f'Unsupported idHypervisor ({vm["idHypervisor"]}). VM #{vm_id} cannot be restarted',
            )
            success = False

        if success:
            logger.info(f'VM #{vm_id} successfully restarted from Server #{vm["idServer"]}')
            # Change the state of the VM to 4
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 4})
            # Email the user
            email_notifier.vm_email_notifier(
                EMAIL_RESTART_SUCCESS_SUBJECT.format(name=vm['name']),
                vm,
                'emails/restart_success.j2',
            )
            metrics.vm_restart_success()
        else:
            logger.info(f'VM #{vm_id} failed to restart . Check log for details.')
            # Change the state of the VM to 3
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})
            email_notifier.vm_email_notifier(
                EMAIL_RESTART_FAILURE_SUBJECT.format(name=vm['name']),
                vm,
                'emails/restart_error.j2',
            )
            metrics.vm_restart_failure()
