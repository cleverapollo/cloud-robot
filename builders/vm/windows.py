"""
builder class for windows vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
import random
import string
from collections import deque
from typing import Any, Deque, Dict, Optional
# lib
from cloudcix.api import IAAS
from netaddr import IPAddress
from winrm.exceptions import WinRMError
# local
import settings
import utils
from mixins import WindowsMixin


__all__ = [
    'Windows',
]

# Map that maps image ids to the name of the unattend file that will be used for the VM
UNATTEND_TEMPLATE_MAP = settings.OS_TEMPLATE_MAP['Windows']


class Windows(WindowsMixin):
    """
    Class that handles the building of the specified VM
    When we get to this point, we can be sure that the VM is a windows VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.builders.vm.windows')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before building
    template_keys = {
        # the admin password for the vm, unencrypted
        'admin_password',
        # the number of cpus in the vm
        'cpu',
        # the dns servers for the vm (in list form, not string form)
        'dns',
        # the drives in the vm
        'drives',
        # the freenas url for the region
        'freenas_url',
        # the subnet gateway
        'gateway',
        # the hdd primary drive of the VM 'id:size'
        'hdd',
        # the DNS hostname for the host machine, as WinRM cannot use IPv6
        'host_name',
        # the filename of the image used to build the vm
        'image_filename',
        # the id of the image used to build the VM
        'image_id',
        # the ip address of the vm in its subnet
        'ip_address',
        # the language of the vm
        'language',
        # the subnet mask in integer form (/24)
        'netmask_int',
        # the amount of RAM in the VM
        'ram',
        # the ssd primary drive of the VM 'id:size'
        'ssd',
        # the timezone of the vm
        'timezone',
        # the vlan that the vm is a part of
        'vlan',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
    }

    @staticmethod
    def build(vm_data: Dict[str, Any], image_data: Dict[str, Any]) -> bool:
        """
        Commence the build of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param image_data: The data of the image for the VM
        :return: A flag stating whether or not the build was successful
        """
        vm_id = vm_data['idVM']

        # Generate the necessary template data
        template_data = Windows._get_template_data(vm_data, image_data)

        # Check that the data was successfully generated
        if template_data is None:
            Windows.logger.error(
                f'Failed to retrieve template data for VM #{vm_id}.',
            )
            return False

        # Check that all of the necessary keys are present
        if not all(template_data[key] is not None for key in Windows.template_keys):
            missing_keys = [
                f'"{key}"' for key in Windows.template_keys if template_data[key] is None
            ]
            Windows.logger.error(
                f'Template Data Error, the following keys were missing from the VM build data: '
                f'{", ".join(missing_keys)}',
            )
            return False

        # If everything is okay, commence building the VM
        host_name = template_data.pop('host_name')
        image_id = template_data.pop('image_id')

        # Write necessary files into the network drive
        file_write_success = Windows._generate_network_drive_files(vm_id, image_id, template_data)
        if not file_write_success:
            # The method will log which part failed, so we can just exit
            return False

        # Render the build command
        vm_build_cmd = utils.JINJA_ENV.get_template('vm/windows/build_cmd.j2').render(**template_data)

        # Open a client and run the two necessary commands on the host
        built = False
        try:
            response = Windows.deploy(vm_build_cmd, host_name)
        except WinRMError:
            Windows.logger.error(
                f'Exception occurred while attempting to build VM #{vm_id} on {host_name}',
                exc_info=True,
            )
        else:
            # Check the stdout and stderr for messages
            if response.std_out:
                msg = response.std_out.strip()
                Windows.logger.debug(f'VM build command for VM #{vm_id} generated stdout\n{msg}')
                built = 'VM Successfully Created' in msg
            if response.std_err:
                msg = response.std_err.strip()
                Windows.logger.warning(f'VM build command for VM #{vm_id} generated stderr\n{msg}')
        finally:
            return built

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], image_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all of the necessary keys for the template
        The keys will be checked in the build method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :param image_data: The data of the Image for the VM
        :returns: The data needed for the templates to build a Windows VM
        """
        vm_id = vm_data['idVM']
        Windows.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Windows.template_keys}

        data['vm_identifier'] = f'{vm_data["idProject"]}_{vm_data["idVM"]}'
        data['image_filename'] = image_data['filename']
        data['image_id'] = image_data['idImage']
        # RAM is needed in MB for the builder but we take it in in GB
        data['ram'] = vm_data['ram'] * 1000
        data['cpu'] = vm_data['cpu']
        data['dns'] = [server.strip() for server in vm_data['dns'].split(',')]

        # Generate encrypted passwords
        data['admin_password'] = Windows._password_generator(size=8)

        # Fetch the drives for the VM and add them to the data
        drives: Deque[str] = deque()
        for storage in utils.api_list(IAAS.storage, {}, vm_id=vm_id):
            # Check if the storage is primary
            if storage['primary']:
                # Determine which field (hdd or ssd) to populate with this storage information
                if storage['storage_type'] == 'HDD':
                    data['hdd'] = f'{storage["idStorage"]}:{storage["gb"]}'
                    data['ssd'] = 0
                elif storage['storage_type'] == 'SSD':
                    data['hdd'] = 0
                    data['ssd'] = f'{storage["idStorage"]}:{storage["gb"]}'
                else:
                    Windows.logger.error(
                        f'Invalid primary drive storage type {storage["storage_type"]}. Expected either "HDD" or "SSD"',
                    )
                    return None
            else:
                # Just append to the drives deque
                drives.append(f'{storage["idStorage"]}:{storage["gb"]}')
        if len(drives) > 0:
            data['drives'] = ','.join(drives)
        else:
            data['drives'] = 0

        # Get the Networking details
        for ip_address in utils.api_list(IAAS.ipaddress, {'vm': vm_id}):
            # The private IP for the VM will be the one we need to pass to the template
            if not IPAddress(ip_address['address']).is_private():
                continue
            data['ip_address'] = ip_address['address']
            # Read the subnet for the IPAddress to fetch information like the gateway and subnet mask
            subnet = utils.api_read(IAAS.subnet, ip_address['idSubnet'])
            if subnet is None:
                return None
            data['gateway'], data['netmask_int'] = subnet['addressRange'].split('/')
            data['vlan'] = subnet['vLAN']

        # Add locale data to the VM
        data['language'] = 'en_IE'
        data['timezone'] = 'GMT Standard Time'

        # Get the ip address of the host
        for mac in utils.api_list(IAAS.macaddress, {}, server_id=vm_data['idServer']):
            if mac['status'] is True and mac['ip'] is not None:
                data['host_name'] = mac['dnsName']
                break

        # Add the host information to the data
        data['freenas_url'] = settings.FREENAS_URL
        return data

    @staticmethod
    def _generate_network_drive_files(vm_id: int, image_id: int, template_data: Dict[str, Any]) -> bool:
        """
        Generate and write files into the network drive so they are on the host for the build scripts to utilise.
        Writes the following files to the drive;
            - unattend file
        :param vm_id: The id of the VM being built. Used for log messages
        :param image_id: The id of the image used to build the VM
        :param template_data: The retrieved template data for the vm
        :returns: A flag stating whether or not the job was successful
        """
        # Determine the unattend template to use for the VM
        os_name = UNATTEND_TEMPLATE_MAP.get(image_id, None)
        network_drive_path = settings.HYPERV_ROBOT_NETWORK_DRIVE_PATH
        if os_name is None:
            valid_ids = ', '.join(f'`{map_id}`' for map_id in UNATTEND_TEMPLATE_MAP.keys())
            Windows.logger.error(
                f'Invalid Windows Image ID for VM #{vm_id}. Received {image_id}, valid choices are {valid_ids}.',
            )
            return False

        # Render and attempt to write the unattend file
        template_name = f'vm/windows/unattends/{os_name}.j2'
        unattend = utils.JINJA_ENV.get_template(template_name).render(**template_data)
        Windows.logger.debug(f'Generated unattend file for VM #{vm_id}\n{unattend}')
        try:
            # Attempt to write
            unattend_filename = f'{network_drive_path}/unattend_xmls/{template_data["vm_identifier"]}.xml'
            with open(unattend_filename, 'w') as f:
                f.write(unattend)
            Windows.logger.debug(f'Successfully wrote unattend file for VM #{vm_id} to {unattend_filename}')
        except IOError:
            Windows.logger.error(
                f'Failed to write unattend file for VM #{vm_id} to {unattend_filename}',
                exc_info=True,
            )
            return False

        # Return True as all was successful
        return True

    @staticmethod
    def _password_generator(size: int = 8, chars: Optional[str] = None) -> str:
        """
        Returns a string of random characters, useful in generating temporary
        passwords for automated password resets.

        :param size: default=8; override to provide smaller/larger passwords
        :param chars: default=A-Za-z0-9; override to provide more/less diversity
        :return: A password of length 'size' generated randomly from 'chars'
        """
        if chars is None:
            chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(size))
