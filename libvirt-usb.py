#!/usr/bin/python3
# A. Lochmann 2022
from __future__ import print_function
from pprint import pprint
from prompt_toolkit.shortcuts import radiolist_dialog
from xml.dom import minidom
import xml.etree.ElementTree as ET
import logging
import sys
import usb.core
import libvirt
import subprocess

logging.basicConfig(encoding='utf-8', level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

def promptDevList(devList):
    valueList = list()
    i = -1
    for entry in devList:
        i = i + 1
        valueList.append((str(i), entry['desc']))
    result = radiolist_dialog(title='USB Devices', text='Please select an USB device', values=valueList).run()
    if result is None:
        return None
    else:
        idx = int(result)
        LOGGER.debug('Selected entry (' + result + '): ' + devList[idx]['desc'])
        return devList[idx]

def selectDevicePyUSB(filterList = None):
    devs = usb.core.find(find_all=1)
    devList = list()
    print(filterList)
    for dev in devs:
        if dev.product is None or dev.manufacturer is None:
           continue
        entry = dict()
        entry['id_vendor'] = hex(dev.idVendor)
        entry['id_product'] = hex(dev.idProduct)
        entry['desc'] = dev.manufacturer + ' ' + dev.product
        if filterList is not None:
           devId = '{:04x}:{:04x}'.format(dev.idVendor, dev.idProduct)
           if (devId not in filterList):
              continue
        devList.append(entry)
    if len(devList) == 0:
        return None
    return promptDevList(devList)

def selectDeviceLSUSB(filterList = None):
    lsusb = subprocess.Popen('lsusb', stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    stdout, stderr = lsusb.communicate()
    if lsusb.returncode == 0:
        LOGGER.debug('Successfully run lsusb')
    else:
        print('Error running lsusb: ' + stderr.decode(), end = '')
    stdout = stdout.decode()
    devList = list()
    for line in stdout.split('\n'):
       elems = line.split(' ')
       # A little bit of heuristics. Each valid output line
       # contains at least six elements
       if len(elems) < 6:
          continue
       entry = dict()
       entry['id_vendor'] = '0x' + elems[5].split(':')[0]
       entry['id_product'] = '0x' + elems[5].split(':')[1]
       entry['desc'] = ' '.join(elems[6:])
       if filterList is not None:
           if (entry['id_vendor'] + ':' + entry['id_product'] not in filterList):
              continue
       devList.append(entry)
    if len(devList) == 0:
        return None
    print(devList)
    return promptDevList(devList)

def virshDom(attach, dom, dev):
    if attach == True:
        op = 'attach'
    else:
        op = 'detach'
    xml = "<hostdev mode='subsystem' type='usb' managed='yes'>\
  <source>\
    <vendor id='" + dev['id_vendor'] + "'/>\
    <product id='" + dev['id_product'] + "'/>\
  </source>\
</hostdev>"
    cmd = ['virsh', op + '-device', dom.name(), '/dev/stdin']
    virsh = subprocess.Popen(cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE, stdin = subprocess.PIPE)
    stdout, stderr = virsh.communicate(input = xml.encode())
    if virsh.returncode == 0:
        print('Successfully ' + op + 'ed device: ' + dev['desc'])
    else:
        print('Error running virsh: ' + stderr.decode(), end = '')

def attachedDevs(dom):
    raw_xml = dom.XMLDesc(0)
    xml = ET.fromstring(raw_xml)
    
    usbDevs = list()
    for hostdev in xml.find('devices').iter('hostdev'):
        if hostdev.get('type') == 'usb':
           src = hostdev.find('source')
           if src is None:
              LOGGER.error('Cannot find source tag below hostdev!')
              sys.exit(1)
           vendor = src.find('vendor')
           product = src.find('product')
           if vendor is None or product is None:
              continue
           devId = vendor.get('id') + ':' + product.get('id')
           LOGGER.debug('Attached USB device: ' + devId)
           usbDevs.append(devId)
    return usbDevs

def detach(dom):
    LOGGER.debug("detach")
    aDevs = attachedDevs(dom)
    if len(aDevs) == 0:
       print('No device attached')
       return
#    dev = selectDevicePyUSB(aDevs)
    dev = selectDeviceLSUSB(aDevs)
    if dev is None:
       print('No device selected')
       return
    virshDom(False, dom, dev)

def attach(dom):
    LOGGER.debug("attach")
#    dev = selectDevicePyUSB(aDevs)
    dev = selectDeviceLSUSB()
    if dev is None:
       print('No device selected')
       return
    virshDom(True, dom, dev)

def listdevs(dom): 
    LOGGER.debug("listdevs")
    for dev in attachedDevs(dom):
        print('Attached USB host devices: ' + dev)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        LOGGER.error('Usage: ' + sys.argv[0] + ' <attach|detach> <dom>')
        sys.exit(1)
    op = sys.argv[1]
    domName = sys.argv[2]

    try:
        conn = libvirt.open('qemu:///system')
    except libvirt.libvirtError as e:
        LOGGER.error('Error during libvirt open: ' + str(e))
        sys.exit(1)
    try:
        dom = conn.lookupByName(domName)
    except libvirt.libvirtError as e:
        LOGGER.error('Error during dom lookup: ' + str(e))
        sys.exit(1)
    if not dom.isActive():
        LOGGER.error('domain "' + dom.name() + '" is not active')
        sys.exit(1)

    if op == 'attach':
        attach(dom)
    elif op == 'detach':
        detach(dom)
    elif op == 'list':
        listdevs(dom)
    else:
        LOGGER.error('Unknown operation!')

    conn.close()
    sys.exit(0)
