# python
import netaddr
import time
from crypt import crypt, mksalt, METHOD_SHA512

# locals
from builders import Linux as LinuxBuilder, Windows as WindowsBuilder
import email_notifier
import metrics
import ro
import utils


EMAIL_SUCCESS_SUBJECT = 'One of your requested VMs has been successfully built.'
EMAIL_FAILURE_SUBJECT = 'Failed to build one of your requested VMs, please contact our NOC team for more information.'


class Vm:
    """
    A class that handles 'dispatching' a VM to various services such as builders, scrubbers, etc.
    """

    # Network password used to login to the host servers
    password: str

    def __init__(self, password: str):
        self.password = password

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
        vm['user_password'] = ro.password_generator(chars='a', size=8)
        vm['root_password'] = ro.password_generator(size=128)

        # Get ip address and subnet details
        for ip in ro.service_entity_list('IAAS', 'ipaddress', {'vm': vm['idVM']}):
            if netaddr.IPAddress(ip['address']).is_private():
                vm['ip'] = ip['address']
                # Get the subnet of this IP
                subnet = ro.service_entity_read('IAAS', 'subnet', ip['idSubnet'])
                vm['gateway'], vm['netmask'] = subnet['addressRange'].split('/')
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
                    metrics.vm_failure()

        # TODO - Add data/ip validations to vm dispatcher

        # CHECK IF VRF IS BUILT OR NOT
        # Get the vrf via idProject which is common for both VM and VRF
        vrf_request_data = {'project': vm['idProject']}
        vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)
        while vm_vrf[0]['state'] != 4:
            time.sleep(5)
            vm_vrf = ro.service_entity_list('IAAS', 'vrf', vrf_request_data)

        # Attempt to build the VM
        success: bool
        if vm['idHypervisor'] == 1:  # HyperV -> Windows
            vm['dns'] = vm['dns'].split(',')
            vm['tz'] = 'GMT Standard Time'
            success = WindowsBuilder.build(vm, self.password)
        elif vm['idHypervisor'] == 2:  # KVM -> Linux
            # Encrypt the passwords
            vm['crypted_root_password'] = str(crypt(vm['root_password'], mksalt(METHOD_SHA512)))
            vm['crypted_user_password'] = str(crypt(vm['user_password'], mksalt(METHOD_SHA512)))
            success = LinuxBuilder.build(vm, self.password)
        else:
            logger.error(f'Unsupported idHypervisor ({vm["idHypervisor"]}). VM #{vm_id} cannot be built')
            success = False

        if success:
            logger.info(f'VM #{vm_id} successfully built in Server #{vm["idServer"]}')
            # Change the state of the VM to Built (4) and log a success in Influx
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 4})
            metrics.vm_success()
            # Email the user
            email_notifier.vm_email_notifier(EMAIL_SUCCESS_SUBJECT, vm)
        else:
            logger.info(f'VM #{vm_id} failed to build so it is being moved to Unresourced (3). Check log for details.')
            # Change the state of the VM to Unresourced (3) and log a failure in Influx
            ro.service_entity_update('IAAS', 'vm', vm_id, {'state': 3})
            metrics.vm_failure()
            # Email the User
            email_notifier.vm_email_notifier(EMAIL_FAILURE_SUBJECT, vm)
