"""
updater class for linux vms

- gathers template data
- generates necessary files
- connects to the vm's server and deploys the vm to it
"""
# stdlib
import logging
import os
import shutil
import socket
from typing import Any, Dict, Optional
# lib
import opentracing
from cloudcix.api import IAAS
from jaeger_client import Span
from netaddr import IPAddress
from paramiko import AutoAddPolicy, RSAKey, SSHClient, SSHException
# local
import settings
import state
from mixins import LinuxMixin, VMUpdateMixin
from utils import api_read, JINJA_ENV, get_ceph_pool


__all__ = [
    'Linux',
]


class Linux(LinuxMixin, VMUpdateMixin):
    """
    Class that handles the updating of the specified VM
    When we get to this point, we can be sure that the VM is a linux VM
    """
    # Keep a logger for logging messages from this class
    logger = logging.getLogger('robot.updaters.vm.linux')
    # Keep track of the keys necessary for the template, so we can ensure that all keys are present before updating
    template_keys = {
        # the id that Virsh assigned to the ceph secret,
        'ceph_secret_id',
        # changes for updates
        'changes',
        # the ip address of the host that the VM is running on
        'host_ip',
        # the sudo password of the host, used to run some commands
        'host_sudo_passwd',
        # The IP Address of the Management interface of the physical Router
        'management_ip',
        # the path on the host where the network drive is found
        'network_drive_path',
        # a flag stating if the VM should be turned back on after updating it
        'restart',
        # storage type (HDD/SSD)
        'storage_type',
        # Total drives count is needed for drive names
        'total_drives',
        # an identifier that uniquely identifies the vm
        'vm_identifier',
        # path for vm's .img files located in host
        'vms_path',
    }

    @staticmethod
    def update(vm_data: Dict[str, Any], span: Span) -> bool:
        """
        Commence the update of a vm using the data read from the API
        :param vm_data: The result of a read request for the specified VM
        :param span: The tracing span in use for this update task
        :return: A flag stating if the update was successful
        """
        vm_id = vm_data['id']

        # Generate the necessary template data
        child_span = opentracing.tracer.start_span('generate_template_data', child_of=span)
        template_data = Linux._get_template_data(vm_data, child_span)
        child_span.finish()

        # Check that the data was successfully generated
        if template_data is None:
            error = f'Failed to retrieve template data for VM #{vm_id}.'
            Linux.logger.error(error)
            vm_data['errors'].append(error)
            span.set_tag('failed_reason', 'template_data_failed')
            return False

        # Check that all necessary keys are present
        if not all(template_data[key] is not None for key in Linux.template_keys):
            missing_keys = [f'"{key}"' for key in Linux.template_keys if template_data[key] is None]
            error_msg = f'Template Data Error, the following keys were missing from the VM update data: ' \
                        f'{", ".join(missing_keys)}.'
            Linux.logger.error(error_msg)
            span.set_tag('failed_reason', 'template_data_keys_missing')
            return False

        # Write necessary files into the network drive if required
        network_drive_path = settings.KVM_ROBOT_NETWORK_DRIVE_PATH
        path = f'{network_drive_path}/VMs/{vm_data["project"]["id"]}_{vm_id}'
        if template_data['changes']['gpu'] and len(template_data['changes']['gpu']) > 0:
            child_span = opentracing.tracer.start_span('write_gpu_file_to_network_drive', child_of=span)
            file_write_success = Linux._generate_network_drive_files(vm_data, template_data, path)
            child_span.finish()
            if not file_write_success:
                # The method will log which part failed, so we can just exit
                span.set_tag('failed_reason', 'network_drive_gpu_file_failed_to_write')
                return False

        # If everything is okay, commence updating the VM
        host_ip = template_data.pop('host_ip')

        # Open a client and run the necessary commands on the host
        updated = False
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        key = RSAKey.from_private_key_file('/root/.ssh/id_rsa')
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            # Try connecting to the host and running the necessary commands
            sock.connect((host_ip, 22))
            client.connect(
                hostname=host_ip,
                username='administrator',
                pkey=key,
                timeout=30,
                sock=sock,
            )  # No need for password as it should have keys
            span.set_tag('host', host_ip)

            # Attempt to execute the update command
            Linux.logger.debug(f'Executing update command for VM #{vm_id}')

            # First make sure the VM must be in shutdown state. So sending shutdown commands.
            quiesce = True
            child_span = opentracing.tracer.start_span('generate_quiesce_command', child_of=span)
            cmd = JINJA_ENV.get_template('vm/kvm/commands/quiesce.j2').render(**template_data)
            child_span.finish()
            Linux.logger.debug(f'Generated VM Quiesce command for VM #{vm_id}\n{cmd}')

            child_span = opentracing.tracer.start_span('quiesce_vm', child_of=span)
            stdout, stderr = Linux.deploy(cmd, client, child_span)
            child_span.finish()

            if stdout:
                Linux.logger.debug(f'VM quiesce command for VM #{vm_id} generated stdout.\n{stdout}')
            if stderr:
                Linux.logger.error(f'VM quiesce command for VM #{vm_id} generated stderr.\n{stderr}')
                quiesce = False

            # CPU changes if any.
            cpu = True
            if template_data['changes']['cpu'] and quiesce:
                child_span = opentracing.tracer.start_span('generate_cpu_command', child_of=span)
                cmd = JINJA_ENV.get_template('vm/kvm/commands/update/cpu.j2').render(**template_data)
                child_span.finish()
                Linux.logger.debug(f'Generated VM CPU update command for VM #{vm_id}\n{cmd}')

                child_span = opentracing.tracer.start_span('update_vm_cpu', child_of=span)
                stdout, stderr = Linux.deploy(cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM update CPU command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.error(f'VM update CPU command for VM #{vm_id} generated stderr.\n{stderr}')
                    cpu = False

            # Drive changes if any.
            drive = True
            if template_data['changes']['storages'] and quiesce:
                child_span = opentracing.tracer.start_span('generate_drive_command', child_of=span)
                cmd = JINJA_ENV.get_template('vm/kvm/commands/update/drive.j2').render(**template_data)
                child_span.finish()
                Linux.logger.debug(f'Generated VM Drive update command for VM #{vm_id}\n{cmd}')

                child_span = opentracing.tracer.start_span('update_vm_drive', child_of=span)
                stdout, stderr = Linux.deploy(cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM update Drive command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.error(f'VM update Drive command for VM #{vm_id} generated stderr.\n{stderr}')
                    drive = False

            # GPU changes if any.
            gpu = True
            if template_data['changes']['gpu'] and quiesce:
                child_span = opentracing.tracer.start_span('generate_gpu_command', child_of=span)
                cmd = JINJA_ENV.get_template('vm/kvm/commands/update/gpu.j2').render(**template_data)
                child_span.finish()
                Linux.logger.debug(f'Generated VM GPU update command for VM #{vm_id}\n{cmd}')

                child_span = opentracing.tracer.start_span('update_vm_gpu', child_of=span)
                stdout, stderr = Linux.deploy(cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM update GPU command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.error(f'VM update GPU command for VM #{vm_id} generated stderr.\n{stderr}')
                    gpu = False

            # RAM changes if any.
            ram = True
            if template_data['changes']['ram'] and quiesce:
                child_span = opentracing.tracer.start_span('generate_ram_command', child_of=span)
                cmd = JINJA_ENV.get_template('vm/kvm/commands/update/ram.j2').render(**template_data)
                child_span.finish()
                Linux.logger.debug(f'Generated VM RAM update command for VM #{vm_id}\n{cmd}')

                child_span = opentracing.tracer.start_span('update_vm_ram', child_of=span)
                stdout, stderr = Linux.deploy(cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM update RAM command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.error(f'VM update RAM command for VM #{vm_id} generated stderr.\n{stderr}')
                    ram = False

            # Ceph changes
            ceph_detach = True
            if template_data['changes']['ceph_detach'] and quiesce:
                for ceph in template_data['changes']['ceph_detach']:
                    child_span = opentracing.tracer.start_span('generate_detach_command', child_of=span)
                    cmd = JINJA_ENV.get_template('vm/kvm/commands/update/ceph_detach.j2').render(
                        target_name=ceph['target_name'],
                        **template_data,
                    )
                    child_span.finish()
                    Linux.logger.debug(f'Generated VM Ceph detach command for VM #{vm_id}\n{cmd}')

                    child_span = opentracing.tracer.start_span('ceph_detach', child_of=span)
                    stdout, stderr = Linux.deploy(cmd, client, child_span)
                    child_span.finish()

                    if stdout:
                        Linux.logger.debug(f'VM Ceph Detach command for VM #{vm_id} generated stdout.\n{stdout}')
                    if stderr:
                        Linux.logger.error(f'VM Ceph Detach command for VM #{vm_id} generated stderr.\n{stderr}')
                    ceph_detach = ceph_detach and stdout and ('CephDetachSuccess' in stdout)

            ceph_attach = True
            if template_data['changes']['ceph_attach'] and quiesce:
                for ceph in template_data['changes']['ceph_attach']:
                    template_data['ceph'] = ceph
                    child_span = opentracing.tracer.start_span('generate_attach_command', child_of=span)
                    cmd = JINJA_ENV.get_template('vm/kvm/commands/update/ceph_attach.j2').render(
                        ceph=ceph,
                        **template_data,
                    )
                    child_span.finish()
                    Linux.logger.debug(f'Generated VM Ceph attach command for VM #{vm_id}\n{cmd}')

                    child_span = opentracing.tracer.start_span('ceph_attach', child_of=span)
                    stdout, stderr = Linux.deploy(cmd, client, child_span)
                    child_span.finish()

                    if stdout:
                        Linux.logger.debug(f'VM Ceph attach command for VM #{vm_id} generated stdout.\n{stdout}')
                    if stderr:
                        Linux.logger.error(f'VM Ceph attach command for VM #{vm_id} generated stderr.\n{stderr}')
                    ceph_attach = ceph_attach and stdout and ('CephAttachSuccess' in stdout)

            # Restart the VM if it was in Running state before.
            restart = True
            if template_data['restart']:
                # Also render and deploy the restart_cmd template
                restart_cmd = JINJA_ENV.get_template('vm/kvm/commands/restart.j2').render(**template_data)

                # Attempt to execute the restart command
                Linux.logger.debug(f'Executing restart command for VM #{vm_id}')
                child_span = opentracing.tracer.start_span('restart_vm', child_of=span)
                stdout, stderr = Linux.deploy(restart_cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM restart command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.error(f'VM restart command for VM #{vm_id} generated stderr.\n{stderr}')
                    restart = False

            updated = all([quiesce, drive, cpu, gpu, ceph_detach, ceph_attach, ram, restart])
        except (OSError, SSHException, TimeoutError) as err:
            error = f'Exception occurred while updating VM #{vm_id} in {host_ip}.'
            Linux.logger.error(error, exc_info=True)
            vm_data['errors'].append(f'{error} Error: {err}')
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()

        # remove all the files created in network drive
        if template_data['changes']['gpu'] and len(template_data['changes']['gpu']) > 0:
            try:
                shutil.rmtree(path)
            except OSError:
                Linux.logger.warning(f'Failed to remove network drive gpu file for VM #{vm_id}')

        return updated

    @staticmethod
    def _get_template_data(vm_data: Dict[str, Any], span: Span) -> Optional[Dict[str, Any]]:
        """
        Given the vm data from the API, create a dictionary that contains all the necessary keys for the template
        The keys will be checked in the update method and not here, this method is only concerned with fetching the data
        that it can.
        :param vm_data: The data of the VM read from the API
        :param span: The tracing span in use for this task. In this method, just pass it to API calls.
        :returns: The data needed for the templates to update a Linux VM
        """
        vm_id = vm_data['id']
        Linux.logger.debug(f'Compiling template data for VM #{vm_id}')
        data: Dict[str, Any] = {key: None for key in Linux.template_keys}

        data['vm_identifier'] = f'{vm_data["project"]["id"]}_{vm_id}'
        data['management_ip'] = settings.MGMT_IP
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD

        # changes
        changes: Dict[str, Any] = {
            'ram': False,
            'cpu': False,
            'gpu': False,
            'storages': False,
            'ceph_attach': list(),
            'ceph_detach': list(),
        }
        updates = vm_data['history'][0]
        try:
            if updates['ram_quantity'] is not None:
                # RAM is needed in MB for the updater but we take it in GB (1024, not 1000)
                changes['ram'] = vm_data['ram'] * 1024
        except KeyError:
            pass
        try:
            if updates['cpu_quantity'] is not None:
                changes['cpu'] = vm_data['cpu']
        except KeyError:
            pass

        # Fetch the device information for the update
        try:
            if updates['gpu_quantity'] is not None:
                # There can only be cases:
                # 1. len(vm_data['gpu_devices']) = gpu_quantity(vm['gpu']) but not
                # len(vm_data['gpu_devices']) < gpu_quantity, if exits then its API mistake. OR
                # 2. len(vm_data['gpu_devices']) > gpu_quantity (vm['gpu'])
                # (a case where Robot has to detach gpus to make length vm_data['gpu_devices'] = gpu_quantity)
                if len(vm_data['gpu_devices']) == vm_data['gpu']:
                    # detach all the gpu devices(changes['gpu']) and attach (changes['gpu_attach']) all present devices
                    changes['gpu'] = changes['gpu_attach'] = vm_data['gpu_devices']
                elif len(vm_data['gpu_devices']) > vm_data['gpu']:
                    # detach all the gpu devices and attach vm['gpu'] number of devices
                    # slice the present_devices into two lists, one with devices to attach
                    # and other with devices to reset on database
                    changes['gpu_attach'] = list(vm_data['gpu_devices'])[:updates['gpu_quantity']]
                    changes['gpu'] = vm_data['gpu_devices']
                    vm_data['reset_gpus'] = list(vm_data['gpu_devices'])[updates['gpu_quantity']:]
                else:
                    error = f'Invalid case of GPU quantity is more than the devices assigned # {vm_id}.'
                    Linux.logger.error(error)
                    vm_data['errors'].append(error)
                    return None

        except KeyError:
            pass

        # Fetch the drive information for the update
        try:
            if len(updates['storage_histories']) != 0:
                Linux.logger.debug(f'Fetching drives for VM #{vm_id}')
                child_span = opentracing.tracer.start_span('fetch_drive_updates', child_of=span)
                changes['storages'] = Linux.fetch_drive_updates(vm_data)
                child_span.finish()
        except KeyError:
            pass

        # Add changes to data
        data['changes'] = changes
        data['network_drive_path'] = settings.KVM_HOST_NETWORK_DRIVE_PATH
        data['storage_type'] = vm_data['storage_type']
        data['total_drives'] = len(vm_data['storages'])
        data['vms_path'] = settings.KVM_VMS_PATH

        # Get the ip address of the host
        host_ip = None
        for interface in vm_data['server_data']['interfaces']:
            if interface['enabled'] is True and interface['ip_address'] is not None:
                if IPAddress(str(interface['ip_address'])).version == 6:
                    host_ip = interface['ip_address']
                    break
        if host_ip is None:
            error = f'Host ip address not found for the server # {vm_data["server_id"]}.'
            Linux.logger.error(error)
            vm_data['errors'].append(error)
            return None
        data['host_ip'] = host_ip

        # Determine restart
        data['restart'] = vm_data['restart']

        linked_resources = updates.get('linked_resources', list())
        for r in linked_resources:
            # Read the resource to get its specs
            resource = api_read(IAAS.ceph, pk=r['id'])
            if resource is None:
                continue

            if resource['state'] is state.RUNNING:
                changes['ceph_attach'].append(resource)
            elif resource['state'] is state.QUIESCE:
                changes['ceph_detach'].append(resource)
            else:
                Linux.logger.warning(
                    f'Found linked resource #{resource["id"]} in state {resource["state"]}. ',
                    f'Should be {state.RUNNING} or {state.QUIESCE})',
                )
                continue

            resource['identifier'] = f'{resource["project_id"]}_{resource["id"]}'
            resource['pool_name'] = get_ceph_pool(resource['specs'][0]['sku'])
            resource['source_name'] = f'{resource["pool_name"]}/{resource["identifier"]}'

        # Generate drive targets for any new ceph drives
        drive_target_map = Linux._get_drive_map(
            host_ip,
            data['vm_identifier'],
            settings.NETWORK_PASSWORD,
            span,
        )
        if drive_target_map is None:
            return data

        target_prefix = 'hd'
        for ceph in data['changes']['ceph_attach']:
            # Generate a drive letter
            for letter in range(ord('a'), ord('z') + 1):
                target_name = target_prefix + chr(letter)
                if target_name not in drive_target_map:
                    break

            if target_name in drive_target_map:
                Linux.logger.info(f'Could not generate new drive name for Ceph #{ceph["id"]}')
                return {}

            # Assign the target to the ceph drive
            ceph['target_name'] = target_name
            drive_target_map[target_name] = ceph['source_name']

        for ceph in data['changes']['ceph_detach']:
            # Match up the existing names for the drives for detaching
            for target_name, source_name in drive_target_map:
                if ceph['source_name'] == source_name:
                    ceph['target_name'] = target_name
                    continue

        # Get the Ceph secret id
        data['ceph_secret_uuid'] = Linux._get_ceph_secret_uuid(host_ip, settings.NETWORK_PASSWORD, span)
        return data

    @staticmethod
    def _get_ceph_secret_uuid(host_ip, host_sudo_passwd, span):
        client = Linux._get_client(host_ip)
        if client is None:
            return None

        cmd = JINJA_ENV.get_template('vm/kvm/commands/get_ceph_secret.j2').render(
            host_sudo_passwd=host_sudo_passwd,
        )
        Linux.logger.debug(f'Generated GetCephSecret command for host {host_ip}')

        child_span = opentracing.tracer.start_span('get_ceph_secret_id', child_of=span)
        try:
            stdout, stderr = Linux.deploy(cmd, client, child_span)
        except SSHException:
            error = f'Exception occurred while running command on {host_ip}.'
            Linux.logger.error(error, exc_info=True)
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()
        child_span.finish()

        if stdout:
            Linux.logger.debug(f'GetCephSecret command for host {host_ip} generated stdout.\n{stdout}')
        if stderr:
            Linux.logger.error(f'GetCephSecret command for host {host_ip} generated  stderr.\n{stderr}')

    @staticmethod
    def _get_drive_map(host_ip, vm_id, host_sudo_passwd, span) -> Dict[str, str]:
        client = Linux._get_client(host_ip)
        if client is None:
            return None

        cmd = JINJA_ENV.get_template('vm/kvm/commands/list_drives.j2').render(
            vm_identifier=vm_id,
            host_sudo_passwd=host_sudo_passwd,
        )
        Linux.logger.debug(f'Generated DriveList command for VM #{vm_id}')

        child_span = opentracing.tracer.start_span('list_drives', child_of=span)
        try:
            stdout, stderr = Linux.deploy(cmd, client, span)
        except SSHException:
            error = f'Exception occurred while executing command on {host_ip}.'
            Linux.logger.error(error, exc_info=True)
            span.set_tag('failed_reason', 'ssh_error')
        finally:
            client.close()
        child_span.finish()

        if stdout:
            Linux.logger.debug(f'VM DriveList command for VM #{vm_id} generated stdout.\n{stdout}')
        if stderr:
            Linux.logger.error(f'VM DriveList command for VM #{vm_id} generated stderr.\n{stderr}')

        drives = dict()
        # Expect output as lines of `<target_name> <source_name>`. Put the data into a dictionary
        for line in stdout.split('\n'):
            target, source = line.split(' ')
            drives[target] = source
        # There should be at least one fs drive returned. If not, something went wrong
        if not drives:
            return None
        return drives

    @staticmethod
    def _generate_network_drive_files(vm_data: Dict[str, Any], template_data: Dict[str, Any], path: str) -> bool:
        """
        Generate and write files into the network drive so they are on the host for the update scripts to utilise.
        Writes the following files to the drive;
            - pci_gpu.xml
            - ceph.xml
        :param vm_data: The data of the VM read from the API
        :param template_data: The retrieved template data for the kvm vm
        :param path: Network drive location to create above files for VM build
        :returns: A flag stating if the job was successful
        """
        vm_id = vm_data['id']
        # Create a folder by vm_identifier name at network_drive_path/VMs/
        try:
            os.mkdir(path)
        except FileExistsError:
            pass
        except OSError as err:
            error = f'Failed to create directory for VM #{vm_id} at {path}.'
            Linux.logger.error(error, exc_info=True)
            vm_data['errors'].append(f'{error} Error: {err}')
            return False

        # Render and attempt to write the pci_gpu files
        template_name = 'vm/kvm/device/pci_gpu.j2'
        for device in vm_data['gpu_devices']:
            pci_gpu_data = JINJA_ENV.get_template(template_name).render(device=device['id_on_host'])
            Linux.logger.debug(f'Generated pci_gpu_{device["id"]}.xml file for VM #{vm_id}\n{pci_gpu_data}')
            pci_gpu_file_path = f'{path}/pci_gpu_{device["id"]}.xml'
            try:
                # Attempt to write
                with open(pci_gpu_file_path, 'w') as f:
                    f.write(pci_gpu_data)
                Linux.logger.debug(
                    f'Successfully wrote pci_gpu_{device["id"]}.xml file for VM #{vm_id} to {pci_gpu_file_path}',
                )
            except IOError as err:
                error = f'Failed to write pci_gpu_{device["id"]}.xml file for VM #{vm_id} to {pci_gpu_file_path}'
                Linux.logger.error(error, exc_info=True)
                vm_data['errors'].append(f'{error} Error: {err}')
                return False

        # Render and attempt to write the ceph.xml files
        if template_data['changes']['ceph_attach']:
            if len(settings.CEPH_MONITORS) == 0:
                Linux.logger.debug('No CephMonitors set, cannot generate Ceph template')
                return False

            template_name = 'vm/kvm/device/ceph.j2'
            for ceph in template_data['changes']['ceph_attach']:
                ceph_data = JINJA_ENV.get_template(template_name).render(ceph=ceph, **template_data)
                Linux.logger.debug(f'Generated ceph_{ceph["id"]}.xml file for VM #{vm_id}\n{pci_gpu_data}')
                ceph_file_path = f'{path}/ceph_{ceph["id"]}.xml'
                try:
                    # Attempt to write
                    with open(ceph_file_path, 'w') as f:
                        f.write(ceph_data)
                    Linux.logger.debug(
                        f'Successfully wrote to {ceph_file_path} file for VM #{vm_id}',
                    )
                except IOError as err:
                    error = f'Failed to write {ceph_file_path} file for VM #{vm_id}'
                    Linux.logger.error(error, exc_info=True)
                    vm_data['errors'].append(f'{error} Error: {err}')
                    return False

        # Return True as all was successful
        return True

    def _get_client(host_ip):
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        key = RSAKey.from_private_key_file('/root/.ssh/id_rsa')
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            # Try connecting to the host
            sock.connect((host_ip, 22))
            client.connect(
                hostname=host_ip,
                username='administrator',
                pkey=key,
                timeout=30,
                sock=sock,
            )
        except SSHException:
            error = f'Exception occurred while connecting to {host_ip}.'
            Linux.logger.error(error, exc_info=True)
            client.close()
            return None
        return client
