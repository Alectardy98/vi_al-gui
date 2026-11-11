"""Explicit hardware-test seam: log HID requests and reject configuration writes."""
import atexit,json,os
from pathlib import Path
import threading
import hidproxy

root=Path(os.environ['VI_AL_VALIDATION_DIR']);root.mkdir(parents=True,exist_ok=True)
state={'requests':0,'blocked':[],'commands':{},'examples':{}}
lock=threading.Lock()
# Existing AMK GET/READ command constants, captured from the shipped protocol.
allowed_amk=set(json.loads((Path(os.environ['VI_AL_VALIDATION_SCRIPT_DIR'])/'readonly_amk_commands.json').read_text()))

def allowed(data):
    if len(data)!=33 or data[0]!=0:return False
    q=data[1:]
    if q[:6]==b'\xcaEC42\2':return q[6] in (0x10,0x11,0x12,0x13,0x14,0x15,0x16,0x1c,0x1d,0x27,0x28,0x2b)
    if q[2:4]==b'\xc0\x21' and 0x81<=q[1]<=0x95:
        # Native Leyden Jar reads/snapshots. No output toggle, trigger save,
        # defaults reset, EEPROM clear, reboot or bootloader is allowed.
        return (q[0]==2 and q[1] in (0x81,0x82,0x83,0x85,0x86,0x8c,0x8d,0x8e,0x8f,0x90,0x91,0x92,0x93,0x95)
                or q[0]==3 and q[1] in (0x84,0x87,0x88))
    if q[0] in (1,2,4,8,12,13,14,17,18):return True
    if q[0]==254:
        return q[1] in (0,1,2,3,5,8,9,10) or (q[1]==13 and q[2] in (0,1,3,5,7))
    if q[0]==253:
        if q[1] in (230,233,234,236):return q[2] in (0,1,5)
        if q[1]==231:return q[2] in (0,1,3)  # SLP1 capabilities/config/status
        if q[1]==232:return q[2] in (0,1,5,6)  # OLED reload (6) reads AUX; no persistence
        if q[1]==235:return q[2] in (0,1,3,4,5)  # TCH2 read-only status/diagnostics
        if q[1]==237:
            return q[2] in (0,2) or (q[2]==1 and ((q[5]==9 and q[6]==0) or q[5]==10 or(q[5]==11 and q[6]==0) or(q[5]==12 and q[6]==2)))
        if q[1]==238:return q[2] in (0,1,2,10,11,13)
        return q[1] in allowed_amk
    return False

factory=hidproxy.hid.device
class Device:
    def __init__(self,*a,**kw):self.handle=factory(*a,**kw)
    def __getattr__(self,name):return getattr(self.handle,name)
    def write(self,data):
        raw=bytes(data);ok=allowed(raw)
        with lock:
            state['requests']+=1;k=raw[1:4].hex();state['commands'][k]=state['commands'].get(k,0)+1
            state['examples'].setdefault(k,raw.hex())
            if not ok:state['blocked'].append(raw.hex())
        if not ok:
            (root/'hid-requests.json').write_text(json.dumps(state,indent=2))
            raise RuntimeError('Hardware validation blocked a non-read-only HID request: '+raw.hex())
        return self.handle.write(data)
    def send_feature_report(self,data):
        raw=bytes(data)
        if len(raw)!=65 or raw[0]!=0 or raw[1] not in (5,0x85,0x88,0x8d,0x86) or any(raw[3:]):
            with lock:state['blocked'].append('feature:'+raw.hex())
            raise RuntimeError('Hardware validation blocked a lighting write')
        return self.handle.send_feature_report(data)
hidproxy.hid.device=Device

def save():
    (root/'hid-requests.json').write_text(json.dumps(state,indent=2)+'\n')
atexit.register(save)
