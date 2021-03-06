# -*- coding: utf-8 -*-
#
# Copyright 2014, 2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
from __future__ import absolute_import

import functools
import os
from os import EX_OK
import re

import pytest

from ost_utils import ansible
from ost_utils import assertions
from ost_utils import engine_utils
from ost_utils import ssh
from ost_utils import utils
from ost_utils.pytest import order_by
from ost_utils.pytest.fixtures.ansible import *
from ost_utils.pytest.fixtures.engine import *
from ost_utils.pytest.fixtures.sdk import *
from ost_utils.pytest.fixtures.virt import *
from ost_utils.pytest.fixtures.vm import *

import ovirtsdk4 as sdk4
import ovirtsdk4.types as types

import test_utils
from test_utils import versioning
from test_utils import host_status_utils
from test_utils import constants

import uuid


KB = 2 ** 10
MB = 2 ** 20
GB = 2 ** 30

DC_NAME = 'test-dc'
TEST_CLUSTER = 'test-cluster'
TEMPLATE_CENTOS7 = 'centos7_template'

SD_NFS_NAME = 'nfs'
SD_SECOND_NFS_NAME = 'second-nfs'
SD_ISCSI_NAME = 'iscsi'

VM_USER_NAME = 'cirros'
VM_PASSWORD = 'gocubsgo'

VM0_NAME = 'vm0'
VM1_NAME = 'vm1'
VM2_NAME = 'vm2'
BACKUP_VM_NAME = 'backup_vm'
IMPORTED_VM_NAME = 'imported_vm'
OVF_VM_NAME = 'ovf_vm'
VMPOOL_NAME = 'test-pool'
DISK0_NAME = '%s_disk0' % VM0_NAME
DISK1_NAME = '%s_disk1' % VM1_NAME
DISK2_NAME = '%s_disk2' % VM2_NAME
FLOATING_DISK_NAME = 'floating_disk'
BACKUP_DISK_NAME = '%s_disk' % BACKUP_VM_NAME

SD_TEMPLATES_NAME = 'templates'

VM_NETWORK = u'VM Network with a very long name and עברית'

SNAPSHOT_DESC_1 = 'dead_snap1'
SNAPSHOT_DESC_2 = 'dead_snap2'
SNAPSHOT_FOR_BACKUP_VM = 'backup_snapshot'
SNAPSHOT_DESC_MEM = 'memory_snap'

VDSM_LOG = '/var/log/vdsm/vdsm.log'

OVA_VM_EXPORT_NAME = 'ova_vm.ova'
OVA_DIR = '/var/tmp'
IMPORTED_OVA_NAME = 'ova:///var/tmp/ova_vm.ova'
OVA_FILE_LOCATION = '%s/%s' % (OVA_DIR, OVA_VM_EXPORT_NAME)

_TEST_LIST = [
    "test_verify_add_all_hosts",
    "test_reconstruct_master_domain",
    "test_add_vm1_from_template",
    "test_verify_add_vm1_from_template",
    "test_add_disks",
    "test_add_floating_disk",
    "test_add_snapshot_for_backup",
    "test_run_vms",
    "test_attach_snapshot_to_backup_vm",
    "test_verify_transient_folder",
    "test_remove_backup_vm_and_backup_snapshot",
    "test_vm0_is_alive",
    "test_hotplug_memory",
    "test_suspend_resume_vm0",
    "test_extend_disk1",
    "test_sparsify_disk1",
    "test_export_vm1",
    "test_verify_backup_snapshot_removed",
    "test_verify_vm2_run",
    "test_incremental_backup_vm2",
    "test_ha_recovery",
    "test_verify_vm1_exported",
    "test_import_vm1",
    "test_template_export",
    "test_template_update",
    "test_verify_vm_import",
    "test_verify_suspend_resume_vm0",
    "test_hotunplug_memory",
    "test_hotplug_disk",
    "test_hotplug_nic",
    "test_hotplug_cpu",
    "test_next_run_unplug_cpu",
    "test_disk_operations",
    "test_live_storage_migration",
    "test_remove_vm2_lease",
    "test_hotunplug_disk",
    "test_make_snapshot_with_memory",
    "test_add_vm_pool",
    "test_preview_snapshot_with_memory",
    "test_update_template_version",
    "test_update_vm_pool",
    "test_remove_vm_pool",
    "test_check_snapshot_with_memory",
    "test_ovf_import",
    "test_vdsm_recovery",
]


@pytest.fixture(scope="session")
def vm_user():
    return VM_USER_NAME


@pytest.fixture(scope="session")
def vm_password():
    return VM_PASSWORD


@pytest.fixture(scope="session")
def vm_ssh(get_vm_ip, vm_user, vm_password):

    def run_ssh(vm_name_or_ip, command):
        if isinstance(command, str):
            command = command.split()
        return ssh.ssh(
            ip_addr=get_vm_ip(vm_name_or_ip),
            command=command,
            username=vm_user,
            password=vm_password,
        )

    return run_ssh


@order_by(_TEST_LIST)
def test_verify_add_all_hosts(engine_api):
    hosts_service = engine_api.system_service().hosts_service()
    total_hosts = len(hosts_service.list(search='datacenter={}'.format(DC_NAME)))

    assertions.assert_true_within(
        lambda: host_status_utils._all_hosts_up(hosts_service, total_hosts),
        timeout=constants.ADD_HOST_TIMEOUT
    )


def _verify_vm_state(engine, vm_name, state):
    vm_service = test_utils.get_vm_service(engine, vm_name)
    assertions.assert_true_within_long(
        lambda:
        vm_service.get().status == state
    )
    return vm_service


