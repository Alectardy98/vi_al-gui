# SPDX-License-Identifier: GPL-2.0-or-later
"""NRL1 ROM catalogue and acknowledged AUX-owned selection, over negotiated AFB."""
from vi_al_addons.my2k.animation_files_protocol import AnimationFilesClient
import struct

ERRORS = {0:'Supported',2:'Invalid or unreadable ROM',3:'Unsupported ROM format',4:'Unsupported cartridge mapper',5:'Invalid ROM length',6:'Unsupported cartridge variant',9:'Cartridge needs more RAM than available',10:'PAL/multi-region timing is not supported yet'}

def decode(data,gbc=False):
    if len(data)<16 or data[:4]!=(b'GRL1' if gbc else b'NRL1') or data[4]!=1 or data[5]!=24 or data[6]>24 or len(data)!=16+112*data[6]:
        raise ValueError('Invalid emulator library response.')
    result=[]
    for i in range(data[6]):
        row=data[16+i*112:16+(i+1)*112]
        raw=row[16:]
        if b'\0' not in raw:raise ValueError('Unterminated ROM name.')
        name=raw.split(b'\0',1)[0].decode('cp437')
        encode_name(name,gbc)
        size,prg,chr_size,mapper,error,selected=struct.unpack_from('<IIIHBB',row)
        if selected>1:raise ValueError('Invalid ROM selection flag.')
        result.append(dict(name=name,size=size,prg=prg,chr=chr_size,mapper=mapper,error=error,selected=bool(selected),status=ERRORS.get(error,'Unsupported cartridge')))
    return result,bool(data[7]&1)

def encode_name(name,gbc=False):
    raw=name.encode('cp437')
    if not (4 if gbc else 5)<=len(raw)<=95 or not name.lower().endswith(('.gb','.gbc') if gbc else '.nes') or any(c in name for c in('/','\\',':','\0')) or '..'in name or any(c<32 for c in raw):
        raise ValueError('Choose a supported ROM filename from the keyboard library.')
    return raw+b'\0'

class NesLibraryClient:
    gbc=False
    list_op=11
    select_op=12
    def __init__(self,keyboard):
        self.files=AnimationFilesClient(keyboard)
        self.files.capabilities()
        if not self.files.fast or not getattr(self.files.fast,'gbc_library' if self.gbc else 'rom_library',False):
            self.close()
            raise ValueError('ROM selection requires the matching emulator-compatible AUX firmware. Existing game controls remain available.')
    def catalogue(self):
        rows=[];cursor=0
        for page in range(22):
            r=self.files.request(self.list_op,offset=cursor)
            batch,unused=decode(r[32:],self.gbc);data=r[32:]
            if any(x['name']in {a['name']for a in rows}for x in batch):raise RuntimeError('ROM catalogue changed while loading. Reload the list.')
            rows.extend(batch)
            if not data[7]&1:return rows,bool(data[7]&2)
            next_cursor=int.from_bytes(data[12:16],'little')
            if not cursor<next_cursor<512:raise RuntimeError('Invalid ROM catalogue cursor.')
            cursor=next_cursor
        raise RuntimeError('ROM catalogue exceeds the bounded directory limit.')
    def select(self,name):
        r=self.files.request(self.select_op,data=encode_name(name,self.gbc))
        if r[32:36]!=(b'GRS1' if self.gbc else b'NRS1') or len(r)!=40:raise RuntimeError('ROM selection acknowledgement is invalid; no save was retried.')
        rows,truncated=self.catalogue()
        if not any(x['name']==name and x['selected'] and not x['error']for x in rows):
            raise RuntimeError('ROM selection readback differs; no save was retried.')
        return rows,truncated
    def close(self):
        if self.files.fast:self.files.fast.close()

class GbcLibraryClient(NesLibraryClient):
    gbc=True
    list_op=13
    select_op=14
