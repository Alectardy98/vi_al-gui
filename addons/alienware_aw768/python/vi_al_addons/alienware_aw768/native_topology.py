# SPDX-License-Identifier: GPL-2.0-or-later
"""Native USB ancestry on Windows/macOS, without shell commands or extra drivers.

These adapters preserve the Linux policy: exact HID interface identity and the
same immediate non-root hub. No fallback pairs merely by product name or count.
"""
import ctypes as C
import re
from .identity import PairingError, UsbLocation


def windows_instance_id(path):
    """HIDAPI symbolic link -> PnP instance ID; the GUID is not part of the ID."""
    match = re.fullmatch(r'\\\\\?\\(hid#[^#]+#[^#]+)#\{[0-9a-f-]+\}',path,re.I)
    if not match:
        raise PairingError('Unrecognized Windows HID interface path.')
    return match[1].replace('#','\\').upper()


def windows_location(path):
    from ctypes import wintypes as W
    api = C.WinDLL('cfgmgr32')
    locate = api.CM_Locate_DevNodeW
    locate.argtypes=[C.POINTER(W.DWORD),W.LPWSTR,W.ULONG];locate.restype=W.ULONG
    parent = api.CM_Get_Parent
    parent.argtypes=[C.POINTER(W.DWORD),W.DWORD,W.ULONG];parent.restype=W.ULONG
    identity = api.CM_Get_Device_IDW
    identity.argtypes=[W.DWORD,W.LPWSTR,W.ULONG,W.ULONG];identity.restype=W.ULONG
    prop = api.CM_Get_DevNode_Registry_PropertyW
    prop.argtypes=[W.DWORD,W.ULONG,C.POINTER(W.ULONG),W.LPVOID,C.POINTER(W.ULONG),W.ULONG]
    prop.restype=W.ULONG
    instance = windows_instance_id(path)
    node = W.DWORD()
    if locate(C.byref(node),C.create_unicode_buffer(instance),0):
        raise PairingError('Windows could not resolve this HID device; refresh devices.')
    nodes=[]
    for _ in range(32):
        text=C.create_unicode_buffer(1024)
        if identity(node.value,text,len(text),0):
            raise PairingError('Windows could not read USB ancestry.')
        nodes.append((node.value,text.value.upper()))
        next_node=W.DWORD()
        if parent(C.byref(next_node),node.value,0):break
        node=next_node
    else:
        raise PairingError('Windows USB ancestry exceeded the bound.')
    interface=None;device=None
    for at,(devinst,name) in enumerate(nodes):
        if not name.startswith('USB\\'):continue
        match=re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})([^\\]*)',name)
        if not match:continue
        mi=re.search(r'&MI_([0-9A-F]{2})',match[3])
        if mi:
            interface=(int(mi[1],16),devinst)
        elif interface is not None:
            device=(at,name,int(match[1],16),int(match[2],16));break
    if device is None or interface is None or device[0]+1>=len(nodes):
        raise PairingError('Windows USB interface/device ancestry is incomplete.')
    def property_text(devinst,code):
        text=C.create_unicode_buffer(2048);kind=W.ULONG();size=W.ULONG(C.sizeof(text))
        if prop(devinst,code,C.byref(kind),text,C.byref(size),0):
            raise PairingError('Windows USB identity properties are unavailable.')
        return ''.join(text).rstrip('\0').upper()
    # CM_DRP_COMPATIBLEIDS = 2; CM_DRP_SERVICE = 5.
    if not re.search(r'USB\\CLASS_03(?:&|\0|$)',property_text(interface[1],2)):
        raise PairingError('The selected Windows interface is not USB HID.')
    hubinst,hub=nodes[device[0]+1]
    if not re.match(r'USB\\VID_[0-9A-F]{4}&PID_[0-9A-F]{4}\\',hub):
        raise PairingError('AW768 boards must share an internal USB hub, not the host root.')
    if property_text(hubinst,5) not in ('USBHUB','USBHUB3'):
        raise PairingError('Windows parent is not a verified USB hub.')
    return UsbLocation(device[1],hub,device[2],device[3],interface[0])


def macos_location(path):
    match=re.fullmatch(r'DevSrvsID:([0-9]+)',path)
    if not match:
        raise PairingError('Unrecognized macOS HIDAPI registry path.')
    io=C.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
    cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    def bind(lib,name,restype,*args):
        func=getattr(lib,name);func.restype=restype;func.argtypes=list(args);return func
    release=bind(io,'IOObjectRelease',C.c_int,C.c_uint)
    parent=bind(io,'IORegistryEntryGetParentEntry',C.c_int,C.c_uint,C.c_char_p,C.POINTER(C.c_uint))
    entry_id=bind(io,'IORegistryEntryGetRegistryEntryID',C.c_int,C.c_uint,C.POINTER(C.c_uint64))
    conforms=bind(io,'IOObjectConformsTo',C.c_ubyte,C.c_uint,C.c_char_p)
    matching=bind(io,'IORegistryEntryIDMatching',C.c_void_p,C.c_uint64)
    service=bind(io,'IOServiceGetMatchingService',C.c_uint,C.c_uint,C.c_void_p)
    create_key=bind(cf,'CFStringCreateWithCString',C.c_void_p,C.c_void_p,C.c_char_p,C.c_uint32)
    get_property=bind(io,'IORegistryEntryCreateCFProperty',C.c_void_p,C.c_uint,C.c_void_p,C.c_void_p,C.c_uint)
    cf_release=bind(cf,'CFRelease',None,C.c_void_p)
    get_type=bind(cf,'CFGetTypeID',C.c_ulong,C.c_void_p)
    number_type=bind(cf,'CFNumberGetTypeID',C.c_ulong)
    get_number=bind(cf,'CFNumberGetValue',C.c_ubyte,C.c_void_p,C.c_int,C.c_void_p)
    def number(node,name):
        key=create_key(None,name.encode(),0x08000100)
        value=get_property(node,key,None,0);cf_release(key)
        if not value:return None
        try:
            result=C.c_int64()
            return result.value if get_type(value)==number_type() and get_number(value,4,C.byref(result)) else None
        finally:cf_release(value)
    def ident(node):
        result=C.c_uint64()
        if entry_id(node,C.byref(result)):raise PairingError('macOS USB registry ID is unavailable.')
        return 'IORegistry:'+str(result.value)
    node=service(0,matching(int(match[1])))
    if not node:raise PairingError('The macOS HID registry entry disappeared; refresh devices.')
    interface=None;device=None
    try:
        for _ in range(32):
            if conforms(node,b'IOUSBHostInterface') or conforms(node,b'IOUSBInterface'):
                interface=(number(node,'bInterfaceNumber'),number(node,'bInterfaceClass'))
            elif conforms(node,b'IOUSBHostDevice') or conforms(node,b'IOUSBDevice'):
                if device is None:
                    device=(ident(node),number(node,'idVendor'),number(node,'idProduct'))
                else:
                    if number(node,'bDeviceClass')!=9 or interface is None or interface[1]!=3:
                        raise PairingError('macOS could not verify the HID interface and internal USB hub.')
                    if any(x is None for x in (*device,*interface)):
                        raise PairingError('macOS USB properties are incomplete.')
                    return UsbLocation(device[0],ident(node),device[1],device[2],interface[0],interface[1])
            next_node=C.c_uint()
            if parent(node,b'IOService',C.byref(next_node)):break
            release(node);node=next_node.value
        raise PairingError('No immediate internal USB hub was found for the macOS HID interface.')
    finally:release(node)