@pytest.fixture(scope="session")
def assert_vm_is_alive(ansible_host0, vm_ssh):

    def is_alive(vm_name):

        def _ping():
            ansible_host0.shell('ping -4 -c 1 -W 60 {}'.format(vm_name))
            return True

        assertions.assert_true_within_long(
            _ping, allowed_exceptions=[ansible.AnsibleExecutionError]
        )

        assert vm_ssh(vm_name, 'true').code == EX_OK

    return is_alive


@order_by(_TEST_LIST)
def test_add_disks(engine_api, cirros_image_glance_disk_name):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    glance_disk = test_utils.get_disk_service(
        engine,
        cirros_image_glance_disk_name,
    )
    assert vm_service and glance_disk

    vm0_disk_attachments_service = test_utils.get_disk_attachments_service(engine, VM0_NAME)

    vm0_disk_attachments_service.add(
        types.DiskAttachment(
            disk=types.Disk(
                id=glance_disk.get().id,
                storage_domains=[
                    types.StorageDomain(
                        name=SD_ISCSI_NAME,
                    ),
                ],
            ),
            interface=types.DiskInterface.VIRTIO,
            active=True,
            bootable=True,
        ),
    )

    disk_params = types.Disk(
        provisioned_size=1 * GB,
        format=types.DiskFormat.COW,
        status=None,
        sparse=True,
        active=True,
        bootable=True,
        backup=types.DiskBackup.INCREMENTAL,
    )

    for vm_name, disk_name, sd_name in (
            (VM1_NAME, DISK1_NAME, SD_NFS_NAME),
            (VM2_NAME, DISK2_NAME, SD_SECOND_NFS_NAME),
            (BACKUP_VM_NAME, BACKUP_DISK_NAME, SD_NFS_NAME)):
        disk_params.name = disk_name
        disk_params.storage_domains = [
            types.StorageDomain(
                name=sd_name,
            )
        ]

        disk_attachments_service = test_utils.get_disk_attachments_service(engine, vm_name)
        assert disk_attachments_service.add(types.DiskAttachment(
            disk=disk_params,
            interface=types.DiskInterface.VIRTIO))

    for disk_name in (cirros_image_glance_disk_name, DISK1_NAME, DISK2_NAME, BACKUP_DISK_NAME):
        disk_service = test_utils.get_disk_service(engine, disk_name)
        assertions.assert_true_within_short(
            lambda:
            disk_service.get().status == types.DiskStatus.OK
        )
    # USER_ADD_DISK_TO_VM_FINISHED_SUCCESS event
    # test_utils.test_for_event(engine, 97, last_event)


@order_by(_TEST_LIST)
def test_add_floating_disk(engine_api, disks_service):
    disks_service.add(
        types.Disk(
            name=FLOATING_DISK_NAME,
            format=types.DiskFormat.COW,
            provisioned_size=2 * MB,
            active=True,
            storage_domains=[
                types.StorageDomain(
                    name=SD_SECOND_NFS_NAME
                )
            ]
        )
    )

    engine = engine_api.system_service()
    disk_service = test_utils.get_disk_service(engine, FLOATING_DISK_NAME)
    assertions.assert_true_within_short(
        lambda:
        disk_service.get().status == types.DiskStatus.OK
    )


@order_by(_TEST_LIST)
def test_extend_disk1(engine_api):
    engine = engine_api.system_service()
    disk_attachments_service = test_utils.get_disk_attachments_service(engine, VM1_NAME)
    for disk_attachment in disk_attachments_service.list():
        disk = engine_api.follow_link(disk_attachment.disk)
        if disk.name == DISK1_NAME:
            attachment_service = disk_attachments_service.attachment_service(disk_attachment.id)
    with engine_utils.wait_for_event(engine, 371): # USER_EXTEND_DISK_SIZE_SUCCESS(371)
       attachment_service.update(
                types.DiskAttachment(
                    disk=types.Disk(provisioned_size=2 * GB,)))

       disk_service = test_utils.get_disk_service(engine, DISK1_NAME)
       assertions.assert_true_within_short(
           lambda:
           disk_service.get().status == types.DiskStatus.OK
       )
       assertions.assert_true_within_short(
           lambda:
           disk_service.get().provisioned_size == 2 * GB
       )


@order_by(_TEST_LIST)
def test_sparsify_disk1(engine_api):
    engine = engine_api.system_service()
    disk_service = test_utils.get_disk_service(engine, DISK1_NAME)
    with engine_utils.wait_for_event(engine, 1325): # USER_SPARSIFY_IMAGE_START event
        disk_service.sparsify()

    with engine_utils.wait_for_event(engine, 1326):  # USER_SPARSIFY_IMAGE_FINISH_SUCCESS
        pass
    # Make sure disk is unlocked
    assert disk_service.get().status == types.DiskStatus.OK


@order_by(_TEST_LIST)
def test_add_snapshot_for_backup(engine_api):
    engine = engine_api.system_service()

    vm2_disk_attachments_service = test_utils.get_disk_attachments_service(engine, VM2_NAME)
    disk = vm2_disk_attachments_service.list()[0]

    backup_snapshot_params = types.Snapshot(
        description=SNAPSHOT_FOR_BACKUP_VM,
        persist_memorystate=False,
        disk_attachments=[
            types.DiskAttachment(
                disk=types.Disk(
                    id=disk.id
                )
            )
        ]
    )

    vm2_snapshots_service = test_utils.get_vm_snapshots_service(engine, VM2_NAME)

    correlation_id = uuid.uuid4()
    with engine_utils.wait_for_event(engine, [45, 68]):
        # USER_CREATE_SNAPSHOT(41) event
        # USER_CREATE_SNAPSHOT_FINISHED_SUCCESS(68) event
        vm2_snapshots_service.add(backup_snapshot_params,
                                  query={'correlation_id': correlation_id})

        assertions.assert_true_within_long(
            lambda:
            test_utils.all_jobs_finished(engine, correlation_id)
        )
        assertions.assert_true_within_long(
            lambda:
            vm2_snapshots_service.list()[-1].snapshot_status == types.SnapshotStatus.OK,
        )


