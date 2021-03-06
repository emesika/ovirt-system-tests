#
# Copyright 2016-2019 Red Hat, Inc.
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

import time

import functools
import nose.tools as nt
from ovirtsdk4.types import DataCenter, Network, NetworkLabel, Vlan

from lago import utils
from ovirtlago import testlib
import test_utils
from test_utils import ipv6_utils, network_utils_v4

# DC/Cluster
DC_NAME = 'Default'
CLUSTER_NAME = 'Default'

# Network
NETWORK_LABEL = 'NETWORK_LABEL'
LABELED_NET_NAME = 'Labeled_Network'
LABELED_NET_VLAN_ID = 600


def _host_is_attached_to_network(engine, host, network_name):
    try:
        attachment = network_utils_v4.get_network_attachment(
            engine, host, network_name, DC_NAME)
    except StopIteration:  # there is no attachment of the network to the host
        return False

    # 'return attachment' cannot be used because assert_true_within_short
    # seems to require True and not just a bool(value) that evaluates as True
    return True


def setup_module():
    ipv6_utils.open_connection_to_api_with_ipv6_on_relevant_suite()


@testlib.with_ovirt_api4
def _hosts_in_cluster(api, cluster_name):
    hosts_service = api.system_service().hosts_service()
    return hosts_service.list(search='cluster={}'.format(cluster_name))


@testlib.with_ovirt_api4
def assign_hosts_network_label(api):
    """
    Assigns NETWORK_LABEL to first network interface of every host in cluster
    """
    engine = api.system_service()

    def _assign_host_network_label(host):
        host_service = engine.hosts_service().host_service(id=host.id)
        nics_service = host_service.nics_service()
        nics = sorted(nics_service.list(),
                      key=lambda n: n.name)
        nt.assert_greater_equal(len(nics), 1)
        nic = nics[0]
        nic_service = nics_service.nic_service(id=nic.id)
        labels_service = nic_service.network_labels_service()
        return labels_service.add(
                NetworkLabel(
                    id=NETWORK_LABEL,
                    host_nic=nic
                )
            )

    hosts = test_utils.hosts_in_cluster_v4(engine, CLUSTER_NAME)
    vec = utils.func_vector(_assign_host_network_label, [(h,) for h in hosts])
    vt = utils.VectorThread(vec)
    vt.start_all()
    nt.assert_true(all(vt.join_all()))


@testlib.with_ovirt_api4
def add_labeled_network(api):
    """
    Creates a labeled network
    """
    # create network
    labeled_net = Network(
        name=LABELED_NET_NAME,
        data_center=DataCenter(
            name=DC_NAME,
        ),
        description='Labeled network on VLAN {}'.format(LABELED_NET_VLAN_ID),
        usages=[],
        # because only one non-VLAN network, here 'ovirtmgmt', can be assigned
        # to each nic, this additional network has to be a VLAN network
        # NOTE: we have added three more NICs since creating this test
        vlan=Vlan(
            id=LABELED_NET_VLAN_ID,
        ),
    )
    networks_service = api.system_service().networks_service()
    net = networks_service.add(labeled_net)
    nt.assert_true(net)

    network_service = networks_service.network_service(id=net.id)
    labels_service = network_service.network_labels_service()

    # assign label to the network
    nt.assert_true(
        labels_service.add(
            NetworkLabel(
                id=NETWORK_LABEL
            )
        )
    )
    nt.assert_equal(
        len(list(label for label in labels_service.list()
                 if label.id == NETWORK_LABEL)),
        1
    )


@testlib.with_ovirt_api4
def assign_labeled_network(api):
    """
    Adds the labeled network to the cluster and asserts the hosts are attached
    """
    engine = api.system_service()

    labeled_net = engine.networks_service().list(
        search='name={}'.format(LABELED_NET_NAME))[0]

    # the logical network will be automatically assigned to all host network
    # interfaces with that label asynchronously

    cluster_service = test_utils.get_cluster_service(engine, CLUSTER_NAME)
    nt.assert_true(
        cluster_service.networks_service().add(labeled_net)
    )

    hosts_service = engine.hosts_service()
    for host in test_utils.hosts_in_cluster_v4(engine, CLUSTER_NAME):
        host_service = hosts_service.host_service(id=host.id)
        testlib.assert_true_within_short(
            functools.partial(_host_is_attached_to_network, engine,
                              host_service, LABELED_NET_NAME))


_TEST_LIST = [
    assign_hosts_network_label,
    add_labeled_network,
    assign_labeled_network,
]


def test_gen():
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t
