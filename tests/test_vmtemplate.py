#
# Project Kimchi
#
# Copyright IBM, Corp. 2013-2015
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

import os
import psutil
import unittest
import uuid

from wok.xmlutils.utils import xpath_get_text

from wok.plugins.kimchi.osinfo import get_template_default
from wok.plugins.kimchi.vmtemplate import VMTemplate

DISKS = [{'size': 10, 'format': 'raw', 'index': 0, 'pool': {'name':
          '/plugins/kimchi/storagepools/default-pool'}},
         {'size': 5, 'format': 'qcow2', 'index': 1, 'pool': {'name':
          '/plugins/kimchi/storagepools/default-pool'}}]


class VMTemplateTests(unittest.TestCase):
    def setUp(self):
        self.iso = '/tmp/mock.iso'
        open(self.iso, 'w').close()

    def tearDown(self):
        os.unlink(self.iso)

    def test_minimal_construct(self):
        disk_bus = get_template_default('old', 'disk_bus')
        memory = get_template_default('old', 'memory')
        nic_model = get_template_default('old', 'nic_model')
        fields = (('name', 'test'), ('os_distro', 'unknown'),
                  ('os_version', 'unknown'), ('cpus', 1),
                  ('memory', memory), ('networks', ['default']),
                  ('disk_bus', disk_bus), ('nic_model', nic_model),
                  ('graphics', {'type': 'vnc', 'listen': '127.0.0.1'}),
                  ('cdrom', self.iso))

        args = {'name': 'test', 'cdrom': self.iso}
        t = VMTemplate(args)
        for name, val in fields:
            self.assertEquals(val, t.info.get(name))

    def test_construct_overrides(self):
        graphics = {'type': 'spice', 'listen': '127.0.0.1'}
        args = {'name': 'test', 'disks': DISKS,
                'graphics': graphics, "cdrom": self.iso}
        t = VMTemplate(args)
        self.assertEquals(2, len(t.info['disks']))
        self.assertEquals(graphics, t.info['graphics'])

    def test_specified_graphics(self):
        # Test specified listen
        graphics = {'type': 'vnc', 'listen': '127.0.0.1'}
        args = {'name': 'test', 'disks': DISKS,
                'graphics': graphics, 'cdrom': self.iso}
        t = VMTemplate(args)
        self.assertEquals(graphics, t.info['graphics'])

        # Test specified type
        graphics = {'type': 'spice', 'listen': '127.0.0.1'}
        args['graphics'] = graphics
        t = VMTemplate(args)
        self.assertEquals(graphics, t.info['graphics'])

        # If no listen specified, test the default listen
        graphics = {'type': 'vnc'}
        args['graphics'] = graphics
        t = VMTemplate(args)
        self.assertEquals(graphics['type'], t.info['graphics']['type'])
        self.assertEquals('127.0.0.1', t.info['graphics']['listen'])

    def test_to_xml(self):
        graphics = {'type': 'spice', 'listen': '127.0.0.1'}
        vm_uuid = str(uuid.uuid4()).replace('-', '')
        t = VMTemplate({'name': 'test-template', 'cdrom': self.iso})
        xml = t.to_vm_xml('test-vm', vm_uuid, graphics=graphics)
        self.assertEquals(vm_uuid, xpath_get_text(xml, "/domain/uuid")[0])
        self.assertEquals('test-vm', xpath_get_text(xml, "/domain/name")[0])
        expr = "/domain/devices/graphics/@type"
        self.assertEquals(graphics['type'], xpath_get_text(xml, expr)[0])
        expr = "/domain/devices/graphics/@listen"
        self.assertEquals(graphics['listen'], xpath_get_text(xml, expr)[0])
        expr = "/domain/maxMemory/@slots"
        self.assertEquals('3', xpath_get_text(xml, expr)[0])
        expr = "/domain/maxMemory"
        self.assertEquals(str((1024 * 4) << 10), xpath_get_text(xml, expr)[0])

        if hasattr(psutil, 'virtual_memory'):
            host_memory = psutil.virtual_memory().total >> 10
        else:
            host_memory = psutil.TOTAL_PHYMEM >> 10
        t = VMTemplate({'name': 'test-template', 'cdrom': self.iso,
                        'memory': (host_memory >> 10) - 512})
        xml = t.to_vm_xml('test-vm', vm_uuid, graphics=graphics)
        expr = "/domain/maxMemory"
        self.assertEquals(str(host_memory), xpath_get_text(xml, expr)[0])
        expr = "/domain/maxMemory/@slots"
        self.assertEquals('1', xpath_get_text(xml, expr)[0])

    def test_arg_merging(self):
        """
        Make sure that default parameters from osinfo do not override user-
        provided parameters.
        """
        graphics = {'type': 'vnc', 'listen': '127.0.0.1'}
        args = {'name': 'test', 'os_distro': 'opensuse', 'os_version': '12.3',
                'cpus': 2, 'memory': 2048, 'networks': ['foo'],
                'cdrom': self.iso, 'graphics': graphics}
        t = VMTemplate(args)
        self.assertEquals(2, t.info.get('cpus'))
        self.assertEquals(2048, t.info.get('memory'))
        self.assertEquals(['foo'], t.info.get('networks'))
        self.assertEquals(self.iso, t.info.get('cdrom'))
        self.assertEquals(graphics, t.info.get('graphics'))
