# SPDX-License-Identifier: GPL-2.0-or-later
"""AFS1 AUX-owned slot service. No mounted filesystem, raw sector writes or retries."""
from pathlib import Path
import os,secrets,struct,tempfile,zlib,time
from vi_al_addons.my2k.animation_codec import CrsReader,HEADER
from vi_al_addons.my2k.animation_library_protocol import slot_name

ERRORS={3:'Invalid animation request.',4:'Storage is busy or in maintenance mode. Return to keyboard mode first.',5:'AUX filesystem operation failed.',6:'This slot is empty.',7:'The destination exists; replacement was not authorized.',8:'Animation size, format or checksum verification failed.',9:'An interrupted transaction needs maintenance inspection. Temporary/backup files were preserved.',11:'Not enough free storage for a staged upload and safety margin.',10:'AUX completion is uncertain. Do not retry the mutation; inspect storage before proceeding.'}

class AnimationFileError(RuntimeError):
    def __init__(self,status):
        self.status=status
        super().__init__(ERRORS.get(status,'Unknown animation error %d.'%status))

class AnimationFilesClient:
    def __init__(self,keyboard):self.keyboard=keyboard;self.token=secrets.randbelow(255)+1;self.uncertain=False;self.ready=False;self.fast=None
    def request(self,op,slot=0,offset=0,data=b'',replace=False):
        if self.uncertain:raise RuntimeError('Transport uncertain; no operation was retried. Reconnect before inspecting the result.')
        if op and op!=10 and not self.ready:self.capabilities()
        if self.fast and op!=10:
            self.token=self.token%255+1
            try:r=self.fast.request(op,self.token,slot,offset,data,replace)
            except Exception:self.uncertain=True;raise
            if r[6]!=2:
                if r[6]==6 and op==1:return None
                if r[6]==10:self.uncertain=True
                raise AnimationFileError(r[6])
            return r
        if op not in range(9)and op!=10:raise ValueError('Unsupported animation operation.')
        if not 0<=slot<=10 or not 0<=offset<=0xffffffff or len(data)>20:raise ValueError('Animation request exceeds bounds.')
        self.token=self.token%255+1
        q=bytes((253,238,op,1,self.token,slot,int(replace),len(data)))+struct.pack('<I',offset)+data
        try:
            if self.keyboard.dev.write(b'\0'+q.ljust(32,b'\0'))!=33:raise RuntimeError('Short animation request.')
            r=bytes(self.keyboard.dev.read(32,timeout_ms=3500))
            if len(r)!=32 or r[:6]!=bytes((253,238,170,1,op,self.token))or r[7]>20:
                raise RuntimeError('Animation file protocol is unsupported or the reply does not match. Install both matching Main and AUX candidates.')
        except (OSError,TypeError,RuntimeError):self.uncertain=True;raise
        if r[6]!=2:
            if r[6]==6 and op==1:return None
            if r[6]==10:self.uncertain=True
            raise AnimationFileError(r[6])
        return r
    def _read_request(self,op,slot=0,offset=0,data=b''):
        if op not in(0,1,2):raise ValueError('Only read-only requests can wait for ownership.')
        deadline=time.monotonic()+8
        while True:
            try:return self.request(op,slot,offset,data)
            except AnimationFileError as error:
                if error.status!=4 or time.monotonic()>=deadline:raise
                time.sleep(.025)
    def capabilities(self):
        if self.fast:return self.capability_reply
        r=self._read_request(0)
        if r[12:18]!=b'AFS1'+bytes((10,20)):raise RuntimeError('AUX does not support AFS1 animation files.')
        if r[18]:raise RuntimeError('Maintenance mode owns the storage. Eject it and return to keyboard mode.')
        if r[19]&2:raise RuntimeError('AUX could not close a storage file. File changes and maintenance export are blocked. Preserve your PC backup and stop this test; do not retry writes.')
        if r[19]&1:raise RuntimeError('An unfinished upload owns storage. Cancel it in the original window, or wait 60 seconds and load the list again. Retained temporary files can be inspected with Maintenance.')
        self.ready=True
        self.capability_reply=r
        if r[8:12]in(b'AFB1',b'AFB2') and self.fast is None and getattr(self.keyboard,'usb_descriptor',getattr(self.keyboard,'desc',{})).get('path'):
            from vi_al_addons.my2k.animation_fast_transport import FastAnimationTransport
            candidate=FastAnimationTransport(self.keyboard)
            self.token=self.token%255+1
            candidate.capabilities(self.token)
            self.fast=candidate
        return r
    def info(self,slot):
        r=self._read_request(1,slot)
        if r is None:return None
        size=int.from_bytes(r[8:12],'little')
        if not 32790<=size<=16778260:raise RuntimeError('Invalid stored animation size.')
        return dict(slot=slot,size=size,name=slot_name(slot)if slot else'Current animation.CRS',stored_crc=int.from_bytes(r[16:20],'little')if self.fast and r[7]&1 else None)
    def download(self,info,destination,progress=None,cancelled=None,preview_ready=None):
        destination=Path(destination);temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='.my2k-preview-',delete=False)as out:
                temporary=Path(out.name);at=0;last_progress=-1;preview_threshold=None;preview_sent=False
                while at<info['size']:
                    if cancelled and cancelled():raise RuntimeError('Preview download cancelled.')
                    n=min(self.fast.read_size if self.fast else 20,info['size']-at);r=self._read_request(2,info['slot'],at,b'\0'*n)
                    count=int.from_bytes(r[30:32],'little')if self.fast else r[7]
                    if count!=n or int.from_bytes(r[8:12],'little')!=at:raise RuntimeError('Animation read offset/length mismatch.')
                    payload=r[32:32+n]if self.fast else r[12:12+n]
                    if preview_ready and at==0:
                        magic,header,offset,size,width,height,depth,frames=HEADER.unpack_from(payload)
                        preview_threshold=offset+width*height*depth*min(frames,2)
                    out.write(payload);at+=n
                    if preview_ready and not preview_sent and at>=preview_threshold:
                        out.flush()
                        with CrsReader(temporary,True,partial=True)as movie:
                            if movie.size!=info['size']:raise RuntimeError('Preview header differs from keyboard file size.')
                        preview_ready(dict(temporary=str(temporary),complete=str(destination)));preview_sent=True
                    value=at*100//info['size']
                    if progress and value!=last_progress:progress(value);last_progress=value
                out.flush();os.fsync(out.fileno())
            with CrsReader(temporary,True):pass
            os.replace(temporary,destination)
        finally:
            if temporary:temporary.unlink(missing_ok=True)
    def upload(self,source,slot,replace=False,progress=None,cancelled=None,skip_unchanged=True):
        source=Path(source)
        with CrsReader(source,True)as movie:size=movie.size
        checksum=0
        with source.open('rb')as f:
            for part in iter(lambda:f.read(65536),b''):checksum=zlib.crc32(part,checksum)
        if not self.ready:self.capabilities()
        self.last_verification=None
        if cancelled and cancelled():raise RuntimeError('Upload cancelled; the previous slot was retained.')
        if self.fast and replace and skip_unchanged:
            existing=self.info(slot)
            if existing and existing['size']==size and existing.get('stored_crc')==checksum:
                self.last_verification=dict(size=size,crc=checksum,unchanged=True)
                if progress:progress(100)
                return 'anamations/'+slot_name(slot)
        self.request(3,slot,size,struct.pack('<I',checksum),replace)
        active=True
        try:
            at=0;last_progress=-1
            with source.open('rb')as f:
                for data in iter(lambda:f.read(self.fast.block_size if self.fast else 20),b''):
                    if cancelled and cancelled():raise RuntimeError('Upload cancelled; the previous slot was retained.')
                    r=self.request(4,slot,at,data);at+=len(data)
                    if int.from_bytes(r[8:12],'little')!=at:raise RuntimeError('AUX upload progress differs from sent data.')
                    value=at*(95 if self.fast else 60)//size
                    if progress and value!=last_progress:progress(value);last_progress=value
            r=self.request(5,slot);active=False
            if int.from_bytes(r[8:12],'little')!=size:raise RuntimeError('AUX committed size differs from source.')
            if self.fast:
                if int.from_bytes(r[16:20],'little')!=checksum:
                    raise RuntimeError('Transfer verification CRC differs. Preserve the source.')
                self.last_verification=dict(size=size,crc=checksum,unchanged=False,stored_reread=not bool(r[7]&2))
                if progress:progress(100)
                return 'anamations/'+slot_name(slot)
            # Independent complete file readback verifies stored bytes, not just the upload ACK.
            with tempfile.TemporaryDirectory(prefix='my2k-verify-')as folder:
                target=Path(folder)/'verify.CRS';info=self.info(slot)
                if not info or info['size']!=size:raise RuntimeError('Committed file metadata differs.')
                try:self.download(info,target,lambda n:progress(60+n*40//100)if progress else None,cancelled)
                except (RuntimeError,OSError,ValueError)as error:raise RuntimeError('The slot was saved, but readback did not finish: '+str(error)+'. Load the list before deciding whether to replace it.')from error
                actual=0
                with target.open('rb')as f:
                    for part in iter(lambda:f.read(65536),b''):actual=zlib.crc32(part,actual)
                if actual!=checksum:raise RuntimeError('Saved-file readback CRC differs. Do not delete the source.')
            return 'anamations/'+slot_name(slot)
        finally:
            if active and not self.uncertain:
                try:self.request(6,slot)
                except (RuntimeError,OSError):pass
    def clear(self,slot):self.request(7,slot)
    def import_legacy(self,replace=False):self.request(8,1,replace=replace)
    def maintenance(self):self.request(10)
