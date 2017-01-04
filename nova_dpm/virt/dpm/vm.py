# Copyright 2016 IBM Corp. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Partition will map nova parameter to PRSM parameter
"""
import sys
import time

from nova.compute import manager as compute_manager
from nova.compute import power_state
from nova.compute import task_states
from nova.compute import vm_states
from nova import exception
from nova.i18n import _
from nova.i18n import _LE
from nova_dpm.virt.dpm import utils
from oslo_log import log as logging
from oslo_utils import importutils
from zhmcclient._exceptions import NotFound

zhmcclient = None


DPM_TO_NOVA_STATE = {
    utils.PartitionState.RUNNING: power_state.RUNNING,
    utils.PartitionState.STOPPED: power_state.SHUTDOWN,
    utils.PartitionState.UNKNOWN: power_state.NOSTATE,
    utils.PartitionState.PAUSED: power_state.PAUSED,
    utils.PartitionState.STARTING: power_state.PAUSED
}

OBJECT_ID = 'object-id'
CPCSUBSET_NAME = 'cpcsubset_name'
LOG = logging.getLogger(__name__)


def _translate_vm_state(dpm_state):

    if dpm_state is None:
        return power_state.NOSTATE

    try:
        nova_state = DPM_TO_NOVA_STATE[dpm_state.lower()]
    except KeyError:
        nova_state = power_state.NOSTATE

    return nova_state


def _get_zhmclient():
    """Lazy initialization for zhmcclient

    This function helps in lazy loading zhmclient. The zhmcclient can
    otherwise be set to fakezhmcclient for unittest framework
    """

    LOG.debug("_get_zhmclient")
    global zhmcclient
    if zhmcclient is None:
        zhmcclient = importutils.import_module('zhmcclient')


class Instance(object):
    def __init__(self, instance, cpc, client, flavor=None):
        _get_zhmclient()
        self.instance = instance
        self.flavor = flavor
        self.cpc = cpc
        self.client = client
        self.partition = self.get_partition(self.cpc, self.instance)

    def properties(self):
        properties = {}
        properties['name'] = self.instance.hostname
        if self.flavor is not None:
            properties['cp-processors'] = self.flavor.vcpus
            properties['initial-memory'] = self.flavor.memory_mb
            properties['maximum-memory'] = self.flavor.memory_mb
        return properties

    def create(self, properties):
        partition_manager = zhmcclient.PartitionManager(self.cpc)
        self.partition = partition_manager.create(properties)

    def attach_nic(self, conf, network_info):
        # TODO(preethipy): Implement the listener flow to register for
        # nic creation events
        LOG.debug("Creating nic interface for the instance")

        for vif in network_info:

            port_id = vif['id']
            vif_type = vif['type']
            mac = vif['address']
            vif_details = vif['details']
            dpm_object_id = vif_details[OBJECT_ID]

            # Only dpm_vswitch attachments are supported for now
            if vif_type != "dpm_vswitch":
                raise Exception

            dpm_nic_dict = {
                "name": "OpenStack_Port_" + str(port_id),
                "description": "OpenStack mac= " + mac +
                               ", CPCSubset= " +
                               conf[CPCSUBSET_NAME],
                "virtual-switch-uri": "/api/virtual-switches/"
                                      + dpm_object_id
            }
            nic_interface = self.partition.nics.create(dpm_nic_dict)
            LOG.debug("NIC created successfully %(nic_name)s "
                      "with URI %(nic_uri)s"
                      % {'nic_name': nic_interface.properties['name'],
                         'nic_uri': nic_interface.properties[
                             'virtual-switch-uri']})
        return nic_interface

    def attachHba(self, conf):
        LOG.debug('Creating vhbas for instance',
                  instance=self.instance)
        mapping = self.createStorageAdapterUris(conf)
        for adapterPort in mapping.get_adapter_port_mapping():
            adapter_object_id = adapterPort['adapter_id']
            adapter_port = adapterPort['port']
            dpm_hba_dict = {
                "name": "OpenStack_Port_" + adapter_object_id +
                        "_" + str(adapter_port),
                "description": "OpenStack CPCSubset= " +
                               conf[CPCSUBSET_NAME],
                "adapter-port-uri": "/api/adapters/"
                                    + adapter_object_id +
                                    "/storage-ports/" +
                                    str(adapter_port)
            }
            hba = self.partition.hbas.create(dpm_hba_dict)
            LOG.debug("HBA created successfully %(hba_name)s "
                      "with URI %(hba_uri)s and adapterporturi"
                      "%(adapter-port-uri)s"
                      % {'hba_name': hba.properties['name'],
                         'hba_uri': hba.properties[
                             'element-uri'],
                         'adapter-port-uri': hba.properties[
                             'adapter-port-uri']})

    def createStorageAdapterUris(self, conf):
        LOG.debug('Creating Adapter uris')
        interface_mappings = conf['physical_storage_adapter_mappings']
        mapping = PhysicalAdapterModel(self.cpc)
        for entry in interface_mappings:
            adapter_uuid, port = \
                PhysicalAdapterModel._parse_config_line(entry)
            adapter = mapping._get_adapter(adapter_uuid)
            mapping._validate_adapter_type(adapter)
            mapping._add_adapter_port(adapter_uuid, port)
        return mapping

    def _build_resources(self, context, instance, block_device_mapping):
        LOG.debug('Start building block device mappings for instance.',
                  instance=self.instance)
        resources = {}
        instance.vm_state = vm_states.BUILDING
        instance.task_state = task_states.BLOCK_DEVICE_MAPPING
        instance.save()

        block_device_info = compute_manager.ComputeManager().\
            _prep_block_device(context, instance,
                               block_device_mapping)
        resources['block_device_info'] = block_device_info
        return resources

    def get_hba_properties(self):
        LOG.debug('Get Hba properties')

    def launch(self, partition=None):
        LOG.debug('Partition launch triggered')
        self.instance.vm_state = vm_states.BUILDING
        self.instance.task_state = task_states.SPAWNING
        self.instance.save()
        bootproperties = self.get_boot_properties()
        self.partition.update_properties(properties=bootproperties)
        result = self.partition.start(True)
        # TODO(preethipy): The below method to be removed once the bug
        # on DPM is fixed to return correct status on API return
        self._loop_status_update(result, 5, 'Active')

    def destroy(self):
        LOG.debug('Partition Destroy triggered')
        if self.partition:
            result = self.partition.stop(True)
            # TODO(preethipy): The below method to be removed once the bug
            # on DPM is fixed to return correct status on API return
            self._loop_status_update(result, 5, 'stopped')
            if (self.partition.properties['status'] == 'stopped'):
                self.partition.delete()
            else:
                errormsg = (_("Partition - %(partition)s status "
                              "%(status)s is invalid") %
                            {'partition': self.partition.properties['name'],
                             'status': self.partition.properties['status']})
                raise exception.InstanceInvalidState(errormsg)
        else:
            errormsg = (_("Partition - %(partition)s does not exist") %
                        {'partition': self.partition.properties['name']})
            raise exception.InstanceNotFound(errormsg)

    def power_on_vm(self):
        LOG.debug('Partition power on triggered')
        result = self.partition.start(True)
        # TODO(preethipy): The below method to be removed once the bug
        # on DPM(701894) is fixed to return correct status on API return
        self._loop_status_update(result, 5, 'Active')

    def power_off_vm(self):
        LOG.debug('Partition power off triggered')
        result = self.partition.stop(True)
        # TODO(preethipy): The below method to be removed once the bug
        # on DPM(701894) is fixed to return correct status on API return
        self._loop_status_update(result, 5, 'stopped')

    def reboot_vm(self):
        LOG.debug('Partition reboot triggered')
        result = self.partition.stop(True)
        # TODO(preethipy): The below method to be removed once the bug
        # on DPM is fixed to return correct status on API return
        self._loop_status_update(result, 5, 'stopped')

        result = self.partition.start(True)
        # TODO(preethipy): The below method to be removed once the bug
        # on DPM is fixed to return correct status on API return
        self._loop_status_update(result, 5, 'Active')

    def _loop_status_update(self, result, iterations, status):
        # TODO(preethipy): This method loops until the partition goes out
        # of pause state or until the iterations complete. Introduced because
        # of the bug in DPM for having status populated correctly only
        # after 4-5 seconds
        self.partition.pull_full_properties()
        if (result['status'] == 'complete'):
            while (self.partition.properties['status'] != status) and (
                    iterations):
                LOG.debug("sleep for 2 seconds every iteration "
                          "for status check")
                time.sleep(2)
                iterations -= 1

    def get_boot_properties(self):
        LOG.debug('Retrieving boot properties for partition')
        # TODO(preethipy): update the boot-device to storage-adapter
        # TODO(preethipy): update the boot-storage-device with valid
        # HBA uri
        # TODO(preethipy): update boot-logical-unit-number and
        # boot-world-wide-port-name
        bootProperties = {'boot-device': 'test-operating-system'}
        return bootProperties

    def get_partition(self, cpc, instance):
        partition = None
        partition_manager = zhmcclient.PartitionManager(cpc)
        partition_lists = partition_manager.list(
            full_properties=False)
        for part in partition_lists:
            if part.properties['name'] == instance.hostname:
                partition = part
        return partition


class InstanceInfo(object):
    """Instance Information

    This object loads VM information like state, memory used etc

    """

    def __init__(self, instance, cpc):
        _get_zhmclient()
        self.instance = instance
        self.cpc = cpc
        self.partition = None
        partition_manager = zhmcclient.PartitionManager(self.cpc)
        partition_lists = partition_manager.list(full_properties=False)
        for partition in partition_lists:
            if partition.properties['name'] == self.instance.hostname:
                self.partition = partition
                self.partition.pull_full_properties()

    @property
    def state(self):

        status = None
        if self.partition is not None:
            status = self.partition.get_property('status')

        return _translate_vm_state(status)

    @property
    def mem(self):

        mem = None
        if self.partition is not None:
            mem = self.partition.get_property('initial-memory')

        return mem

    @property
    def max_mem(self):

        max_mem = None
        if self.partition is not None:
            max_mem = self.partition.get_property('maximum-memory')

        return max_mem

    @property
    def num_cpu(self):

        num_cpu = None
        if self.partition is not None:
            num_cpu = self.partition.get_property('cp-processors')

        return num_cpu

    @property
    def cpu_time(self):

        # TODO(pranjank): will implement
        # As of now returning dummy value
        return 100


class PhysicalAdapterModel(object):
    """Model for physical storage adapter

    Validates and retrieval capabilities for
    adapter id and port
    """
    def __init__(self, cpc):
        self._cpc = cpc
        self._adapter_ports = []

    def _get_adapter(self, adapter_id):
        try:
            # TODO(andreas_s): Optimize in zhmcclient - For 'find' the
            # whole list of items is retrieved
            return self._cpc.adapters.find(**{'object-id': adapter_id})
        except NotFound:
            LOG.error(_LE("Configured adapter %s could not be "
                          "found. Please update the agent "
                          "configuration. Agent terminated!"),
                      adapter_id)
            sys.exit(1)

    @staticmethod
    def _validate_adapter_type(adapter):
        adapt_type = adapter.get_property('type')
        if adapt_type not in ['fcp']:
            LOG.error(_LE("Configured adapter %s is not an fcp "),
                      adapter)
            sys.exit(1)

    def _add_adapter_port(self, adapter_id, port):
        self._adapter_ports.append({"adapter_id": adapter_id,
                                    "port": port})

    def get_adapter_port_mapping(self):
        """Get a list of adapter port uri

        :return: list of adapter_port dict
        """
        return self._adapter_ports

    @staticmethod
    def _parse_config_line(line):
        result = line.split(":")
        adapter_id = result[0]
        # If no port-element-id was defined, default to 0
        # result[1] can also be '' - handled by 'and result[1]'
        port = int(result[1] if len(result) == 2 and result[1] else 0)
        return adapter_id, port