@order_by(_TEST_LIST)
def test_attach_snapshot_to_backup_vm(engine_api):
    engine = engine_api.system_service()
    vm2_snapshots_service = test_utils.get_vm_snapshots_service(engine, VM2_NAME)
    vm2_disk_attachments_service = test_utils.get_disk_attachments_service(engine, VM2_NAME)
    vm2_disk = vm2_disk_attachments_service.list()[0]
    disk_attachments_service = test_utils.get_disk_attachments_service(engine, BACKUP_VM_NAME)

    with engine_utils.wait_for_event(engine, 2016): # USER_ATTACH_DISK_TO_VM event
        disk_attachments_service.add(
            types.DiskAttachment(
                disk=types.Disk(
                    id=vm2_disk.id,
                    snapshot=types.Snapshot(
                        id=vm2_snapshots_service.list()[-1].id
                    )
                ),
                interface=types.DiskInterface.VIRTIO_SCSI,
                bootable=False,
                active=True
            )
        )
        assert len(disk_attachments_service.list()) > 0

@order_by(_TEST_LIST)
def test_verify_transient_folder(assert_vm_is_alive, engine_api,
                                 get_ansible_host_for_vm):
    engine = engine_api.system_service()
    sd = engine.storage_domains_service().list(search='name={}'.format(SD_SECOND_NFS_NAME))[0]
    ansible_host = get_ansible_host_for_vm(BACKUP_VM_NAME)
    out = ansible_host.shell('ls /var/lib/vdsm/transient')['stdout']

    all_volumes = out.strip().splitlines()
    assert len(all_volumes) == 1

    assert sd.id in all_volumes[0]
    assert_vm_is_alive(VM0_NAME)


@order_by(_TEST_LIST)
def test_remove_backup_vm_and_backup_snapshot(engine_api):
    engine = engine_api.system_service()
    backup_vm_service = test_utils.get_vm_service(engine, BACKUP_VM_NAME)
    vm2_snapshots_service = test_utils.get_vm_snapshots_service(engine, VM2_NAME)
    vm2_snapshot = vm2_snapshots_service.list()[-1]
    # power-off backup-vm
    with engine_utils.wait_for_event(engine, [33, 61]):
        # VM_DOWN(61) event
        # USER_STOP_VM(33) event
        backup_vm_service.stop()
        assertions.assert_true_within_long(
            lambda:
            backup_vm_service.get().status == types.VmStatus.DOWN
        )
    # remove backup_vm
    num_of_vms = len(engine.vms_service().list())
    backup_vm_service.remove()
    assert len(engine.vms_service().list()) == (num_of_vms-1)
    with engine_utils.wait_for_event(engine, 342): # USER_REMOVE_SNAPSHOT event
        # remove vm2 snapshot
        vm2_snapshots_service.snapshot_service(vm2_snapshot.id).remove()


@order_by(_TEST_LIST)
def test_verify_backup_snapshot_removed(engine_api):
    engine = engine_api.system_service()
    vm2_snapshots_service = test_utils.get_vm_snapshots_service(engine, VM2_NAME)

    assertions.assert_true_within_long(
        lambda: len(vm2_snapshots_service.list()) == 1
    )


def snapshot_cold_merge(engine_api):
    engine = engine_api.system_service()
    vm1_snapshots_service = test_utils.get_vm_snapshots_service(engine, VM1_NAME)
    if vm1_snapshots_service is None:
        pytest.skip('Glance is not available')

    disk = engine.disks_service().list(search='name={} and vm_names={}'.
                                       format(DISK1_NAME, VM1_NAME))[0]

    dead_snap1_params = types.Snapshot(
        description=SNAPSHOT_DESC_1,
        persist_memorystate=False,
        disk_attachments=[
            types.DiskAttachment(
                disk=types.Disk(
                    id=disk.id
                )
            )
        ]
    )
    correlation_id = uuid.uuid4()

    vm1_snapshots_service.add(dead_snap1_params,
                              query={'correlation_id': correlation_id})

    assertions.assert_true_within_long(
        lambda:
        test_utils.all_jobs_finished(engine, correlation_id)
    )
    assertions.assert_true_within_long(
        lambda:
        vm1_snapshots_service.list()[-1].snapshot_status == types.SnapshotStatus.OK
    )

    dead_snap2_params = types.Snapshot(
        description=SNAPSHOT_DESC_2,
        persist_memorystate=False,
        disk_attachments=[
            types.DiskAttachment(
                disk=types.Disk(
                    id=disk.id
                )
            )
        ]
    )
    correlation_id_snap2 = uuid.uuid4()

    vm1_snapshots_service.add(dead_snap2_params,
                              query={'correlation_id': correlation_id_snap2})

    assertions.assert_true_within_long(
        lambda:
        test_utils.all_jobs_finished(engine, correlation_id_snap2)
    )
    assertions.assert_true_within_long(
        lambda:
        vm1_snapshots_service.list()[-1].snapshot_status == types.SnapshotStatus.OK
    )

    snapshot = vm1_snapshots_service.list()[-2]
    vm1_snapshots_service.snapshot_service(snapshot.id).remove()

    assertions.assert_true_within_long(
        lambda:
        len(vm1_snapshots_service.list()) == 2
    )
    assertions.assert_true_within_long(
        lambda:
        vm1_snapshots_service.list()[-1].snapshot_status == types.SnapshotStatus.OK
    )


