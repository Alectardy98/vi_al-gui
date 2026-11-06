#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual Qt widgets/handlers, offscreen and no device discovery."""
import os,sys,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from unittest.mock import patch
from vi_al_addons.my2k.aux_display import AuxDsiplay
WARNINGS=[]
from vi_al_addons.my2k import oled_config
from PyQt5.QtWidgets import QApplication,QWidget

class Client:
 def __init__(self):self.values=oled_config.decode_config(oled_config.encode_config('Saved message','MY2K'));self.calls=[]
 def capabilities(self):return dict(peer_ready=True,persistent=True)
 def read(self,refresh=False):return dict(self.values)
 def apply(self,**v):oled_config.decode_config(oled_config.encode_config(**v));self.values=dict(v);self.calls.append(dict(v));return dict(pending_save=False,durable=True)
 def sync_datetime(self,*date):self.date=date;return dict(state=2)
 def status(self):return dict(pending_save=False,durable=True)
class GuiTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  WARNINGS.clear();self.warning=patch('vi_al_addons.my2k.aux_display.QMessageBox.warning',side_effect=lambda *args:WARNINGS.append(args));self.warning.start();self.addCleanup(self.warning.stop);self.client=Client();self.original=oled_config.OledClient;oled_config.OledClient=lambda k:self.client
  self.ui=AuxDsiplay(None,None);self.root=QWidget();self.root.setLayout(self.ui)
  self.ui.keyboard=type('K',(),{'amk_aux_display':{'width':70,'height':40}})();self.ui.reset_ui()
 def tearDown(self):oled_config.OledClient=self.original;self.ui.save_timer.stop();self.ui.ready_timer.stop();self.root.deleteLater()
 def test_device_values_loaded_without_hello_default(self):self.assertEqual(self.ui.ad_preview.get_pixmap_width(),72);self.assertEqual(self.ui.ad_text.toPlainText(),'Saved message');self.assertEqual(self.ui.typing_label.toPlainText(),'MY2K')
 def test_message_bitmap_and_font_transmitted(self):
  self.ui.ad_text.setPlainText('Release 1');self.assertTrue(self.ui.on_sync_clicked());v=self.client.calls[-1];self.assertEqual(v['message'],'Release 1');self.assertEqual(len(v['bitmap']),360);self.assertTrue(any(v['bitmap']));self.assertEqual(v['font_size'],8)
 def test_blank_label_and_typing_toggle(self):
  self.ui.typing_label.setPlainText('');self.assertTrue(self.ui.on_sync_clicked());self.assertEqual(self.client.values['label'],'');self.ui.typing_toggle.setChecked(False);self.assertTrue(self.ui.on_typing_update());self.assertTrue(self.ui.on_sync_clicked());self.assertFalse(self.client.values['typing'])
 def test_clock_happy_exclusion(self):
  self.ui.happy_toggle.setChecked(True);self.assertTrue(self.ui.on_happy_update());self.assertEqual(self.client.calls,[]);self.assertTrue(self.ui.on_sync_clicked());self.assertTrue(self.client.values['happy']);self.ui.clock_toggle.setChecked(True);self.assertTrue(self.ui.on_clock_update());self.assertTrue(self.ui.on_sync_clicked());self.assertTrue(self.client.values['clock']);self.assertFalse(self.client.values['happy']);self.assertFalse(self.ui.happy_toggle.isChecked());self.assertEqual(len(self.client.date),7)
 def test_font_clipping_and_invalid_character_rejected(self):
  self.ui.ad_text.setPlainText('A'*59);self.assertFalse(self.ui.on_sync_clicked());self.assertEqual(self.client.calls,[])
  self.ui.ad_text.setPlainText('é');self.assertFalse(self.ui.on_sync_clicked());self.assertTrue(WARNINGS)
 def test_maximum_pixel_fitting_message(self):
  text='\n'.join(['A'*14]*4);self.assertEqual(len(text),59);self.ui.ad_text.setPlainText(text);self.assertTrue(self.ui.on_sync_clicked())
 def test_empty_message_draws_blank(self):
  self.ui.ad_text.setPlainText('');self.assertTrue(self.ui.on_sync_clicked());self.assertFalse(any(self.client.values['bitmap']))
 def test_sync_preserves_configuration(self):
  before=dict(self.client.values);self.assertTrue(self.ui.on_dt_btn());self.assertEqual(before,self.client.values);self.assertEqual(len(self.client.date),7)
if __name__=='__main__':unittest.main()
