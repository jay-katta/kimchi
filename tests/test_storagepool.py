#
# Project Kimchi
#
# Copyright IBM, Corp. 2013
#
# Authors:
#  Zhou Zheng Sheng <zhshzhou@linux.vnet.ibm.com>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import libxml2
import unittest


import kimchi.model
from kimchi.rollbackcontext import RollbackContext


class storagepoolTests(unittest.TestCase):
    def test_get_storagepool_xml(self):
        poolDefs = [
            {'def':
                {'type': 'dir',
                 'name': 'unitTestDirPool',
                 'path': '/var/temp/images'},
             'xml':
             """
             <pool type='dir'>
               <name>unitTestDirPool</name>
               <target>
                 <path>/var/temp/images</path>
               </target>
             </pool>
             """},
            {'def':
                {'type': 'netfs',
                 'name': 'unitTestNFSPool',
                 'source': {'host': '127.0.0.1',
                            'path': '/var/export'}},
             'xml':
             """
             <pool type='netfs'>
               <name>unitTestNFSPool</name>
               <source>
                 <host name='127.0.0.1'/>
                 <dir path='/var/export'/>
               </source>
               <target>
                 <path>/var/lib/kimchi/nfs_mount/unitTestNFSPool</path>
               </target>
             </pool>
             """},
            {'def':
                {'type': 'logical',
                 'name': 'unitTestLogicalPool',
                 'source': {'devices': ['/dev/hda', '/dev/hdb']}},
             'xml':
             """
             <pool type='logical'>
             <name>unitTestLogicalPool</name>
                 <source>
                     <device path="/dev/hda" />
                     <device path="/dev/hdb" />
                 </source>
             <target>
                 <path>/var/lib/kimchi/logical_mount/unitTestLogicalPool</path>
             </target>
             </pool>
             """},
            {'def':
                {'type': 'iscsi',
                 'name': 'unitTestISCSIPool',
                 'source': {
                     'host': '127.0.0.1',
                     'target': 'iqn.2003-01.org.linux-iscsi.localhost'}},
             'xml':
             """
             <pool type='iscsi'>
               <name>unitTestISCSIPool</name>
               <source>
                 <host name='127.0.0.1' />
                 <device path='iqn.2003-01.org.linux-iscsi.localhost'/>
               </source>
               <target>
                 <path>/dev/disk/by-id</path>
               </target>
             </pool>
             """},
            {'def':
                {'type': 'iscsi',
                 'name': 'unitTestISCSIPoolPort',
                 'source': {
                     'host': '127.0.0.1',
                     'port': 3266,
                     'target': 'iqn.2003-01.org.linux-iscsi.localhost'}},
             'xml':
             """
             <pool type='iscsi'>
               <name>unitTestISCSIPoolPort</name>
               <source>
                 <host name='127.0.0.1' port='3266' />
                 <device path='iqn.2003-01.org.linux-iscsi.localhost'/>
               </source>
               <target>
                 <path>/dev/disk/by-id</path>
               </target>
             </pool>
             """},
            {'def':
                {'type': 'iscsi',
                 'name': 'unitTestISCSIPoolAuth',
                 'source': {
                     'host': '127.0.0.1',
                     'target': 'iqn.2003-01.org.linux-iscsi.localhost',
                     'auth': {'username': 'testUser',
                              'password': 'ActuallyNotUsedInPoolXML'}}},
             'xml':
             """
             <pool type='iscsi'>
               <name>unitTestISCSIPoolAuth</name>
               <source>
                 <host name='127.0.0.1' />
                 <device path='iqn.2003-01.org.linux-iscsi.localhost'/>
                 <auth type='chap' username='testUser'>
                   <secret type='iscsi' usage='unitTestISCSIPoolAuth'/>
                 </auth>
               </source>
               <target>
                 <path>/dev/disk/by-id</path>
               </target>
             </pool>
             """}]

        for poolDef in poolDefs:
            defObj = kimchi.model.StoragePoolDef.create(poolDef['def'])
            xmlStr = defObj.xml
            with RollbackContext() as rollback:
                t1 = libxml2.readDoc(xmlStr, URL='', encoding='UTF-8',
                                     options=libxml2.XML_PARSE_NOBLANKS)
                rollback.prependDefer(t1.freeDoc)
                t2 = libxml2.readDoc(poolDef['xml'], URL='', encoding='UTF-8',
                                     options=libxml2.XML_PARSE_NOBLANKS)
                rollback.prependDefer(t2.freeDoc)
                self.assertEquals(t1.serialize(), t2.serialize())