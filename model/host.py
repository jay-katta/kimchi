#
# Project Kimchi
#
# Copyright IBM Corp, 2015-2016
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA

import libvirt
import os
from collections import defaultdict
from lxml import objectify

from wok.exception import InvalidParameter
from wok.exception import NotFoundError
from wok.xmlutils.utils import xpath_get_text

from wok.plugins.gingerbase import disks
from wok.plugins.kimchi.model import hostdev
from wok.plugins.kimchi.model.config import CapabilitiesModel
from wok.plugins.kimchi.model.vms import VMModel, VMsModel


class DevicesModel(object):
    def __init__(self, **kargs):
        self.conn = kargs['conn']
        self.caps = CapabilitiesModel(**kargs)
        self.cap_map = \
            {'net': libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_NET,
             'pci': libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_PCI_DEV,
             'scsi': libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_SCSI,
             'scsi_host': libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_SCSI_HOST,
             'storage': libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_STORAGE,
             'usb_device': libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_USB_DEV,
             'usb':
             libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_USB_INTERFACE}
        # TODO: when no longer supporting Libvirt < 1.0.5 distros
        # (like RHEL6) remove this verification and insert the
        # key 'fc_host' with the libvirt variable in the hash
        # declaration above.
        try:
            self.cap_map['fc_host'] = \
                libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_FC_HOST
        except AttributeError:
            self.cap_map['fc_host'] = None

    def _get_unavailable_devices(self):
        vm_list = VMsModel.get_vms(self.conn)
        unavailable_devs = []
        for vm in vm_list:
            dom = VMModel.get_vm(vm, self.conn)
            xmlstr = dom.XMLDesc(0)
            root = objectify.fromstring(xmlstr)
            try:
                hostDevices = root.devices.hostdev
            except AttributeError:
                continue

            vm_devs = [DeviceModel.deduce_dev_name(e, self.conn)
                       for e in hostDevices]

            for dev in vm_devs:
                unavailable_devs.append(dev)

        return unavailable_devs

    def get_list(self, _cap=None, _passthrough=None,
                 _passthrough_affected_by=None,
                 _available_only=None):
        if _passthrough_affected_by is not None:
            # _passthrough_affected_by conflicts with _cap and _passthrough
            if (_cap, _passthrough) != (None, None):
                raise InvalidParameter("KCHHOST0004E")
            return sorted(
                self._get_passthrough_affected_devs(_passthrough_affected_by))

        if _cap == 'fc_host':
            dev_names = self._get_devices_fc_host()
        else:
            dev_names = self._get_devices_with_capability(_cap)

        if _passthrough is not None and _passthrough.lower() == 'true':
            conn = self.conn.get()
            passthrough_names = [
                dev['name'] for dev in hostdev.get_passthrough_dev_infos(conn)]

            dev_names = list(set(dev_names) & set(passthrough_names))

            if _available_only is not None and _available_only.lower() \
                    == 'true':
                unavailable_devs = self._get_unavailable_devices()
                dev_names = [dev for dev in dev_names
                             if dev not in unavailable_devs]

        dev_names.sort()
        return dev_names

    def _get_devices_with_capability(self, cap):
        conn = self.conn.get()
        if cap is None:
            cap_flag = 0
        else:
            cap_flag = self.cap_map.get(cap)
            if cap_flag is None:
                return []
        return [name.name() for name in conn.listAllDevices(cap_flag)]

    def _get_passthrough_affected_devs(self, dev_name):
        conn = self.conn.get()
        info = DeviceModel(conn=self.conn).lookup(dev_name)
        affected = hostdev.get_affected_passthrough_devices(conn, info)
        return [dev_info['name'] for dev_info in affected]

    def _get_devices_fc_host(self):
        conn = self.conn.get()
        # Libvirt < 1.0.5 does not support fc_host capability
        if not self.caps.fc_host_support:
            ret = []
            scsi_hosts = self._get_devices_with_capability('scsi_host')
            for host in scsi_hosts:
                xml = conn.nodeDeviceLookupByName(host).XMLDesc(0)
                path = '/device/capability/capability/@type'
                if 'fc_host' in xpath_get_text(xml, path):
                    ret.append(host)
            return ret
        # Double verification to catch the case where the libvirt
        # supports fc_host but does not, for some reason, recognize
        # the libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_FC_HOST
        # attribute.
        if not self.cap_map['fc_host']:
            return conn.listDevices('fc_host', 0)
        return self._get_devices_with_capability('fc_host')


