"""Binary conversion and library file operations in temporary directories only."""
import os,sys,struct,tempfile,unittest,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from PyQt5.QtWidgets import QApplication,QWidget
from vi_al_addons.my2k.animation_codec import CrsReader,convert_animation,HEADER
from vi_al_addons.my2k.animation_library_protocol import AnimationClient,MountedLibrary,slot_name,verified_mount
from vi_al_addons.my2k.animation import Animation,KEYBOARD_FORMATS
from vi_al_addons.my2k.animation_library import AnimationLibrary

def gif():
    b=b'GIF89a'+struct.pack('<HHBBB',1,1,0x80,0,0)+bytes((255,0,0,0,0,255))
    for c,delay in[(0,5),(1,9)]:b+=b'!\xf9\x04\0'+struct.pack('<H',delay)+b'\0\0'+b',\0\0\0\0\x01\0\x01\0\0\x02\x02'+bytes((0x44+8*c,1))+b'\0'
    return b+b';'

class CodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance()or QApplication([])
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.src=self.root/'source.gif';self.src.write_bytes(gif());self.dst=self.root/'clip.CRS'
    def tearDown(self):self.temp.cleanup()
    def test_gif_frames_timing_endian_and_streamed_preview(self):
        result=convert_animation(self.src,self.dst);self.assertEqual(result['frames'],2)
        raw=self.dst.read_bytes();self.assertEqual(HEADER.unpack(raw[:20]),(b'ANIM',20,24,65560,128,128,2,2));self.assertEqual(raw[24:26],b'\xf8\0');self.assertEqual(raw[32792:32794],b'\0\x1f')
        with CrsReader(self.dst,True)as c:self.assertEqual(c.delays,(50,90));self.assertEqual(c.frame(0).pixelColor(0,0).name(),'#ff0000');self.assertEqual(c.frame(1).pixelColor(0,0).name(),'#0000ff');self.assertFalse(hasattr(c,'images'))
    def test_corrupt_header_size_offset_and_truncation_rejected(self):
        convert_animation(self.src,self.dst);raw=self.dst.read_bytes()
        for offset in (0,4,6,8,12,16,18):
            bad=bytearray(raw);bad[offset]^=1;self.dst.write_bytes(bad)
            with self.assertRaises(ValueError):CrsReader(self.dst,True)
        self.dst.write_bytes(raw[:-1])
        with self.assertRaises(ValueError):CrsReader(self.dst,True)
    def test_cancel_and_invalid_source_preserve_existing_destination(self):
        self.dst.write_bytes(b'original')
        with self.assertRaises(RuntimeError):convert_animation(self.src,self.dst,cancelled=lambda:True)
        self.assertEqual(self.dst.read_bytes(),b'original');self.src.write_bytes(b'invalid')
        with self.assertRaises(ValueError):convert_animation(self.src,self.dst)
        self.assertEqual(self.dst.read_bytes(),b'original')
    def test_converted_input_roundtrip_and_non_my2k_rejected_for_upload(self):
        convert_animation(self.src,self.dst);out=self.root/'copy.CRS';convert_animation(self.dst,out);self.assertEqual(out.read_bytes(),self.dst.read_bytes())
        convert_animation(self.src,out,60,60)
        with self.assertRaises(ValueError):CrsReader(out,True)
    def test_mount_operations_only_touch_the_selected_slot(self):
        convert_animation(self.src,self.dst);drive=self.root/'drive';drive.mkdir();mew=drive/'Mew Close Up.CRS';mew.write_bytes(b'Mew protected');oled=drive/'BW_TEXT.ABW';oled.write_bytes(b'OLED protected')
        checks=[];lib=MountedLibrary(drive,verify=lambda root:checks.append(root));target=lib.upload(self.dst,10)
        self.assertEqual(Path(target).name,'animation_10.CRS');self.assertEqual(Path(target).read_bytes(),self.dst.read_bytes());self.assertEqual(len(lib.files()),1)
        with self.assertRaises(RuntimeError):lib.upload(self.dst,10,cancelled=lambda:True)
        self.assertEqual(Path(target).read_bytes(),self.dst.read_bytes());lib.move(10,3);self.assertFalse(Path(target).exists());self.assertEqual((drive/slot_name(3)).read_bytes(),self.dst.read_bytes());lib.delete(3);self.assertFalse((drive/slot_name(3)).exists());self.assertEqual(mew.read_bytes(),b'Mew protected');self.assertEqual(oled.read_bytes(),b'OLED protected');self.assertGreater(len(checks),3)
    def test_capacity_and_mount_verification_precede_writes(self):
        convert_animation(self.src,self.dst);lib=MountedLibrary(self.root,verify=lambda root:None)
        with patch('vi_al_addons.my2k.animation_library_protocol.shutil.disk_usage',return_value=SimpleNamespace(free=10)):
            with self.assertRaises(ValueError):lib.upload(self.dst,1)
        self.assertFalse((self.root/'animation_01.CRS').exists())
        with patch('PyQt5.QtCore.QStorageInfo')as volume:
            volume.return_value.isValid.return_value=True
            volume.return_value.isReady.return_value=True
            volume.return_value.isReadOnly.return_value=False
            volume.return_value.rootPath.return_value=str(self.root)
            volume.return_value.fileSystemType.return_value=b'ext4'
            with self.assertRaises(ValueError):verified_mount(self.root)
    def test_slot_bounds_and_default_converter(self):
        self.assertEqual(KEYBOARD_FORMATS[0]['name'],'MY-2K 100NG')
        for slot in (0,11,-1,True,'1'):
            with self.assertRaises(ValueError):slot_name(slot)
        self.assertEqual(slot_name(1),'animation_01.CRS');self.assertEqual(slot_name(10),'animation_10.CRS')
        page=Animation();root=QWidget();root.setLayout(page);self.assertEqual(page.library_page.format.currentText(),'MY-2K 100NG');page.library_page.source_preview.stop();page.library_page.device_preview.stop();root.deleteLater()
    def test_firmware_frame_limit_rejected_before_replacing_output(self):
        b=gif();header=b[:19];frame=b[19:-1][:23]
        # Repeat a complete image/control pair, keeping the tiny GIF bounded.
        pair=b[19:42]
        self.src.write_bytes(header+pair*513+b';');self.dst.write_bytes(b'previous')
        with self.assertRaisesRegex(ValueError,'512'):convert_animation(self.src,self.dst)
        self.assertEqual(self.dst.read_bytes(),b'previous')
    def test_source_preview_releases_external_file_and_uses_local_cache(self):
        page=AnimationLibrary(KEYBOARD_FORMATS)
        with patch('vi_al_addons.my2k.animation_library.QFileDialog.getOpenFileName',return_value=(str(self.src),'')):
            page.choose_source()
        self.assertEqual(page.source_name,self.src);self.assertNotEqual(page.source,self.src);self.assertEqual(page.source.parent,Path(page.cache.name))
        self.src.unlink();self.assertTrue(page.source.exists());convert_animation(page.source,self.dst)
        page.source_preview.stop();page.device_preview.stop();page.close();page.deleteLater()