@order_by(_TEST_LIST)
def test_make_snapshot_with_memory(engine_api):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    disks_service = engine.disks_service()
    vm_disks_service = \
        test_utils.get_disk_attachments_service(engine, VM0_NAME)
    vm_disks = [disks_service.disk_service(attachment.disk.id).get()
                for attachment in vm_disks_service.list()]
    disk_attachments = [types.DiskAttachment(disk=types.Disk(id=disk.id))
                        for disk in vm_disks
                        if disk.storage_type != types.DiskStorageType.LUN]
    snapshots_service = vm_service.snapshots_service()
    snapshot_params = types.Snapshot(
        description=SNAPSHOT_DESC_MEM,
        persist_memorystate=True,
        disk_attachments=disk_attachments
    )
    with engine_utils.wait_for_event(engine, 45):  # USER_CREATE_SNAPSHOT event
        snapshots_service.add(snapshot_params)


@order_by(_TEST_LIST)
def test_preview_snapshot_with_memory(engine_api):
    engine = engine_api.system_service()
    events = engine.events_service()
    assertions.assert_true_within_long(
        # wait for event 68 == USER_CREATE_SNAPSHOT_FINISHED_SUCCESS
        lambda: any(e.code == 68 for e in events.list(max=6))
    )
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    vm_service.stop()
    _verify_vm_state(engine, VM0_NAME, types.VmStatus.DOWN)
    snapshot = test_utils.get_snapshot(engine, VM0_NAME, SNAPSHOT_DESC_MEM)
    vm_service.preview_snapshot(snapshot=snapshot, async=False,
                                restore_memory=True)


@order_by(_TEST_LIST)
def test_check_snapshot_with_memory(engine_api):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    assertions.assert_true_within_long(
        lambda: test_utils.get_snapshot(engine, VM0_NAME,
                                        SNAPSHOT_DESC_MEM).snapshot_status ==
        types.SnapshotStatus.IN_PREVIEW
    )
    vm_service.start()
    _verify_vm_state(engine, VM0_NAME, types.VmStatus.UP)


def cold_storage_migration(engine_api):
    engine = engine_api.system_service()
    disk_service = test_utils.get_disk_service(engine, DISK2_NAME)

    # Cold migrate the disk to ISCSI storage domain and then migrate it back
    # to the NFS domain because it is used by other cases that assume the
    # disk found on that specific domain
    for domain in [SD_ISCSI_NAME, SD_SECOND_NFS_NAME]:
        with engine_utils.wait_for_event(engine, 2008): # USER_MOVED_DISK(2,008)
            disk_service.move(
                async=False,
                storage_domain=types.StorageDomain(
                    name=domain
                )
            )

            assertions.assert_true_within_long(
                lambda: engine_api.follow_link(
                    disk_service.get().storage_domains[0]).name == domain
            )
            assertions.assert_true_within_long(
                lambda:
                disk_service.get().status == types.DiskStatus.OK
            )


@order_by(_TEST_LIST)
def test_live_storage_migration(engine_api):
    engine = engine_api.system_service()
    disk_service = test_utils.get_disk_service(engine, DISK0_NAME)
    correlation_id = 'live_storage_migration'
    disk_service.move(
        async=False,
        filter=False,
        storage_domain=types.StorageDomain(
            name=SD_ISCSI_NAME
        ),
        query={'correlation_id': correlation_id}
    )

    assertions.assert_true_within_long(lambda: test_utils.all_jobs_finished(engine, correlation_id))

    # Assert that the disk is on the correct storage domain,
    # its status is OK and the snapshot created for the migration
    # has been merged
    assertions.assert_true_within_long(
        lambda: engine_api.follow_link(disk_service.get().storage_domains[0]).name == SD_ISCSI_NAME
    )

    vm0_snapshots_service = test_utils.get_vm_snapshots_service(engine, VM0_NAME)
    assertions.assert_true_within_long(
        lambda: len(vm0_snapshots_service.list()) == 1
    )
    assertions.assert_true_within_long(
        lambda: disk_service.get().status == types.DiskStatus.OK
    )


@order_by(_TEST_LIST)
def test_export_vm1(engine_api):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM1_NAME)
    host = test_utils.get_first_active_host_by_name(engine)

    with engine_utils.wait_for_event(engine, 1223): # IMPORTEXPORT_STARTING_EXPORT_VM_TO_OVA event
        vm_service.export_to_path_on_host(
            host=types.Host(id=host.id),
            directory=OVA_DIR,
            filename=OVA_VM_EXPORT_NAME, async=True
        )


@order_by(_TEST_LIST)
def test_verify_vm1_exported(engine_api):
    engine = engine_api.system_service()
    vm1_snapshots_service = test_utils.get_vm_snapshots_service(engine, VM1_NAME)
    assertions.assert_true_within_long(
        lambda:
        len(vm1_snapshots_service.list()) == 1,
    )


@order_by(_TEST_LIST)
def test_import_vm1(engine_api):
    engine = engine_api.system_service()
    sd = engine.storage_domains_service().list(search='name={}'.format(SD_ISCSI_NAME))[0]
    cluster = engine.clusters_service().list(search='name={}'.format(TEST_CLUSTER))[0]
    imports_service = engine.external_vm_imports_service()
    host = test_utils.get_first_active_host_by_name(engine)
    correlation_id = "test_validate_ova_import_vm"

    with engine_utils.wait_for_event(engine, 1165): # IMPORTEXPORT_STARTING_IMPORT_VM
        imports_service.add(
            types.ExternalVmImport(
                name=IMPORTED_VM_NAME,
                provider=types.ExternalVmProviderType.KVM,
                url=IMPORTED_OVA_NAME,
                cluster=types.Cluster(
                    id=cluster.id
                ),
                storage_domain=types.StorageDomain(
                    id=sd.id
                ),
                host=types.Host(
                    id=host.id
                ),
                sparse=True
            ), async=True, query={'correlation_id': correlation_id}
        )


