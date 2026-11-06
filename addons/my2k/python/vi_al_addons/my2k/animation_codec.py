# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded CRS conversion/preview. RGB565 pixels are big endian on disk."""
from array import array
from pathlib import Path
import os
import struct
import sys
import tempfile
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QImageReader, QPainter

HEADER = struct.Struct('<4sHHIHHHH')
MY2K_WIDTH = MY2K_HEIGHT = 128
MAX_BYTES = 128*1024*1024


class PreviewFramePending(RuntimeError):
    """A complete frame has not arrived in a growing host preview file yet."""


class CrsReader:
    """Keep a file and its delay table, not an entire decoded movie, in RAM."""
    def __init__(self, filename, require_my2k=False, partial=False):
        self.file = open(filename, 'rb')
        try:
            raw = self.file.read(HEADER.size)
            if len(raw) != HEADER.size:
                raise ValueError('Truncated animation header.')
            magic, header, offset, size, width, height, depth, frames = HEADER.unpack(raw)
            actual = os.fstat(self.file.fileno()).st_size
            if magic not in (b'ANIM', b'ABKG', b'AUXI', b'AMFT', b'ASTS') or header != HEADER.size or depth != 2 or not frames or not 1 <= width <= 240 or not 1 <= height <= 240:
                raise ValueError('Unsupported animation header or dimensions.')
            if require_my2k and (magic != b'ANIM' or (width,height) != (128,128)):
                raise ValueError('MY-2K requires a 128 × 128 RGB565 CRS animation.')
            if require_my2k and frames > 512:
                raise ValueError('The current MY-2K playback engine supports at most 512 frames per animation.')
            if offset != header+2*frames or size != offset+width*height*2*frames or (actual!=size and(not partial or actual<offset or actual>size)) or size > MAX_BYTES:
                raise ValueError('Animation offsets, frame count or file size do not match.')
            self.width,self.height,self.frames,self.offset,self.size,self.magic = width,height,frames,offset,size,magic
            self.delays = struct.unpack('<'+'H'*frames, self.file.read(2*frames))
            self.frame_bytes = width*height*2
            self.partial=bool(partial)
        except Exception:
            self.file.close()
            raise

    def frame(self, index):
        if not 0 <= index < self.frames:
            raise ValueError('Frame index out of range.')
        if self.partial and self.offset+(index+1)*self.frame_bytes>os.fstat(self.file.fileno()).st_size:
            raise PreviewFramePending('Preview frame is still downloading.')
        self.file.seek(self.offset+index*self.frame_bytes)
        raw = self.file.read(self.frame_bytes)
        if len(raw) != self.frame_bytes:
            raise ValueError('Animation file changed or was truncated.')
        pixels = array('H')
        pixels.frombytes(raw)
        if sys.byteorder == 'little':
            pixels.byteswap()
        return QImage(pixels.tobytes(),self.width,self.height,self.width*2,QImage.Format_RGB16).copy()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self,*unused):
        self.close()


def crop_frame(image,crop):
    if crop is None:return image
    if len(crop)!=3:raise ValueError('Invalid square crop.')
    x,y,side=map(int,crop)
    if side<1 or x<0 or y<0 or x+side>image.width()or y+side>image.height():
        raise ValueError('The crop must remain inside every source frame.')
    return image.copy(x,y,side,side)


def fitted_frame(image, width, height):
    if image.isNull():
        raise ValueError('Image decoder returned an empty frame.')
    scaled = image.scaled(width,height,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    target = QImage(width,height,QImage.Format_RGB16)
    target.fill(Qt.black)
    painter = QPainter(target)
    painter.drawImage((width-scaled.width())//2,(height-scaled.height())//2,scaled)
    painter.end()
    pixels = array('H')
    stride = target.bytesPerLine()
    raw = target.constBits().asstring(target.sizeInBytes())
    for y in range(height):
        pixels.frombytes(raw[y*stride:y*stride+width*2])
    if sys.byteorder == 'little':
        pixels.byteswap()
    return pixels.tobytes()


def convert_animation(source, destination, width=128, height=128, magic=b'ANIM', progress=None, cancelled=None, crop=None):
    """Stream to local temporary files; replace destination only after validation."""
    if not 1 <= width <= 240 or not 1 <= height <= 240 or magic not in (b'ANIM',b'ABKG',b'AUXI',b'AMFT',b'ASTS'):
        raise ValueError('Unsupported output format.')
    destination = Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    source = Path(source)
    crs = None
    try:
        if source.suffix.lower() in ('.crs','.anm','.sml','.bkg','.sts','.aux'):
            crs = CrsReader(source)
            total = crs.frames
        else:
            reader = QImageReader(str(source))
            if not reader.canRead():
                raise ValueError('Cannot decode the selected image or GIF.')
            total = reader.imageCount()
            if total < 1:
                raise ValueError('The decoder could not determine a bounded frame count.')
        offset = HEADER.size+2*total
        size = offset+total*width*height*2
        if magic == b'ANIM' and (width,height) == (128,128) and total > 512:
            raise ValueError('MY-2K currently supports at most 512 frames per animation. Trim the GIF before converting.')
        if offset > 65535 or size > MAX_BYTES:
            raise ValueError('Animation exceeds the CRS frame-table or 128 MiB limit.')
        with tempfile.TemporaryFile() as spool:
            delays=[];previous=None;input_frames=total
            for index in range(total):
                if cancelled and cancelled():
                    raise RuntimeError('Conversion cancelled; destination was not replaced.')
                image = crs.frame(index) if crs else reader.read()
                if image.isNull():
                    raise ValueError('GIF/image decoding failed before the last frame.')
                delay = crs.delays[index] if crs else reader.nextImageDelay() if total > 1 else 1000
                if not 0 <= delay <= 65535:
                    raise ValueError('A frame delay cannot be represented in CRS.')
                delay=delay or 10
                pixels=fitted_frame(crop_frame(image,crop),width,height)
                if delays and pixels==previous and delays[-1]+delay<=65535:
                    delays[-1]+=delay
                else:
                    delays.append(delay);spool.write(pixels);previous=pixels
                if progress:
                    progress((index+1)*100//total)
            total=len(delays);offset=HEADER.size+2*total;size=offset+total*width*height*2
            with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='.my2k-convert-',delete=False) as output:
                temporary = Path(output.name)
                try:
                    output.write(HEADER.pack(magic,HEADER.size,offset,size,width,height,2,total))
                    output.write(struct.pack('<'+'H'*total,*delays))
                    spool.seek(0)
                    while True:
                        chunk=spool.read(65536)
                        if not chunk:
                            break
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                    with CrsReader(temporary):
                        pass
                    os.replace(temporary,destination)
                finally:
                    temporary.unlink(missing_ok=True)
        return dict(frames=total,input_frames=input_frames,duplicate_frames_removed=input_frames-total,bytes=size,width=width,height=height)
    finally:
        if crs:
            crs.close()
