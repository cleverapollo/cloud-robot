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
from jaeger_client import Span
from netaddr import IPAddress
from paramiko import AutoAddPolicy, RSAKey, SSHClient, SSHException
# local
import settings
import state
from mixins import LinuxMixin, VMUpdateMixin
from utils import JINJA_ENV, get_ceph_monitors, get_ceph_pool


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
        if len(template_data['changes']['gpu']) > 0:
            child_span = opentracing.tracer.start_span('write_gpu_file_to_network_drive', child_of=span)
            file_write_success = Linux._generate_network_drive_files(vm_data, template_data, path)
            child_span.finish()
            if not file_write_success:
                # The method will log which part failed, so we can just exit
                span.set_tag('failed_reason', 'network_drive_gpu_file_failed_to_write')
                return False

        # If everything is okay, commence updating the VM
        host_ip = template_data.pop('host_ip')

        # Open a client and run the two necessary commands on the host
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
            if template_data['changes']['ceph']['detach'] and quiesce:
                child_span = opentracing.tracer.start_span('generate_detach_command', child_of=span)
                cmd = JINJA_ENV.get_template('vm/kvm/commands/update/ceph_detach.j2').render(**template_data)
                child_span.finish()
                Linux.logger.debug(f'Generated VM Ceph detach command for VM #{vm_id}\n{cmd}')

                child_span = opentracing.tracer.start_span('ceph_detach', child_of=span)
                stdout, stderr = Linux.deploy(cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM Ceph Detach command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.error(f'VM Ceph Detach command for VM #{vm_id} generated stderr.\n{stderr}')
                    ceph_detach = False

            ceph_attach = True
            if template_data['changes']['ceph']['attach'] and quiesce:
                child_span = opentracing.tracer.start_span('generate_attach_command', child_of=span)
                cmd = JINJA_ENV.get_template('vm/kvm/commands/update/ceph_attach.j2').render(**template_data)
                child_span.finish()
                Linux.logger.debug(f'Generated VM Ceph attach command for VM #{vm_id}\n{cmd}')

                child_span = opentracing.tracer.start_span('ceph_attach', child_of=span)
                stdout, stderr = Linux.deploy(cmd, client, child_span)
                child_span.finish()

                if stdout:
                    Linux.logger.debug(f'VM Ceph attach command for VM #{vm_id} generated stdout.\n{stdout}')
                if stderr:
                    Linux.logger.error(f'VM Ceph attach command for VM #{vm_id} generated stderr.\n{stderr}')
                    ceph_detach = False

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
        if len(template_data['changes']['gpu']) > 0:
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

        # changes
        changes: Dict[str, Any] = {
            'ram': False,
            'cpu': False,
            'gpu': False,
            'storages': False,
            'ceph': False,
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

        linked_resources = updates.get('linked_resources', list())
        attach = list()
        detach = list()
        for resource in linked_resources:
            resource['identifier'] = f'{resource["project_id"]}_{resource["id"]}'
            resource['pool_name'] = get_ceph_pool(resource['specs'][0]['sku'])

            if resource['state'] is state.RUNNING:
                attach.append(resource)
            elif resource['state'] is state.QUIESCE:
                detach.append(resource)
            else:
                Linux.logger.warning(
                    f'Found linked resource #{resource["id"]} in state {resource["state"]}. ',
                    f'Should be {state.RUNNING} or {state.QUIESCE})',
                )

        if len(attach) > 0 or len(detach) > 0:
            changes['ceph'] = {
                'attach': attach,
                'detach': detach,
            }

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

        # Add the host information to the data
        data['host_sudo_passwd'] = settings.NETWORK_PASSWORD

        # Determine restart
        data['restart'] = vm_data['restart']

        return data

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

        # Render and write the Ceph XML snippets for attaching
        monitor_ips = get_ceph_monitors()
        if monitor_ips is None or len(monitor_ips) == 0:
            Linux.logger.error('Could not get Ceph Monitor IPs when building ')
            return False

        template_name = 'vm/kvm/device/ceph.xml.j2'
        template = JINJA_ENV.get_template(template_name)
        for ceph in template_data['changes']['ceph_attach']:
            ceph_xml = template.render(
                device_name=ceph['identifier'],
                monitor_ips=monitor_ips,
                pool_name=ceph['pool_name'],
            )
            ceph_file_path = f'{path}/ceph_{ceph["identifier"]}.xml'

            try:
                # Attempt to write
                with open(ceph_file_path, 'w') as f:
                    f.write(ceph_xml)
                Linux.logger.debug(f'Successfully wrote {ceph_file_path} for ceph #{ceph["id"]}')
            except IOError as err:
                error = f'Failed to write {ceph_file_path} for ceph #{ceph["id"]}'
                Linux.logger.error(error, exc_info=True)
                vm_data['errors'].append(f'{error} Error: {err}')
                return False

        # Return True as all was successful
        return True