@order_by(_TEST_LIST)
def test_verify_vm_import(engine_api):
    engine = engine_api.system_service()
    correlation_id = "test_validate_ova_import_vm"
    assertions.assert_true_within_long(
        lambda:
        test_utils.all_jobs_finished(engine, correlation_id)
    )
    _verify_vm_state(engine, IMPORTED_VM_NAME, types.VmStatus.DOWN)


@order_by(_TEST_LIST)
def test_add_vm1_from_template(engine_api, cirros_image_glance_template_name):
    engine = engine_api.system_service()
    templates_service = engine.templates_service()
    glance_template = templates_service.list(
        search='name=%s' % cirros_image_glance_template_name
    )[0]
    if glance_template is None:
        pytest.skip('%s: template %s not available.' % (
            add_vm1_from_template.__name__, cirros_image_glance_template_name
        ))

    vm_memory = 128 * MB # runs with 64 ok, but we need to do a hotplug later (64+256 is too much difference)
    vms_service = engine.vms_service()
    vms_service.add(
        types.Vm(
            name=VM1_NAME,
            description='CirrOS imported from Glance as Template',
            memory= vm_memory,
            cluster=types.Cluster(
                name=TEST_CLUSTER,
            ),
            template=types.Template(
                name=cirros_image_glance_template_name,
            ),
            use_latest_template_version=True,
            stateless=True,
            display=types.Display(
                type=types.DisplayType.VNC,
            ),
            memory_policy=types.MemoryPolicy(
                guaranteed=vm_memory, # with so little memory we don't want guaranteed to be any lower
                ballooning=False,
            ),
            os=types.OperatingSystem(
                type='rhel_7x64', # even though it's CirrOS we want to check a non-default OS type
            ),
            time_zone=types.TimeZone(
                name='Etc/GMT',
            ),
            type=types.VmType.SERVER,
            serial_number=types.SerialNumber(
                policy=types.SerialNumberPolicy.CUSTOM,
                value='12345678',
            ),
            cpu=types.Cpu(
                architecture=types.Architecture.X86_64,
                topology=types.CpuTopology(
                    sockets=1,
                    cores=1,
                    threads=2,
                ),
            ),
        )
    )


@order_by(_TEST_LIST)
def test_verify_add_vm1_from_template(engine_api):
    engine = engine_api.system_service()
    _verify_vm_state(engine, VM1_NAME, types.VmStatus.DOWN)

    disks_service = engine.disks_service()
    vm1_disk_attachments_service = test_utils.get_disk_attachments_service(engine, VM1_NAME)
    for disk_attachment in vm1_disk_attachments_service.list():
        disk_service = disks_service.disk_service(disk_attachment.disk.id)
        assertions.assert_true_within_short(
            lambda:
            disk_service.get().status == types.DiskStatus.OK
        )


@pytest.fixture(scope="session")
def management_gw_ip(engine_ip):
    gw_ip = engine_ip.split('.')[:3] + ['1']
    return '.'.join(gw_ip)


@order_by(_TEST_LIST)
def test_run_vms(assert_vm_is_alive, engine_api, management_gw_ip):
    engine = engine_api.system_service()

    vm_params = types.Vm(
        initialization=types.Initialization(
            user_name=VM_USER_NAME,
            root_password=VM_PASSWORD
        )
    )

    vm_params.initialization.host_name = BACKUP_VM_NAME
    backup_vm_service = test_utils.get_vm_service(engine, BACKUP_VM_NAME)
    backup_vm_service.start(use_cloud_init=True, vm=vm_params)

    vm_params.initialization.host_name = VM2_NAME
    vm2_service = test_utils.get_vm_service(engine, VM2_NAME)
    vm2_service.start(use_cloud_init=True, vm=vm_params)

    # CirrOS cloud-init is different, networking doesn't work since it doesn't support the format oVirt is using
    vm_params.initialization.host_name = VM0_NAME # hostname seems to work, the others not
    vm_params.initialization.dns_search = 'lago.local'
    vm_params.initialization.domain = 'lago.local'
    vm_params.initialization.dns_servers = management_gw_ip
    vm0_service = test_utils.get_vm_service(engine, VM0_NAME)
    vm0_service.start(use_cloud_init=True, vm=vm_params)

    for vm_name in [VM0_NAME, BACKUP_VM_NAME]:
        _verify_vm_state(engine, vm_name, types.VmStatus.UP)

    assert_vm_is_alive(VM0_NAME)


@order_by(_TEST_LIST)
def test_verify_vm2_run(engine_api):
    _verify_vm_state(engine_api.system_service(), VM2_NAME, types.VmStatus.UP)


@order_by(_TEST_LIST)
def test_incremental_backup_vm2(engine_api):
    engine = engine_api.system_service()
    disks_service = engine.disks_service()
    disk2 = disks_service.list(search='name={}'.format(DISK2_NAME))[0]
    vm2_backups_service = test_utils.get_vm_service(engine, VM2_NAME).backups_service()
    created_checkpoint_id = None

    # The first iteration will be a full VM backup (from_checkpoint_id=None)
    # and the second iteration will be an incremental VM backup.
    for _ in range(2):
        correlation_id = 'test_incremental_backup'
        backup = vm2_backups_service.add(
            types.Backup(
                disks=[types.Disk(id=disk2.id)],
                from_checkpoint_id=created_checkpoint_id
            ), query={'correlation_id': correlation_id}
        )

        backup_service = vm2_backups_service.backup_service(backup.id)
        assertions.assert_true_within_long(
            lambda: backup_service.get().phase == types.BackupPhase.READY,
            allowed_exceptions=[sdk4.NotFoundError]
        )

        backup = backup_service.get()
        created_checkpoint_id = backup.to_checkpoint_id

        backup_service.finalize()

        assertions.assert_true_within_long(
            lambda: len(vm2_backups_service.list()) == 0
        )
        assertions.assert_true_within_long(
            lambda:
            disks_service.disk_service(disk2.id).get().status == types.DiskStatus.OK
        )


