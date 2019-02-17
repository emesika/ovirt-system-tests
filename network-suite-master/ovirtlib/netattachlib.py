# Copyright 2019 Red Hat, Inc.
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

from ovirtsdk4 import types


class IpVersion(object):

    V4 = types.IpVersion.V4
    V6 = types.IpVersion.V6


DYNAMIC_IP_CONFIG = [
    types.IpAddressAssignment(assignment_method=types.BootProtocol.DHCP),
    types.IpAddressAssignment(assignment_method=types.BootProtocol.DHCP,
                              ip=types.Ip(version=IpVersion.V6))
]


class NetworkAttachmentData(object):

    def __init__(self, network, nic_name, ip_configuration=None):
        self._network = network
        self._nic_name = nic_name
        self._ip_configuration = ip_configuration

    @property
    def network(self):
        return self._network

    @property
    def nic_name(self):
        return self._nic_name

    @property
    def ip_configuration(self):
        return self._ip_configuration


def create_static_ip_config_assignment(addr, mask, gateway=None,
                                       version=IpVersion.V4):
    ip = types.Ip(address=addr, netmask=mask,
                  version=version, gateway=gateway)
    return types.IpAddressAssignment(
        assignment_method=types.BootProtocol.STATIC, ip=ip)
