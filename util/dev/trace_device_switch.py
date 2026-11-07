"""Record even transient standalone controls while changing selected keyboards."""
import json,os,time,traceback
from pathlib import Path
from PyQt5.QtCore import QEvent,QObject,QTimer,Qt
from PyQt5.QtWidgets import QWidget,QLabel,QAbstractButton,QMessageBox
from widgets.editor_container import EditorContainer

window=WINDOW;app=APP
root=Path(os.environ['VI_AL_VALIDATION_DIR']);root.mkdir(parents=True,exist_ok=True)
result={'started':time.time(),'standalone_shows':[],'switches':[],'errors':[]}
queue=[];stage='initial';deadline=time.monotonic()+150;last=time.monotonic()


def save():
    (root/'switch-trace.json').write_text(json.dumps(result,indent=2)+'\n')


class Watch(QObject):
    def eventFilter(self,obj,event):
        if (event.type()==QEvent.Show and isinstance(obj,QWidget)and obj.isWindow()
                and obj is not window and obj.windowType()not in(Qt.Popup,Qt.ToolTip)):
            texts=[x.text()for x in obj.findChildren(QLabel)]+[x.text()for x in obj.findChildren(QAbstractButton)]
            if isinstance(obj,(QLabel,QAbstractButton)):texts.insert(0,obj.text())
            result['standalone_shows'].append({'stage':stage,'class':obj.metaObject().className(),
                'title':obj.windowTitle(),'texts':texts[:12],'stack':traceback.format_stack(limit=9)})
            save()
        return False


watch=Watch(window);app.installEventFilter(watch)


def step():
    global stage,last
    try:
        if time.monotonic()>deadline:raise RuntimeError('Switch capture deadline exceeded')
        if not queue and stage=='initial':
            if len(window.autorefresh.devices)<3:QTimer.singleShot(200,step);return
            result['devices']=[d.title()for d in window.autorefresh.devices]
            my2k=next(i for i,d in enumerate(window.autorefresh.devices)if'MY-2K'in d.title())
            others=[i for i in range(len(window.autorefresh.devices))if i!=my2k]
            queue.extend([my2k,others[0],my2k,others[1],my2k,others[0]])
        if not queue:
            result['finished']=time.time();save();window.close();app.quit();return
        index=queue.pop(0);stage=window.autorefresh.devices[index].title()
        window.combobox_devices.setCurrentIndex(index)
        if window.autorefresh.current_device is not window.autorefresh.devices[index]:window.on_device_selected()
        result['switches'].append({'device':stage,'tabs':[window.tabs.tabText(i)for i in range(window.tabs.count())],
            'containers':len(window.findChildren(EditorContainer)),
            'unexpected_visible':[w.metaObject().className()for w in app.topLevelWidgets()if w is not window and w.isVisible()and w.windowType()not in(Qt.Popup,Qt.ToolTip)]})
        save();last=time.monotonic();QTimer.singleShot(800,wait_idle)
    except Exception as error:
        traceback.print_exc();result['errors'].append(str(error));save();app.exit(1)


def wait_idle():
    workers=[getattr(e,'worker',None)for e,_ in window.editors]
    if any(w is not None and w.isRunning()for w in workers)and time.monotonic()-last<12:
        QTimer.singleShot(100,wait_idle);return
    QTimer.singleShot(100,step)


QTimer.singleShot(200,step)