@order_by(_TEST_LIST)
def test_vm0_is_alive(assert_vm_is_alive):
    assert_vm_is_alive(VM0_NAME)


@order_by(_TEST_LIST)
def test_ha_recovery(engine_api, get_ansible_host_for_vm):
    engine = engine_api.system_service()
    with engine_utils.wait_for_event(engine, [119, 9602, 506]):
        # VM_DOWN_ERROR event(119)
        # HA_VM_FAILED event event(9602)
        # VDS_INITIATED_RUN_VM event(506)
        ansible_host = get_ansible_host_for_vm(VM2_NAME)
        pid = ansible_host.shell('pgrep -f qemu.*guest=vm2')['stdout'].strip()
        ansible_host.shell('kill -KILL {}'.format(pid))

    vm_service = test_utils.get_vm_service(engine, VM2_NAME)
    assertions.assert_true_within_long(
        lambda:
        vm_service.get().status == types.VmStatus.UP
    )
    with engine_utils.wait_for_event(engine, 33): # USER_STOP_VM event
        vm_service.stop()


@order_by(_TEST_LIST)
def test_vdsm_recovery(ansible_by_hostname, engine_api):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    host_id = vm_service.get().host.id
    host_service = engine.hosts_service().host_service(host_id)
    host_name = host_service.get().name
    ansible_host = ansible_by_hostname(host_name)

    ansible_host.systemd(name='vdsmd', state='stopped')
    assertions.assert_true_within_short(
        lambda:
        vm_service.get().status == types.VmStatus.UNKNOWN
    )

    ansible_host.systemd(name='vdsmd', state='started')
    assertions.assert_true_within_short(
        lambda:
        host_service.get().status == types.HostStatus.UP
    )
    assertions.assert_true_within_short(
        lambda:
        vm_service.get().status == types.VmStatus.UP
    )


@order_by(_TEST_LIST)
def test_template_export(engine_api, cirros_image_glance_template_name):
    engine = engine_api.system_service()

    template_guest = test_utils.get_template_service(
        engine, cirros_image_glance_template_name
    )
    if template_guest is None:
        pytest.skip('{0}: template {1} is missing'.format(
            template_export.__name__,
            cirros_image_glance_template_name
            )
        )

    storage_domain = engine.storage_domains_service().list(search='name={}'.format(SD_TEMPLATES_NAME))[0]
    with engine_utils.wait_for_event(engine, 1164):
        # IMPORTEXPORT_STARTING_EXPORT_TEMPLATE event
        template_guest.export(
            storage_domain=types.StorageDomain(
                id=storage_domain.id,
            ),
        )

    with engine_utils.wait_for_event(engine, 1156):
        # IMPORTEXPORT_EXPORT_TEMPLATE event
        assertions.assert_true_within_long(
            lambda:
            template_guest.get().status == types.TemplateStatus.OK,
        )


@order_by(_TEST_LIST)
def test_add_vm_pool(engine_api, cirros_image_glance_template_name):
    engine = engine_api.system_service()
    pools_service = engine.vm_pools_service()
    pool_cluster = engine.clusters_service().list(search='name={}'.format(TEST_CLUSTER))[0]
    pool_template = engine.templates_service().list(search='name={}'.format(
        cirros_image_glance_template_name
    ))[0]
    with engine_utils.wait_for_event(engine, 302):
        pools_service.add(
            pool=types.VmPool(
                name=VMPOOL_NAME,
                cluster=pool_cluster,
                template=pool_template,
                use_latest_template_version=True,
            )
        )
    vm_service = test_utils.get_vm_service(engine, VMPOOL_NAME+'-1')
    assertions.assert_true_within_short(
        lambda:
        vm_service.get().status == types.VmStatus.DOWN,
        allowed_exceptions=[IndexError]
    )


@order_by(_TEST_LIST)
def test_update_template_version(engine_api, cirros_image_glance_template_name):
    engine = engine_api.system_service()
    stateless_vm = engine.vms_service().list(search='name={}'.format(VM1_NAME))[0]
    templates_service = engine.templates_service()
    template = templates_service.list(search='name={}'.format(
        cirros_image_glance_template_name
    ))[0]

    assert stateless_vm.memory != template.memory

    templates_service.add(
        template=types.Template(
            name=cirros_image_glance_template_name,
            vm=stateless_vm,
            version=types.TemplateVersion(
                base_template=template,
                version_number=2
            )
        )
    )
    pool_service = test_utils.get_pool_service(engine, VMPOOL_NAME)
    assertions.assert_true_within_long(
        lambda:
        pool_service.get().vm.memory == stateless_vm.memory
    )


@order_by(_TEST_LIST)
def test_update_vm_pool(engine_api):
    engine = engine_api.system_service()
    pool_service = test_utils.get_pool_service(engine, VMPOOL_NAME)
    correlation_id = uuid.uuid4()
    pool_service.update(
        pool=types.VmPool(
            max_user_vms=2
        ),
        query={'correlation_id': correlation_id}
    )
    assert pool_service.get().max_user_vms == 2
    assertions.assert_true_within_long(
        lambda:
        test_utils.all_jobs_finished(engine, correlation_id)
    )


@versioning.require_version(4, 1)
@order_by(_TEST_LIST)
def test_remove_vm2_lease(engine_api):
    engine = engine_api.system_service()
    vm2_service = test_utils.get_vm_service(engine, VM2_NAME)

    vm2_service.update(
        vm=types.Vm(
            high_availability=types.HighAvailability(
                enabled=False,
            ),
            lease=types.StorageDomainLease(
                storage_domain=None
            )
        )
    )
    assertions.assert_true_within_short(
        lambda:
        vm2_service.get().lease is None
    )


