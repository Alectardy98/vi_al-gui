"""Source preview keeps original decoder pixels; device conversion stays separate."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage
from PyQt5.QtCore import Qt
from vi_al_addons.my2k.animation_library import AnimationLibrary,CropPreview
from vi_al_addons.my2k.animation import KEYBOARD_FORMATS
from vi_al_addons.my2k.animation_codec import convert_animation,CrsReader
app=QApplication.instance()or QApplication([])
class OriginalPreviewTests(unittest.TestCase):
 def test_full_resolution_image_stays_original_until_explicit_conversion(self):
  with tempfile.TemporaryDirectory()as folder:
   root=Path(folder);source=root/'wide.png';image=QImage(480,270,QImage.Format_RGB32);image.fill(Qt.red);self.assertTrue(image.save(str(source)))
   page=AnimationLibrary(KEYBOARD_FORMATS)
   try:
    page.resize(1024,700);page.show();app.processEvents()
    with patch('vi_al_addons.my2k.animation_library.QFileDialog.getOpenFileName',return_value=(str(source),''))as picker:page.choose_source()
    self.assertIn('Original GIFs and images',picker.call_args.args[3]);self.assertEqual(page.source_preview.image.size(),image.size());self.assertIn('480 × 270 source pixels',page.source_label.text());self.assertIn('(original)',page.source_label.text())
    rect=page.source_preview.geometry_for_image();self.assertAlmostEqual(rect.width()/rect.height(),480/270);self.assertGreater(rect.width(),128);self.assertGreater(rect.height(),128)
    page.source_preview.set_mode(1);self.assertEqual(page.source_preview.image.size(),image.size());self.assertEqual(page.source_preview.crop(),(105,0,270))
    output=root/'converted.CRS';convert_animation(page.source,output)
    with CrsReader(output,True)as reader:self.assertEqual((reader.width,reader.height),(128,128))
    self.assertEqual(page.source_preview.image.size(),image.size())
    with patch('vi_al_addons.my2k.animation_library.QFileDialog.getOpenFileName',return_value=(str(output),'')):page.choose_source()
    self.assertIn('128 × 128 source pixels',page.source_label.text());self.assertIn('(already converted)',page.source_label.text())
   finally:page.source_preview.stop();page.device_preview.stop();page.close();page.deleteLater()
 def test_gif_decoder_is_not_scaled_to_keyboard_dimensions(self):
  from test_animation_library import gif
  with tempfile.TemporaryDirectory()as folder:
   p=Path(folder)/'source.gif';p.write_bytes(gif());preview=CropPreview()
   try:
    with patch('vi_al_addons.my2k.animation_library.CrsReader',side_effect=AssertionError('Original GIF passed through CRS decoder')):preview.load(p)
    app.processEvents();self.assertEqual((preview.image.width(),preview.image.height()),(1,1));self.assertTrue(preview.movie.scaledSize().isEmpty());self.assertIsNone(preview.reader)
   finally:preview.stop();preview.close();preview.deleteLater()
 def test_repeat_preview_cached_but_refresh_epoch_forces_actual_download(self):
  with tempfile.TemporaryDirectory()as folder:
   root=Path(folder);source=root/'source.png';image=QImage(8,8,QImage.Format_RGB32);image.fill(Qt.blue);image.save(str(source));asset=root/'asset.CRS';convert_animation(source,asset)
   page=AnimationLibrary(KEYBOARD_FORMATS);page.keyboard=object();page.items={2:dict(slot=2,size=asset.stat().st_size)};page.populate();page.files.setCurrentRow(1)
   jobs=[]
   page.run_job=lambda title,job,done,**kw:(jobs.append(title),done(job(lambda n:None,lambda:False)))
   def download(info,destination,*args,**kw):Path(destination).write_bytes(asset.read_bytes())
   try:
    with patch('vi_al_addons.my2k.animation_library.AnimationFilesClient')as client:
     client.return_value.download.side_effect=download;page.preview();page.preview();self.assertEqual(client.return_value.download.call_count,1);self.assertIn('cached',page.status.text())
     page.invalidate_preview_cache();page.preview();self.assertEqual(client.return_value.download.call_count,2)
     page.rebuild(object());self.assertFalse(page.preview_cache)
   finally:page.source_preview.stop();page.device_preview.stop();page.close();page.deleteLater()
if __name__=='__main__':unittest.main()