class ProtocolTests(unittest.TestCase):
    def device(self):
        class Dev:
            def __init__(self):self.packets=[];self.timeout=False;self.active=1;self.wrong=False
            def write(self,p):
                self.packets.append(bytes(p));q=p[1:];r=bytearray(32);r[:6]=bytes((253,237,170,1,q[2],q[4]))
                if q[2]==0:r[6:13]=b'ANI1'+bytes((1,10,1))
                elif q[2]==1:self.op,self.arg,self.part=q[5:8]
                else:
                    r[6]=2;r[8:12]=bytes((self.op,22,self.arg,0));r[12]=9 if self.wrong else(self.arg or self.active);r[13]=1
                self.reply=bytes(r);return 33
            def read(self,*args,**kw):return []if self.timeout else self.reply
        k=SimpleNamespace(dev=Dev());return k,AnimationClient(k)
    def test_capability_and_selection_ack_readback(self):
        k,c=self.device();c.capabilities();self.assertEqual(c.selection(4)['active'],4);self.assertEqual([p[3]for p in k.dev.packets],[0,0,1,2])
        k,c=self.device();k.dev.wrong=True
        with self.assertRaises(RuntimeError):c.selection(4)
    def test_timeout_never_retries_selection(self):
        k,c=self.device();k.dev.timeout=True
        with self.assertRaises(RuntimeError):c.selection(4)
        self.assertEqual(len(k.dev.packets),1)
        with self.assertRaises(RuntimeError):c.selection(4)
        self.assertEqual(len(k.dev.packets),1)
    def test_preview_download_validation_and_cancel_preserves_local_file(self):
        with tempfile.TemporaryDirectory()as folder:
            p=Path(folder);(p/'in.gif').write_bytes(gif());convert_animation(p/'in.gif',p/'clip.CRS');raw=(p/'clip.CRS').read_bytes();closed=[]
            k=SimpleNamespace(open_anim_file=lambda *args:2,read_anim_file=lambda h,at,n:raw[at:at+n],close_anim_file=lambda h:closed.append(h)or True);c=AnimationClient(k);dest=p/'download.CRS';info=dict(alias='CLIP.CRS',size=len(raw))
            c.download(info,dest);self.assertEqual(dest.read_bytes(),raw)
            dest.write_bytes(b'preserved')
            with self.assertRaises(RuntimeError):c.download(info,dest,cancelled=lambda:True)
            self.assertEqual(dest.read_bytes(),b'preserved');self.assertEqual(closed,[2,2])

if __name__=='__main__':unittest.main()