@order_by(_TEST_LIST)
def test_remove_vm_pool(engine_api):
    engine = engine_api.system_service()
    pool_service = test_utils.get_pool_service(engine, VMPOOL_NAME)
    correlation_id = uuid.uuid4()
    with engine_utils.wait_for_event(engine, [321, 304]):
        # USER_REMOVE_VM_POOL_INITIATED(321) event
        # USER_REMOVE_VM_POOL(304) event
        pool_service.remove(query={'correlation_id': correlation_id})
        vm_pools_service = engine_api.system_service().vm_pools_service()
        assert len(vm_pools_service.list()) == 0
    assertions.assert_true_within_long(
        lambda:
        test_utils.all_jobs_finished(engine, correlation_id)
    )


@order_by(_TEST_LIST)
def test_template_update(engine_api, cirros_image_glance_template_name):
    template_guest = test_utils.get_template_service(
        engine_api.system_service(), cirros_image_glance_template_name
    )

    if template_guest is None:
        pytest.skip('{0}: template {1} is missing'.format(
            template_update.__name__,
            cirros_image_glance_template_name
        )
    )
    new_comment = "comment by ovirt-system-tests"
    template_guest.update(
        template = types.Template(
            comment=new_comment
        )
    )
    assertions.assert_true_within_short(
        lambda:
        template_guest.get().status == types.TemplateStatus.OK
    )
    assert template_guest.get().comment == new_comment


@order_by(_TEST_LIST)
def test_disk_operations(engine_api):
    vt = utils.VectorThread(
        [
            functools.partial(cold_storage_migration, engine_api),
            functools.partial(snapshot_cold_merge, engine_api),
        ],
    )
    vt.start_all()
    vt.join_all()


@pytest.fixture(scope="session")
def hotplug_mem_amount():
    return 256 * MB


@pytest.fixture(scope="session")
def get_vm_libvirt_memory_amount(get_vm_libvirt_xml):

    def mem_amount(vm_name):
        xml = get_vm_libvirt_xml(vm_name)
        match = re.search(r'<currentMemory unit=\'KiB\'>(?P<mem>[0-9]+)', xml)
        return int(match.group('mem'))

    return mem_amount


@order_by(_TEST_LIST)
def test_hotplug_memory(assert_vm_is_alive, engine_api,
                        get_vm_libvirt_memory_amount, hotplug_mem_amount):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    new_memory = vm_service.get().memory + hotplug_mem_amount
    with engine_utils.wait_for_event(engine, 2039): # HOT_SET_MEMORY(2,039)
        vm_service.update(
            vm=types.Vm(
                memory=new_memory,
                # Need to avoid OOM scenario where ballooning would immediately try to claim some memory.
                # CirrOS is lacking memory onlining rules so the guest memory doesn't really increase and
                # balloon inflation just crashes the guest instead. Balloon gets inflated because MOM
                # does not know that guest size didn't increase and just assumes it did, and the host
                # OST VM is likely under memory pressure, there's not much free RAM in OST environment.
                # Setting minimum guaranteed to new memory size keeps MOM from inflating balloon.
                memory_policy=types.MemoryPolicy(
                    guaranteed=new_memory,
                )
            )
        )
        assert vm_service.get().memory == new_memory

    assert_vm_is_alive(VM0_NAME)
    assert get_vm_libvirt_memory_amount(VM0_NAME) // KB == new_memory // MB


@order_by(_TEST_LIST)
def test_hotunplug_memory(assert_vm_is_alive, engine_api,
                          get_vm_libvirt_memory_amount, hotplug_mem_amount):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    new_memory = vm_service.get().memory - hotplug_mem_amount
    with engine_utils.wait_for_event(engine, 2046): # MEMORY_HOT_UNPLUG_SUCCESSFULLY_REQUESTED(2,046)
        vm_service.update(
            vm=types.Vm(
                memory=new_memory,
                memory_policy=types.MemoryPolicy(
                    guaranteed=new_memory,
                )
            )
        )
        assert vm_service.get().memory == new_memory

    assert_vm_is_alive(VM0_NAME)
    assert get_vm_libvirt_memory_amount(VM0_NAME) // KB == new_memory // MB


@order_by(_TEST_LIST)
def test_hotplug_cpu(engine_api, vm_ssh):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    new_cpu = vm_service.get().cpu
    new_cpu.topology.sockets = 2
    with engine_utils.wait_for_event(engine, 2033): # HOT_SET_NUMBER_OF_CPUS(2,033)
        vm_service.update(
            vm=types.Vm(
                cpu=new_cpu
            )
        )
        assert vm_service.get().cpu.topology.sockets == 2
    ret = vm_ssh(VM0_NAME, 'lscpu')
    assert ret.code == 0
    match = re.search(r'CPU\(s\):\s+(?P<cpus>[0-9]+)', ret.out.decode('utf-8'))
    assert match.group('cpus') == '2'


@order_by(_TEST_LIST)
def test_next_run_unplug_cpu(engine_api):
    engine = engine_api.system_service()
    vm_service = test_utils.get_vm_service(engine, VM0_NAME)
    new_cpu = vm_service.get().cpu
    new_cpu.topology.sockets = 1
    vm_service.update(
        vm=types.Vm(
            cpu=new_cpu,
        ),
        next_run=True
    )
    assert vm_service.get().cpu.topology.sockets == 2
    assert vm_service.get(next_run=True).cpu.topology.sockets == 1

    with engine_utils.wait_for_event(engine, 157): # USER_REBOOT_VM(157)
        vm_service.reboot()
        assertions.assert_true_within_long(
            lambda:
             vm_service.get().status == types.VmStatus.UP
        )
    assert vm_service.get().cpu.topology.sockets == 1


