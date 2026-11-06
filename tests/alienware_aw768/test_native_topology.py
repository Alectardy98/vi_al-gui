"""Native topology adapters keep exact pairing without invoking host tools."""
import ctypes
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from vi_al_addons.alienware_aw768.identity import PairingError
from vi_al_addons.alienware_aw768.native_topology import windows_instance_id,windows_location,macos_location

PATH=r'\\?\hid#vid_04f2&pid_1666&mi_02#7&abcd&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}'


def api(hub=r'USB\VID_05E3&PID_0610\HUB',interface_class='03'):
    names={1:r'HID\VID_04F2&PID_1666&MI_02\7&ABCD&0&0000',
           2:r'USB\VID_04F2&PID_1666&MI_02\INTERFACE',
           3:r'USB\VID_04F2&PID_1666\0000',4:hub}
    def locate(out,name,flags):out._obj.value=1;return 0
    def identity(node,out,size,flags):out.value=names[node];return 0
    def parent(out,node,flags):out._obj.value=node+1;return 0 if node<4 else 1
    def prop(node,key,kind,out,size,flags):
        out.value='USB\\Class_'+interface_class+'&SubClass_00\0' if key==2 else 'USBHUB3'
        return 0
    return SimpleNamespace(CM_Locate_DevNodeW=locate,CM_Get_Device_IDW=identity,
                           CM_Get_Parent=parent,CM_Get_DevNode_Registry_PropertyW=prop)


def test_windows_hid_path_maps_to_exact_instance():
    assert windows_instance_id(PATH)==r'HID\VID_04F2&PID_1666&MI_02\7&ABCD&0&0000'
    for invalid in ['/dev/hidraw1','',r'USB\VID_04F2&PID_1666',PATH+'extra']:
        with pytest.raises(PairingError):windows_instance_id(invalid)


def test_windows_uses_native_parent_hub_and_hid_class():
    with patch.object(ctypes,'WinDLL',return_value=api(),create=True):
        location=windows_location(PATH)
    assert (location.vendor_id,location.product_id,location.interface_number)==(0x04f2,0x1666,2)
    assert location.hub==r'USB\VID_05E3&PID_0610\HUB'


def test_windows_rejects_root_hub_and_non_hid_interface():
    for fake in [api(hub=r'USB\ROOT_HUB30\ROOT'),api(interface_class='08')]:
        with patch.object(ctypes,'WinDLL',return_value=fake,create=True):
            with pytest.raises(PairingError):windows_location(PATH)


def test_macos_rejects_foreign_registry_paths_without_loading_libraries():
    with patch.object(ctypes,'CDLL')as load:
        for path in ['/dev/hidraw1','DevSrvsID:-1','DevSrvsID:1x']:
            with pytest.raises(PairingError):macos_location(path)
        load.assert_not_called()
