import builtins,json,os,time,traceback
from pathlib import Path
from PyQt5.QtCore import QTimer,QPoint
from PyQt5.QtWidgets import QMessageBox,QWidget
root=Path(os.environ['COMPARE_OUT']);started=time.monotonic();stage=0;ready_at=None
report={};WINDOW.showMaximized()
def tick():
 global stage,ready_at
 try:
  assert time.monotonic()-started<110,'Hardware check timed out'
  assert not [w for w in APP.topLevelWidgets()if isinstance(w,QMessageBox)and w.isVisible()]
  state=builtins.vi_al_fault
  if stage==0:
   assert WINDOW.autorefresh.current_device is None
   assert 'verify the keyboard layout' in WINDOW.statusBar().currentMessage()
   assert state['corruptions']==2,state
   report['permanent_corruption']='Inline error, no dialog, partial connection closed'
   state['mode']='once';stage=1
   WINDOW.on_click_refresh()
  elif stage==1:
   dev=WINDOW.autorefresh.current_device
   if dev is None:QTimer.singleShot(100,tick);return
   assert state['corruptions']==3,state
   assert WINDOW.statusBar().currentMessage()==''
   report['transient_corruption']='Read-only full retry succeeded on physical keyboard'
   items=[WINDOW.combobox_devices.itemText(i)for i in range(WINDOW.combobox_devices.count())]
   fat=next(i for i,text in enumerate(items)if 'IBM Model F AT'in text)
   if WINDOW.combobox_devices.currentIndex()!=fat:WINDOW.combobox_devices.setCurrentIndex(fat)
   tabs=[WINDOW.tabs.tabText(i)for i in range(WINDOW.tabs.count())]
   WINDOW.tabs.setCurrentIndex(tabs.index('Calibration'));stage=2;ready_at=time.monotonic()
  elif stage==2:
   c=WINDOW.xwhatsit
   if c.client is None or c.worker is not None or c.pending is not None or time.monotonic()-ready_at<2:
    QTimer.singleShot(100,tick);return
   assert not hasattr(c,'recalibrate')
   button=c.defaults;group=c.calibration_controls
   center=button.mapTo(group,button.rect().center()).x()
   assert abs(center-group.rect().center().x())<=4
   assert all(group.layout().rowMinimumHeight(3+i*3)>=8 for i in range(len(c.sliders)-1))
   report.update(version=APP.applicationVersion(),center_offset=center-group.rect().center().x(),slider_count=len(c.sliders),samples=len(c.last_samples))
   assert WINDOW.grab().save(str(root/'fat-calibration.png'))
   c.timer.stop();stage=3
   (root/'ready.json').write_text(json.dumps(report,indent=2))
  elif stage==3:
   if (root/'finish').exists():
    if not all(s.before_close()for s in WINDOW.addon_manager.sessions):QTimer.singleShot(100,tick);return
    (root/'result.json').write_text(json.dumps(report,indent=2));WINDOW.close();APP.exit(0);return
  QTimer.singleShot(100,tick)
 except Exception:
  traceback.print_exc()
  (root/'error.txt').write_text(traceback.format_exc())
  for s in WINDOW.addon_manager.sessions:s.before_close()
  APP.exit(1)
QTimer.singleShot(200,tick)
