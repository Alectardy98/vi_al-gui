from types import SimpleNamespace
import struct
import pytest
from vi_al_addons.xwhatsit.protocol import Client,Settings,ProtocolError,KeysHeld,crc8,supported

DEFAULT=Settings(8,3,16,16,5,96)

class Handle:
    def __init__(self,extended=True):
        self.extended=extended;self.settings=DEFAULT;self.calls=[];self.response=[];self.saves=0;self.held=False;self.booted=False
    def write(self,data):
        self.calls.append(bytes(data))
        assert len(data)==33 and data[:3]==b'\0\x55\xaa'
        op=data[3];payload=data[4:];reply=bytearray(29);status=0x22
        if op==0x11:reply[:4]=bytes((2,int(self.extended),0,5))
        elif op==0x1a:reply[:10]=bytes((16,8,0,8,8,3,1,255,15,8))
        elif op==0x30:
            reply[:9]=b'XCAL\1'+bytes((5,3))+struct.pack('<H',4095);reply[9:17]=DEFAULT.encode()
        elif op==0x31:reply[:8]=self.settings.encode()
        elif op in (0x32,0x33,0x34):
            if self.held:status=0x24
            else:
                if op==0x32:self.settings=Settings.decode(payload[:8]);self.saves+=1
                if op==0x33:self.settings=DEFAULT;self.saves+=1
                reply[:8]=self.settings.encode()
        elif op==0x16:
            group=payload[0];offset=payload[1]
            bitmap=b''.join(sum(1<<c for c in range(16) if c%5==group).to_bytes(2,'little') for _ in range(8))
            reply[:3]=bytes((5,))+struct.pack('<H',300+group*10);reply[3:3+min(26,16-offset)]=bitmap[offset:offset+26]
        elif op==0x15:
            if self.held:reply[0]=1
        elif op==0x19:reply[:2]=struct.pack('<H',220 if self.held else 340)
        elif op==0x12:self.booted=True;return 33
        elif op==0x18:pass
        else:status=0x23
        self.response.append(b'\x55\xaa'+bytes((status,))+reply)
        return 33
    def read(self,size,timeout_ms):return self.response.pop(0) if self.response else b''

def keyboard(handle):
    return SimpleNamespace(dev=handle,keyboard_id=int.from_bytes(bytes.fromhex('f6f743db220116d9'),'little'),rows=8,cols=16)

def client(extended=True):
    handle=Handle(extended);return Client(keyboard(handle)).connect(),handle

