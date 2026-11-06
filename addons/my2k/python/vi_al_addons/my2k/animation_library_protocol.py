# SPDX-License-Identifier: GPL-2.0-or-later
"""Animation selection over HID; file mutations only on a verified exported mount."""
from pathlib import Path
import hashlib,os,shutil,tempfile,time
from vi_al_addons.my2k.animation_codec import CrsReader,MAX_BYTES

def slot_name(slot):
    if type(slot) is not int or not 1 <= slot <= 10:
        raise ValueError('Choose animation slot 1–10.')
    return 'animation_%02d.CRS'%slot

class AnimationClient:
    def __init__(self,keyboard,clock=time.monotonic,sleep=time.sleep):
        self.keyboard,self.clock,self.sleep=keyboard,clock,sleep
        self.token=0
        self.uncertain=False
        self.rate_supported=False
        self.timing_supported=False
        self.test_supported=False

    def request(self,operation,token=0,payload=b''):
        if self.uncertain:
            raise RuntimeError('Animation transport is uncertain; reconnect before another request. No mutation was retried.')
        packet=bytes((253,237,operation,1,token))+payload
        if len(packet)>32:
            raise ValueError('Animation request too long.')
        try:
            if self.keyboard.dev.write(b'\0'+packet.ljust(32,b'\0'))!=33:
                raise RuntimeError('Short animation request.')
            r=bytes(self.keyboard.dev.read(32,timeout_ms=1500))
            if len(r)!=32 or r[:6]!=bytes((253,237,170,1,operation,token)):
                raise RuntimeError('Animation command unsupported, busy or rejected. New Main and AUX are required for selection.')
            return r
        except (OSError,RuntimeError,TypeError):
            self.uncertain=True
            raise

    def capabilities(self):
        r=self.request(0)
        if r[6:10]!=b'ANI1' or r[11:13]!=bytes((10,1)):
            raise RuntimeError('Unsupported animation capabilities.')
        if not r[10]:
            raise RuntimeError('Animation AUX not ready or not compatible. Wait and Refresh after both new images are installed.')
        self.rate_supported=bool(r[13]&1)
        self.timing_supported=bool(r[13]&2)
        self.test_supported=bool(r[13]&4)
        return dict(rate_supported=self.rate_supported,timing_supported=self.timing_supported,test_supported=self.test_supported,saved_rate=r[14],active_rate=r[15],save_pending=bool(r[16]),durable=bool(r[17]),saved_timing=r[18],active_timing=r[19],ready=bool(r[26])if r[25]==1 else True,restore_state=r[27]if r[25]==1 else None)

    def wait_ready(self):
        deadline=self.clock()+8
        while True:
            try:
                if self.capabilities().get('ready',True):return
            except RuntimeError as e:
                if 'AUX not ready'not in str(e):raise
            if self.clock()>=deadline:
                raise RuntimeError('Animation startup is not ready; no operation was sent. Wait and try again.')
            self.sleep(.025)

    def transact(self,op,arg=0,part=0):
        if op not in (9,10,11,12) or not 0<=arg<=255 or not 0<=part<=3 or(op==11 and(not self.rate_supported or arg not in(0,30,60)or part>(1 if self.timing_supported else 0)or(not arg and part)))or(op==12 and(not self.test_supported or arg not in(0,1,2)or part)):
            raise ValueError('Invalid animation command.')
        self.wait_ready()
        self.token=self.token%255+1
        self.request(1,self.token,bytes((op,arg,part)))
        deadline=self.clock()+8
        while self.clock()<deadline:
            r=self.request(2,self.token)
            if r[6] in (2,3):
                response=r[8:16]
                if response[0]!=op or response[2]!=arg:
                    self.uncertain=True
                    raise RuntimeError('Animation reply does not match the request.')
                if r[6]==3:
                    if op==10 and r[7]==3:
                        return None
                    raise RuntimeError('AUX rejected the animation request (error %d).'%r[7])
                return response
            if r[6]!=1:
                raise RuntimeError('Animation request state is invalid.')
            self.sleep(.025)
        self.uncertain=True
        raise RuntimeError('Animation completion timed out. No selection was retried.')

    def selection(self,action=0):
        r=self.transact(9,action)
        if r[4]>10 or (1<=action<=10 and r[4]!=action):
            raise RuntimeError('Animation selection readback differs from the requested slot.')
        return dict(active=r[4],mask=r[5]|r[6]<<8)

    def frame_rate(self,target=None,timing=None):
        if target is not None and(type(target)is not int or target not in(30,60)):
            raise ValueError('Choose30or60FPS.')
        self.capabilities()
        if not self.rate_supported:raise RuntimeError('Playback-rate control requires matching Main and AUX firmware.')
        if timing is not None and(type(timing)is not int or timing not in(0,1)or target is None):
            raise ValueError('Timing is0(original)or1(fixed),and requires a target rate.')
        if timing is not None and not self.timing_supported:raise RuntimeError('Separate GIF timing requires newer Main and AUX firmware.')
        if target is not None and timing is None and self.timing_supported:timing=self.transact(11,0)[6]
        r=self.transact(11,0 if target is None else target,0 if timing is None else timing)
        if r[4]not in(30,60)or r[5]!=60 or(target is not None and r[4]!=target):
            raise RuntimeError('Playback-rate acknowledgement differs from the request.')
        active=r[4]
        policy=r[6]if self.timing_supported else 1
        if policy not in(0,1)or(timing is not None and policy!=timing):raise RuntimeError('GIF timing acknowledgement differs from the request.')
        if target is not None:
            check=self.transact(11,0)
            if check[4]!=active or(self.timing_supported and check[6]!=policy):raise RuntimeError('Playback-rate/timing readback differs.')
            deadline=self.clock()+5
            while True:
                status=self.capabilities()
                if status['active_rate']!=active or status['saved_rate']!=active:
                    raise RuntimeError('Main/AUX playback-rate state differs after acknowledgement.')
                if self.timing_supported and(status['active_timing']!=policy or status['saved_timing']!=policy):
                    raise RuntimeError('Main/AUX GIF timing state differs after acknowledgement.')
                if status['durable']and not status['save_pending']:break
                if self.clock()>=deadline:raise RuntimeError('Rate applied, but persistent save was not confirmed. No SET was retried.')
                self.sleep(.025)
        return dict(active=active,timing=policy,timing_supported=self.timing_supported,test_supported=self.test_supported,persistent=target is not None)

    def original_speed(self):
        """Explicit Save/Play only. Avoid rewriting an already-saved policy."""
        caps=self.capabilities()
        if not caps['timing_supported']:
            raise RuntimeError('Original GIF timing requires matching Main and AUX firmware.')
        if (caps['active_timing'],caps['saved_timing'],caps['active_rate'],caps['saved_rate'])==(0,0,60,60):
            return dict(active=60,timing=0,persistent=caps['durable'] and not caps['save_pending'])
        return self.frame_rate(60,0)

    def display_test(self,action=2):
        if type(action)is not int or action not in(0,1,2):raise ValueError('Test action is stop0,start1orGET2.')
        self.capabilities()
        if not self.test_supported:raise RuntimeError('Display Test requires matching Main and AUX firmware.')
        r=self.transact(12,action)
        if r[4]not in(0,1)or(action<2 and r[4]!=action):raise RuntimeError('Display-test acknowledgement differs.')
        if action<2:
            check=self.transact(12,2)
            if check[4]!=r[4]:raise RuntimeError('Display-test readback differs.')
            r=check
        return dict(active=bool(r[4]),FPS=(r[5]|r[6]<<8)/10,error=bool(r[7]),temporary=True)

    def info(self,slot):
        if not 0<=slot<=10:
            raise ValueError('Invalid animation slot.')
        r=self.transact(10,slot,0)
        if r is None:
            return None
        size=int.from_bytes(r[4:8],'little')
        alias=b''.join(self.transact(10,slot,part)[4:8]for part in (1,2,3)).split(b'\0')[0].decode('ascii')
        if not 20<size<=MAX_BYTES or not alias or len(alias)>12 or any(c in alias for c in '/\\:'):
            raise RuntimeError('Invalid animation file metadata.')
        return dict(slot=slot,size=size,alias=alias,name=slot_name(slot)if slot else alias)

    def download(self,info,destination,progress=None,cancelled=None):
        handle=self.keyboard.open_anim_file(info['alias'],True)
        if handle==255:
            raise RuntimeError('Could not open the keyboard animation for preview.')
        closed=False
        destination=Path(destination)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='.my2k-preview-',delete=False)as f:
                temporary=Path(f.name)
                offset=0
                while offset<info['size']:
                    if cancelled and cancelled():
                        raise RuntimeError('Preview download cancelled.')
                    requested=min(24,info['size']-offset)
                    data=self.keyboard.read_anim_file(handle,offset,requested)
                    if not data or len(data)>requested:
                        raise RuntimeError('Keyboard animation read failed at byte%d.'%offset)
                    f.write(data);offset+=len(data)
                    if progress:
                        progress(offset*100//info['size'])
            if not self.keyboard.close_anim_file(handle):
                raise RuntimeError('Could not close the preview file.')
            closed=True
            with CrsReader(temporary,require_my2k=True):
                pass
            os.replace(temporary,destination)
        finally:
            if not closed:
                try:self.keyboard.close_anim_file(handle)
                except (OSError,RuntimeError,ValueError):pass
            if temporary:temporary.unlink(missing_ok=True)

def verified_mount(root):
    """Require the root of a writable FAT mount on this custom keyboard's USB export."""
    root=Path(root).resolve()
    from PyQt5.QtCore import QStorageInfo
    volume=QStorageInfo(str(root))
    if (not volume.isValid() or not volume.isReady() or volume.isReadOnly() or
            Path(volume.rootPath()).resolve()!=root or bytes(volume.fileSystemType()).lower() not in (b'vfat',b'msdos')):
        raise ValueError('Choose the root of the mounted, writable MY-2K FAT asset drive—not ASTRO BOOT.')
    dev=root.stat().st_dev
    node=(Path('/sys/dev/block')/('%d:%d'%(os.major(dev),os.minor(dev)))).resolve(strict=True)
    for p in (node,*node.parents):
        if(p/'idVendor').is_file()and(p/'idProduct').is_file():
            if (p/'idVendor').read_text().strip().lower()=='4d58'and(p/'idProduct').read_text().strip().lower()=='f1fc':
                return root
            break
    raise ValueError('This mount is not the MY-2K custom storage-export device (4d58:f1fc).')

def available_mounts():
    from PyQt5.QtCore import QStorageInfo
    result=[]
    for volume in QStorageInfo.mountedVolumes():
        if bytes(volume.fileSystemType()).lower()not in(b'vfat',b'msdos'):
            continue
        try:result.append(verified_mount(volume.rootPath()))
        except (OSError,ValueError,KeyError):pass
    return result

class MountedLibrary:
    def __init__(self,root,verify=verified_mount):
        self.root,self.verify=Path(root),verify
        self.verify(self.root)

    def files(self):
        self.verify(self.root)
        result=[]
        for slot in range(1,11):
            p=self.root/slot_name(slot)
            if p.is_file():
                try:
                    with CrsReader(p,require_my2k=True)as movie:result.append(dict(slot=slot,name=p.name,size=movie.size,path=str(p)))
                except (OSError,ValueError):result.append(dict(slot=slot,name=p.name,size=p.stat().st_size,path=str(p),invalid=True))
        return result

    def upload(self,source,slot,progress=None,cancelled=None):
        self.verify(self.root)
        with CrsReader(source,require_my2k=True)as movie:size=movie.size
        if shutil.disk_usage(self.root).free<size+65536:
            raise ValueError('Not enough free space to stage this animation without truncating the current slot.')
        destination=self.root/slot_name(slot)
        with tempfile.NamedTemporaryFile(dir=self.root,prefix='.MY2K-upload-',delete=False)as output:
            temp=Path(output.name)
            try:
                with open(source,'rb')as f:
                    completed=0
                    while True:
                        if cancelled and cancelled():raise RuntimeError('Upload cancelled; original slot was not replaced.')
                        data=f.read(65536)
                        if not data:break
                        output.write(data);completed+=len(data)
                        if progress:progress(completed*100//size)
                output.flush();os.fsync(output.fileno())
                with CrsReader(temp,require_my2k=True):pass
                def digest(p):
                    with open(p,'rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
                if digest(source)!=digest(temp):raise RuntimeError('Staged animation readback differs; current slot preserved.')
                self.verify(self.root)
                os.replace(temp,destination)
                # Flush directory/device metadata before reporting completion.
                fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
                return str(destination)
            finally:temp.unlink(missing_ok=True)

    def delete(self,slot):
        self.verify(self.root)
        (self.root/slot_name(slot)).unlink()
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def move(self,source_slot,target_slot):
        self.verify(self.root)
        source=self.root/slot_name(source_slot);target=self.root/slot_name(target_slot)
        if source_slot==target_slot:
            raise ValueError('Choose a different destination slot.')
        with CrsReader(source,require_my2k=True):pass
        os.replace(source,target)
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return str(target)
