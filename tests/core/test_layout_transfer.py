"""Bounded, read-only layout recovery without keyboards."""
import json
import lzma
import struct
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QObject
from protocol.keyboard_comm import Keyboard, KeyboardDefinitionError
from autorefresh.autorefresh import Autorefresh

LAYOUT = {'name':'test','matrix':{'rows':1,'cols':1},'layouts':{'keymap':[['0,0']]}}


class Device:
    def __init__(self, corrupt=0, size=None, short=False):
        self.payload = lzma.compress(json.dumps(LAYOUT).encode())
        self.corrupt, self.size, self.short = corrupt, size, short
        self.attempt = 0
        self.calls = []
        self.drains = 0

    def read(self, count, timeout_ms):
        self.drains += 1
        return b''

    @staticmethod
    def send(dev, message, retries=1):
        assert retries == 1, 'Layout requests must not queue duplicate packets'
        dev.calls.append(message)
        if message == b'\x01':
            dev.attempt += 1
            if dev.short and dev.attempt == 1:
                return b'\x01'
            data = b'\x01\x00\x09'
        elif message == b'\xfe\x00':
            data = struct.pack('<IQ',6,1234)
        elif message == b'\xfe\x01':
            data = struct.pack('<I',len(dev.payload) if dev.size is None else dev.size)
        else:
            assert message[:2] == b'\xfe\x02'
            offset = struct.unpack('<I',message[2:])[0]*32
            payload = dev.payload
            if dev.attempt <= dev.corrupt:
                payload = bytes([payload[0]^255])+payload[1:]
            data = payload[offset:offset+32]
        return data.ljust(32,b'\0')


def test_valid_transfer_and_corrupt_first_attempt_recovery():
    for damaged in (0,1):
        dev=Device(corrupt=damaged)
        assert Keyboard(dev,usb_send=Device.send).read_device_definition()==LAYOUT
        assert dev.attempt==damaged+1
        assert all(cmd==b'\x01' or cmd[:2]in(b'\xfe\x00',b'\xfe\x01',b'\xfe\x02')for cmd in dev.calls)


def test_permanent_corruption_is_a_connection_error_not_lzma_traceback():
    dev=Device(corrupt=2)
    with pytest.raises(KeyboardDefinitionError,match='Close other keyboard tools'):
        Keyboard(dev,usb_send=Device.send).read_device_definition()
    assert dev.attempt==2 and dev.drains==1
    assert len([cmd for cmd in dev.calls if cmd[:2]==b'\xfe\x02'])==2


@pytest.mark.parametrize('size',[0,0xffffffff])
def test_bad_size_is_rejected_without_reading_blocks(size):
    dev=Device(size=size)
    with pytest.raises(KeyboardDefinitionError):
        Keyboard(dev,usb_send=Device.send).read_device_definition()
    assert dev.attempt==2
    assert not any(cmd[:2]==b'\xfe\x02'for cmd in dev.calls)


def test_short_packet_retries_the_whole_read_and_truncated_stream_is_rejected():
    dev=Device(short=True)
    assert Keyboard(dev,usb_send=Device.send).read_device_definition()==LAYOUT
    assert dev.attempt==2
    dev=Device();dev.payload=dev.payload[:-5]
    with pytest.raises(KeyboardDefinitionError):Keyboard(dev,usb_send=Device.send).read_device_definition()


def test_failed_open_closes_partial_connection():
    closed=[];published=[]
    def bad_open(_):raise KeyboardDefinitionError('bad layout')
    old=SimpleNamespace(close=lambda:closed.append('old'))
    new=SimpleNamespace(sideload=False,via_stack=False,open=bad_open,close=lambda:closed.append('new'))
    refresh=Autorefresh.__new__(Autorefresh);QObject.__init__(refresh)
    refresh.current_device=old;refresh.devices=[new]
    refresh.thread=SimpleNamespace(set_device=published.append)
    with pytest.raises(KeyboardDefinitionError):refresh.select_device(0)
    assert closed==['old','new'] and refresh.current_device is None and published==[None]
