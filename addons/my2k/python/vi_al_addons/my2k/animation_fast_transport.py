# SPDX-License-Identifier: GPL-2.0-or-later
"""AFB1 large-block vendor EP0 transport; no HID claiming, reset or retries."""
from pathlib import Path
import struct,time

class FastAnimationTransport:
    block_size=4064
    read_size=4064
    frame_size=4096
    pipelined=False
    def __init__(self,keyboard,device=None):
        if device is None:
            import usb.core
            import libusb_package
            from usb.backend import libusb1
            # Bind libusb to the exact opened hidraw device, never the first
            # matching VID/PID (several identical keyboards may be connected).
            desc=getattr(keyboard,'usb_descriptor',getattr(keyboard,'desc',{}))
            name=Path(desc.get('path',b'').decode() if isinstance(desc.get('path'),bytes) else desc.get('path','')).name
            node=Path('/sys/class/hidraw')/name/'device'
            node=node.resolve()
            parent=next((p for p in (node,*node.parents)if(p/'idVendor').exists()),None)
            if parent is None or (parent/'idVendor').read_text().strip()!='4d58' or (parent/'idProduct').read_text().strip()!='f103':
                raise RuntimeError('Fast animation transfer requires the connected MY-2K in keyboard mode.')
            bus=int((parent/'busnum').read_text());address=int((parent/'devnum').read_text())
            backend=libusb1.get_backend(find_library=libusb_package.find_library)
            devices=list(usb.core.find(find_all=True,idVendor=0x4d58,idProduct=0xf103,backend=backend))
            matches=[d for d in devices if d.bus==bus and d.address==address]
            if len(matches)!=1:raise RuntimeError('Cannot uniquely match the keyboard USB control transport.')
            device=matches[0]
        self.rom_library=False;self.gbc_library=False;self.device=device;self.uncertain=False;self.requests=0;self.bytes=0;self.timings={};self.poll_estimate={};self.bulk=None;self.framed=False;self.combined=False;self.rle=False;self.out_packet=512;self.prefix_capacity=512;self.compressed_requests=0;self.logical_write_bytes=0;self.encoded_write_bytes=0
    def request(self,op,token,slot=0,offset=0,data=b'',replace=False):
        if self.uncertain:raise RuntimeError('Fast transfer uncertain; no mutation was retried.')
        if not (0<=op<=8 or (op in(11,12) and self.rom_library) or (op in(13,14) and self.gbc_library)) or not 0<=slot<=10 or not 1<=token<=255 or not 0<=offset<=0xffffffff or len(data)>(self.read_size if op==2 else self.block_size):
            raise ValueError('Fast animation request exceeds bounds.')
        logical=len(data);codec=0
        if op==4 and self.rle and logical and not logical&1:
            from vi_al_addons.my2k.animation_rle import encode
            packed=encode(data)
            if ((len(packed)+511)&~511)<((logical+511)&~511):data=packed;codec=1
        q=bytearray(32)
        q[:8]=bytes((253,238,op,2,token,slot,int(replace),0));struct.pack_into('<I',q,8,offset)
        struct.pack_into('<H',q,30,len(data))
        if op==3:
            if len(data)!=4:raise ValueError('BEGIN requires CRC32.')
            q[12:16]=data
        elif op in(4,12,14):
            if codec:q[7]=1;struct.pack_into('<H',q,28,logical)
            q+=data
        elif op!=2 and data:raise ValueError('Unexpected fast payload.')
        try:
            framed=self.bulk and self.framed and op in(2,4)
            idle_deadline=time.monotonic()+3
            while not framed:
                ready=bytes(self.device.ctrl_transfer(0xc0,0x62,0,0,4,timeout=2000))
                if len(ready)!=4 or ready[:3]!=b'AFB':raise RuntimeError('AFB1 readiness response is invalid.')
                if ready[3]==0:break
                if ready[3] not in(5,6):raise RuntimeError('A previous animation request still owns the transfer buffer; no command was sent.')
                if time.monotonic()>=idle_deadline:raise RuntimeError('Animation response buffer did not retire; no command was sent.')
                time.sleep(.0003)
            started=time.monotonic()
            if framed and self.combined:
                n=self.device.write(self.bulk[1],q,timeout=2000)
                # Device borrows a fixed prefix buffer. An exact packet boundary
                # below that capacity needs a ZLP to terminate this short frame.
                if len(q)<self.prefix_capacity and not len(q)%self.out_packet:
                    if self.device.write(self.bulk[1],b'',timeout=2000)!=0:raise RuntimeError('Animation frame terminator failed.')
            elif framed:
                n=self.device.write(self.bulk[1],q[:32],timeout=2000)
                if n!=32:raise RuntimeError('Short animation bulk header.')
                if op==4:n+=self.device.write(self.bulk[1],q[32:],timeout=2000)
            elif self.bulk and op==4:
                self.device.ctrl_transfer(0x40,0x63,len(q),0,b'',timeout=2000)
                n=self.device.write(self.bulk[1],q,timeout=2000)
            else:n=self.device.ctrl_transfer(0x40,0x60,0,0,q,timeout=2000)
            if n!=len(q):raise RuntimeError('Short fast animation request.')
            out_done=time.monotonic()
            # Learned, bounded pacing reduces repeated pending-status IRQs.
            # It never substitutes for checking an ACK or replays an OUT.
            delay=self.poll_estimate.get(op,0)*.75 if op in(2,4) and not(framed or(self.bulk and op==4)) else 0
            if delay:time.sleep(min(delay,.010))
            deadline=time.monotonic()+20
            while True:
                r=bytes(self.device.read(self.bulk[2],32+(len(data)if op==2 else 0),timeout=20000))if framed or(self.bulk and op==4) else bytes(self.device.ctrl_transfer(0xc0,0x61,0,0,self.frame_size,timeout=2000))
                if len(r)<32 or r[:6]!=bytes((253,238,170,2,op,token)):
                    raise RuntimeError('Fast animation acknowledgement does not match.')
                n=struct.unpack_from('<H',r,30)[0]
                if n>self.read_size or len(r)!=32+n:raise RuntimeError('Invalid fast animation response length.')
                if r[6]!=1:
                    self.requests+=1;self.bytes+=len(q)+len(r)
                    if op==4 and r[6]==2:self.compressed_requests+=codec;self.logical_write_bytes+=logical;self.encoded_write_bytes+=len(data)
                    elapsed=time.monotonic()-out_done
                    self.poll_estimate[op]=min(elapsed,self.poll_estimate.get(op,elapsed))
                    samples=self.timings.setdefault(op,[])
                    if len(samples)<2048:samples.append((time.monotonic()-started,int.from_bytes(r[20:24],'little'),int.from_bytes(r[24:28],'little')))
                    return r
                if time.monotonic()>=deadline:raise RuntimeError('Fast animation completion timed out.')
                time.sleep(.0005)
        except Exception:
            self.uncertain=True
            raise
    def capabilities(self,token):
        try:r=self.request(0,token)
        except Exception as error:
            if getattr(error,'errno',None)==13:
                raise RuntimeError('Fast animation USB access is denied. Install the supplied MY-2K USB permission rule, then reconnect.')from error
            if getattr(error,'errno',None)==32:
                raise RuntimeError('Fast animation protocol requires matching Main and AUX firmware. No file change was sent.')from error
            raise
        if r[6]!=2 or r[16]!=10:raise RuntimeError('Matching AFB Main/AUX firmware is required.')
        self.rom_library=bool(r[22]&32)
        self.gbc_library=bool(r[22]&64)
        signature=r[12:16];limit=int.from_bytes(r[20:22],'little')
        if signature in(b'AFB3',b'AFB5',b'AFB6',b'AFB7') and limit==4096:
            self.framed=signature in(b'AFB5',b'AFB6',b'AFB7');self.combined=signature in(b'AFB6',b'AFB7');self.rle=signature==b'AFB7';self.prefix_capacity=4096 if self.rle else 512
            import usb.util
            cfg=self.device.get_active_configuration()
            interfaces=[i for i in cfg if i.bInterfaceClass==255 and i.bInterfaceSubClass==0xaf and i.bInterfaceProtocol==3]
            if len(interfaces)!=1:raise RuntimeError('Missing dedicated animation bulk interface.')
            interface=interfaces[0];outs=[e.bEndpointAddress for e in interface if e.bmAttributes&3==2 and not e.bEndpointAddress&128];ins=[e.bEndpointAddress for e in interface if e.bmAttributes&3==2 and e.bEndpointAddress&128]
            if len(outs)!=1 or len(ins)!=1:raise RuntimeError('Invalid animation bulk endpoints.')
            self.out_packet=next(getattr(e,'wMaxPacketSize',512)for e in interface if e.bEndpointAddress==outs[0])
            if self.out_packet not in(64,512):raise RuntimeError('Unsupported animation bulk packet size.')
            usb.util.claim_interface(self.device,interface.bInterfaceNumber)
            self.bulk=(interface.bInterfaceNumber,outs[0],ins[0]);self.pipelined=True;self.block_size=4096;self.frame_size=4096
            # Both peer bit7 and Main bit0 are required; old pairs stay4064.
            if r[22]&128 and r[23]&1:self.read_size=4096
        elif signature==b'AFB2' and limit==4096:
            self.pipelined=True;self.block_size=4064;self.frame_size=4096
            # Linux usbfs limits synchronous EP0 requests to4096 bytes.
            # AUX bulk packets still pad4064 file bytes to4096 on the wire.
        elif signature==b'AFB1' and limit==4064:
            self.pipelined=False;self.block_size=4064;self.frame_size=4096
        else:raise RuntimeError('Unsupported animation transfer capabilities.')
        return r

    def close(self):
        if self.bulk:
            import usb.util
            try:usb.util.release_interface(self.device,self.bulk[0])
            finally:self.bulk=None
    def __del__(self):
        try:self.close()
        except Exception:pass