@order_by(_TEST_LIST)
def test_hotplug_nic(assert_vm_is_alive, engine_api):
    vms_service = engine_api.system_service().vms_service()
    vm = vms_service.list(search='name=%s' % VM0_NAME)[0]
    nics_service = vms_service.vm_service(vm.id).nics_service()
    nics_service.add(
        types.Nic(
            name='eth1',
            interface=types.NicInterface.VIRTIO
        ),
    )
    assert_vm_is_alive(VM0_NAME)


@order_by(_TEST_LIST)
def test_hotplug_disk(assert_vm_is_alive, engine_api):
    engine = engine_api.system_service()
    disk_attachments_service = test_utils.get_disk_attachments_service(engine, VM0_NAME)
    disk_attachment = disk_attachments_service.add(
        types.DiskAttachment(
            disk=types.Disk(
                name=DISK0_NAME,
                provisioned_size=2 * GB,
                format=types.DiskFormat.COW,
                storage_domains=[
                    types.StorageDomain(
                        name=SD_NFS_NAME,
                    ),
                ],
                status=None,
                sparse=True,
            ),
            interface=types.DiskInterface.VIRTIO,
            bootable=False,
            active=True
        )
    )

    disks_service = engine.disks_service()
    disk_service = disks_service.disk_service(disk_attachment.disk.id)
    attachment_service = disk_attachments_service.attachment_service(disk_attachment.id)

    assertions.assert_true_within_short(
        lambda:
        attachment_service.get().active == True
    )
    assertions.assert_true_within_short(
        lambda:
        disk_service.get().status == types.DiskStatus.OK
    )
    assert_vm_is_alive(VM0_NAME)


@order_by(_TEST_LIST)
def test_hotunplug_disk(engine_api):
    engine = engine_api.system_service()
    disk_service = test_utils.get_disk_service(engine, DISK0_NAME)
    disk_attachments_service = test_utils.get_disk_attachments_service(engine, VM0_NAME)
    disk_attachment = disk_attachments_service.attachment_service(disk_service.get().id)

    with engine_utils.wait_for_event(engine, 2002):
        # USER_HOTUNPLUG_DISK(2,002)
        correlation_id = 'test_hotunplug_disk'
        assert disk_attachment.update(types.DiskAttachment(active=False),
                                      query={'correlation_id': correlation_id})
        assertions.assert_true_within_long(
            lambda:
            test_utils.all_jobs_finished(engine, correlation_id)
        )

        assertions.assert_true_within_short(
            lambda:
            disk_service.get().status == types.DiskStatus.OK
        )

        assertions.assert_true_within_short(
            lambda:
            disk_attachment.get().active == False
        )


@order_by(_TEST_LIST)
def test_suspend_resume_vm0(assert_vm_is_alive, engine_api, vm_ssh):
    # start a background job we are going to check if it's still running later
    ret = vm_ssh(VM0_NAME, 'sleep 3600 &')
    assert ret.code == EX_OK

    assert_vm_is_alive(VM0_NAME)

    vm_service = test_utils.get_vm_service(engine_api.system_service(), VM0_NAME)
    vm_service.suspend()
    assertions.assert_true_within_long(
        lambda: vm_service.get().status == types.VmStatus.SUSPENDED
    )

    vm_service.start()


@order_by(_TEST_LIST)
def test_verify_suspend_resume_vm0(engine_api, vm_ssh):
    _verify_vm_state(engine_api.system_service(), VM0_NAME, types.VmStatus.UP)
    ret = vm_ssh(VM0_NAME, 'pidof sleep')
    assert ret.code == EX_OK


@order_by(_TEST_LIST)
def test_reconstruct_master_domain(engine_api):
    pytest.skip('TODO:Handle case where tasks are running')
    system_service = engine_api.system_service()
    dc_service = test_utils.data_center_service(system_service, DC_NAME)
    attached_sds_service = dc_service.storage_domains_service()
    master_sd = next(sd for sd in attached_sds_service.list() if sd.master)
    attached_sd_service = attached_sds_service.storage_domain_service(master_sd.id)
    attached_sd_service.deactivate()
    assertions.assert_true_within_long(
        lambda: attached_sd_service.get().status ==
                types.StorageDomainStatus.MAINTENANCE
        )
    new_master_sd = next(sd for sd in attached_sds_service.list() if sd.master)
    assert new_master_sd.id != master_sd.id
    attached_sd_service.activate()
    assertions.assert_true_within_long(
        lambda: attached_sd_service.get().status ==
                types.StorageDomainStatus.ACTIVE
        )


@order_by(_TEST_LIST)
def test_ovf_import(engine_api):
    # Read the OVF file and replace the disk id
    engine = engine_api.system_service()
    disk_service = test_utils.get_disk_service(engine, DISK0_NAME)
    disk_id = disk_service.get().id
    ovf_file = os.path.join(os.environ['SUITE'], 'files', 'test-vm.ovf')
    ovf_text = open(ovf_file).read()
    ovf_text = ovf_text.replace(
        "ovf:diskId='52df5324-2230-40d9-9d3d-8cbb2aa33ba6'",
        "ovf:diskId='%s'" % (disk_id,)
    )
    # Upload OVF
    vms_service = engine.vms_service()
    vms_service.add(
        types.Vm(
            name=OVF_VM_NAME,
            cluster=types.Cluster(
                name=TEST_CLUSTER,
            ),
            initialization=types.Initialization(
                configuration=types.Configuration(
                    type=types.ConfigurationType.OVA,
                    data=ovf_text
                )
            )
        )
    )
    # Check the VM exists
    assert test_utils.get_vm_service(engine, OVF_VM_NAME) is not None