@pytest.mark.parametrize('value',[DEFAULT,Settings(1,1,1,2,1,0),Settings(32,32,32,32,15,4095)])
def test_record_roundtrip_and_every_single_bit_error(value):
    raw=value.encode();assert Settings.decode(raw)==value
    for bit in range(64):
        damaged=bytearray(raw);damaged[bit//8]^=1<<(bit%8)
        with pytest.raises(ProtocolError):Settings.decode(damaged)

@pytest.mark.parametrize('value',[Settings(0,3,16,16,5,96),Settings(33,3,16,16,5,96),Settings(8,33,16,16,5,96),Settings(8,3,3,16,5,96),Settings(8,3,64,16,5,96),Settings(8,3,16,16,16,96),Settings(8,3,16,16,5,4096)])
def test_invalid_values_are_rejected_before_sending(value):
    with pytest.raises(ProtocolError):value.encode()

def test_capabilities_and_live_state_no_configuration_writes():
    c,h=client();assert c.extension and c.defaults==DEFAULT and c.settings==DEFAULT
    assert len(c.thresholds)==128
    assert c.snapshot((0,0))==(set(),340)
    h.held=True;assert c.snapshot((0,0))==({(0,0)},220)
    assert h.saves==0

def test_legacy_monitoring_without_reflash_never_sends_extension_commands():
    c,h=client(False);assert not c.extension
    c.snapshot((0,0));assert all(call[3]<0x30 for call in h.calls)
    with pytest.raises(ProtocolError):c.get_settings()

def test_save_busy_readback_defaults_and_boot():
    c,h=client();updated=Settings(10,6,32,32,3,120)
    h.held=True
    with pytest.raises(KeysHeld):c.apply(updated)
    assert h.settings==DEFAULT and h.saves==0
    h.held=False;assert c.apply(updated)==updated and c.get_settings()==updated and h.saves==1
    assert c.reset_defaults()==DEFAULT and h.saves==2
    c.enter_bootloader();assert h.booted

def test_short_write_or_missing_ack_is_not_retried():
    c,h=client();before=len(h.calls)
    h.write=lambda data:0
    with pytest.raises(ProtocolError):c.apply(DEFAULT)
    assert len(h.calls)==before
    c,h=client();send=h.write
    def silent(data):send(data);h.response.clear();return 33
    h.write=silent
    with pytest.raises(ProtocolError):c.apply(DEFAULT)
    assert len([x for x in h.calls if x[3]==0x32])==1

def test_wrong_profile_and_matrix_are_rejected():
    h=Handle();kb=keyboard(h);kb.keyboard_id=0
    with pytest.raises(ProtocolError):Client(kb)
    assert not h.calls
    c,h=client();c.rows=7
    with pytest.raises(ProtocolError):c.connect()


def test_frame_reads_only_one_extra_key_and_never_persists():
    c,h=client();before=len(h.calls)
    position,pressed,readings=c.frame((0,0),(0,1))
    assert pressed==set() and readings=={(0,0):340,(0,1):340}
    assert [call[3]for call in h.calls[before:]]==[0x15,0x19,0x15,0x19]
    before=len(h.calls);c.frame((0,0),(0,0))
    assert [call[3]for call in h.calls[before:]]==[0x15,0x19]
    before=len(h.calls);c.frame((0,0),(99,99))
    assert [call[3]for call in h.calls[before:]]==[0x15,0x19,0x15]
    assert h.saves==0


def test_typing_and_release_cooldown_pause_background_reads(monkeypatch):
    import vi_al_addons.xwhatsit.protocol as protocol
    now=[100.];monkeypatch.setattr(protocol.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(protocol.time,'sleep',lambda seconds:None)
    c,h=client();h.held=True;before=len(h.calls)
    pos,pressed,readings=c.frame((0,3),[(0,1),(0,2),(0,4)])
    assert pos==(0,0) and pressed=={(0,0)} and readings=={(0,0):220}
    assert len([r for r in h.calls[before:]if r[3]==0x19])==1
    h.held=False;now[0]+=.1
    assert len(c.frame((0,0),[(0,1)])[2])==1
    now[0]+=.36
    assert len(c.frame((0,0),[(0,1)])[2])==2
    assert h.saves==0


def test_cached_matrix_uses_vial_state_and_respects_unlock():
    c,h=client();cached_calls=[]
    c._cached_matrix_supported=True
    c.keyboard.get_unlock_status=lambda retries=1:True
    def cached():
        cached_calls.append(1)
        return b'\x02\x03'+b'\x00\x01'+bytes(28)
    c.keyboard.matrix_poll=cached
    before=len(h.calls)
    pos,pressed,values=c.frame((0,2),[(0,1)])
    assert pos==(0,0) and pressed=={(0,0)} and values=={(0,0):340}
    assert cached_calls and all(call[3]!=0x15 for call in h.calls[before:])
    assert c._use_cached_matrix is False
    c.keyboard.get_unlock_status=lambda retries=1:False
    before=len(h.calls);c.frame((0,0),[])
    assert any(call[3]==0x15 for call in h.calls[before:])
    assert h.saves==0


def test_cached_matrix_decodes_20_columns_big_endian():
    h=Handle();kb=keyboard(h)
    kb.keyboard_id=int.from_bytes(bytes.fromhex('1e0909a118b415db'),'little')
    kb.rows=4;kb.cols=20;kb.vial_protocol=6
    kb.matrix_poll=lambda:b'\x02\x03'+(1<<19).to_bytes(3,'big')+bytes(27)
    kb.get_unlock_status=lambda retries=1:True
    c=Client(kb);c._use_cached_matrix=True
    assert c.key_state()=={(0,19)}