class DeviceModel(object):
    def __init__(self, **kargs):
        self.conn = kargs['conn']
        self.iommu_groups = self._get_iommu_groups()

    def _get_iommu_groups(self):
        iommu_groups = defaultdict(list)
        conn = self.conn

        try:
            devices = DevicesModel(conn=conn).get_list()

        except:
            return iommu_groups

        for device in devices:
            info = hostdev.get_dev_info(
                conn.get().nodeDeviceLookupByName(device))
            if 'iommuGroup' not in info:
                continue
            iommu_group_nr = int(info['iommuGroup'])
            iommu_groups[iommu_group_nr].append(device)

        return iommu_groups

    def lookup(self, nodedev_name):
        conn = self.conn.get()
        try:
            dev = conn.nodeDeviceLookupByName(nodedev_name)
        except:
            raise NotFoundError('KCHHOST0003E', {'name': nodedev_name})

        info = hostdev.get_dev_info(dev)
        info['multifunction'] = self.is_multifunction_pci(info)
        info['vga3d'] = self.is_device_3D_controller(info)
        return info

    def is_multifunction_pci(self, info):
        if 'iommuGroup' not in info:
            return False
        iommu_group_nr = int(info['iommuGroup'])
        return len(self.iommu_groups[iommu_group_nr]) > 1

    def is_device_3D_controller(self, info):
        try:
            with open(os.path.join(info['path'], 'class')) as f:
                pci_class = int(f.readline().strip(), 16)

        except:
            return False

        if pci_class == 0x030200:
            return True

        return False

    @staticmethod
    def _toint(num_str):
        if num_str.startswith('0x'):
            return int(num_str, 16)
        elif num_str.startswith('0'):
            return int(num_str, 8)
        else:
            return int(num_str)

    @staticmethod
    def deduce_dev_name(e, conn):
        if e.attrib['type'] == 'pci':
            return DeviceModel._deduce_dev_name_pci(e)
        elif e.attrib['type'] == 'scsi':
            return DeviceModel._deduce_dev_name_scsi(e)
        elif e.attrib['type'] == 'usb':
            return DeviceModel._deduce_dev_name_usb(e, conn)
        return None

    @staticmethod
    def _deduce_dev_name_pci(e):
        attrib = {}
        for field in ('domain', 'bus', 'slot', 'function'):
            attrib[field] = DeviceModel._toint(e.source.address.attrib[field])
        return 'pci_%(domain)04x_%(bus)02x_%(slot)02x_%(function)x' % attrib

    @staticmethod
    def _deduce_dev_name_scsi(e):
        attrib = {}
        for field in ('bus', 'target', 'unit'):
            attrib[field] = DeviceModel._toint(e.source.address.attrib[field])
        attrib['host'] = DeviceModel._toint(
            e.source.adapter.attrib['name'][len('scsi_host'):])
        return 'scsi_%(host)d_%(bus)d_%(target)d_%(unit)d' % attrib

    @staticmethod
    def _deduce_dev_name_usb(e, conn):
        dev_names = DevicesModel(conn=conn).get_list(_cap='usb_device')
        usb_infos = [DeviceModel(conn=conn).lookup(dev_name)
                     for dev_name in dev_names]

        unknown_dev = None

        try:
            evendor = DeviceModel._toint(e.source.vendor.attrib['id'])
            eproduct = DeviceModel._toint(e.source.product.attrib['id'])
        except AttributeError:
            evendor = 0
            eproduct = 0
        else:
            unknown_dev = 'usb_vendor_%s_product_%s' % (evendor, eproduct)

        try:
            ebus = DeviceModel._toint(e.source.address.attrib['bus'])
            edevice = DeviceModel._toint(e.source.address.attrib['device'])
        except AttributeError:
            ebus = -1
            edevice = -1
        else:
            unknown_dev = 'usb_bus_%s_device_%s' % (ebus, edevice)

        for usb_info in usb_infos:
            ivendor = DeviceModel._toint(usb_info['vendor']['id'])
            iproduct = DeviceModel._toint(usb_info['product']['id'])
            if evendor == ivendor and eproduct == iproduct:
                return usb_info['name']
            ibus = usb_info['bus']
            idevice = usb_info['device']
            if ebus == ibus and edevice == idevice:
                return usb_info['name']
        return unknown_dev


class PartitionsModel(object):
    def __init__(self, **kargs):
        pass

    def get_list(self):
        result = disks.get_partitions_names()
        return result


class PartitionModel(object):
    def __init__(self, **kargs):
        pass

    def lookup(self, name):
        return disks.get_partition_details(name)


class VolumeGroupsModel(object):
    def __init__(self, **kargs):
        pass

    def get_list(self):
        return [vg['vgname'] for vg in disks.vgs()]


class VolumeGroupModel(object):
    def __init__(self, **kargs):
        pass

    def lookup(self, name):
        def _format(vg):
            return {'name': vg['vgname'],
                    'size': vg['size'],
                    'free': vg['free'],
                    'pvs': [pv['pvname'] for pv in disks.pvs(vg['vgname'])],
                    'lvs': [lv['lvname'] for lv in disks.lvs(vg['vgname'])]}

        vgs = [_format(vg) for vg in disks.vgs() if vg['vgname'] == name]
        if not vgs:
            raise InvalidParameter("KCHLVMS0001E", {'name': name})

        return vgs[0]
