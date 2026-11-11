"""Run inside the compiled app via the explicit local test bridge."""
import json,os,re,time
from pathlib import Path
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox,QLabel,QTabWidget

root=Path(os.environ['VI_AL_VALIDATION_DIR']);root.mkdir(parents=True,exist_ok=True)
window=WINDOW;app=APP
result={'devices':[],'pages':[],'dialogs':[],'errors':[],'started':time.time()}
deadline=time.monotonic()+240
queue=[];active=None;last=time.monotonic()

# A device-selection warning can open a nested Qt event loop before capture()
# returns. Close/report it from an independent timer so the run cannot hang.
def dismiss_dialogs():
    for dialog in app.topLevelWidgets():
        if isinstance(dialog,QMessageBox) and dialog.isVisible():
            result['dialogs'].append(dialog.text());save();dialog.accept()

dialog_timer=QTimer(window);dialog_timer.timeout.connect(dismiss_dialogs);dialog_timer.start(100)


def save():
    (root/'pages.json').write_text(json.dumps(result,indent=2)+'\n')


def capture():
    global active,last
    try:
        if time.monotonic()>deadline:raise RuntimeError('Page capture deadline exceeded')
        dialogs=[w for w in app.topLevelWidgets() if isinstance(w,QMessageBox) and w.isVisible()]
        for dialog in dialogs:
            result['dialogs'].append(dialog.text());dialog.accept()
        if active is None:
            if not window.autorefresh.devices:
                QTimer.singleShot(200,capture);return
            result['devices']=[d.title() for d in window.autorefresh.devices]
            queue.extend(range(len(window.autorefresh.devices)))
            active={'phase':'device'}
        phase=active['phase']
        if phase=='device':
            if not queue:
                result['finished']=time.time();save()
                if os.environ.get('VI_AL_AFTER_CAPTURE_BRIDGE'):
                    import runpy
                    runpy.run_path(os.environ['VI_AL_AFTER_CAPTURE_BRIDGE'],init_globals={'APP':app,'WINDOW':window})
                else:
                    window.close();app.quit()
                return
            index=queue.pop(0)
            print('CAPTURE device',index,flush=True)
            window.combobox_devices.setCurrentIndex(index)
            if window.autorefresh.current_device is not window.autorefresh.devices[index]:window.on_device_selected()
            title=window.autorefresh.devices[index].title()
            active.update(phase='page',title=title,at=0)
            active['tabs']=[window.tabs.tabText(i) for i in range(window.tabs.count())]
            result.setdefault('tab_lists',{})[title]=active['tabs']
            window.resize(1250,900)
            QTimer.singleShot(700,capture);return
        if active['at']>=window.tabs.count():
            if window.current_tab:window.current_tab.editor.deactivate()
            active['phase']='device';QTimer.singleShot(400,capture);return
        index=active['at'];window.tabs.setCurrentIndex(index)
        active['phase']='snapshot';last=time.monotonic()
        QTimer.singleShot(800,snapshot)
    except Exception as error:
        import traceback;traceback.print_exc();result['errors'].append(str(error));save();window.close();app.exit(1)


def snapshot():
    try:
        editor=window.tabs.currentWidget().editor
        workers=[getattr(editor,'worker',None)]
        library=getattr(editor,'library_page',None)
        if library:workers.append(getattr(library,'worker',None))
        controller=getattr(editor,'ec_controller',None)
        if controller:workers.append(getattr(controller,'worker',None))
        native=getattr(window,'leyden_jar',None)
        if native:workers.append(getattr(native,'worker',None))
        if any(w is not None and w.isRunning() for w in workers) and time.monotonic()-last<12:
            QTimer.singleShot(100,snapshot);return
        index=active['at'];title=window.tabs.tabText(index)
        print('CAPTURE page',active['title'],title,flush=True)
        slug=re.sub(r'[^a-zA-Z0-9]+','-',active['title'])[:70]
        name=f'{slug}-{index:02d}-{re.sub(r"[^a-zA-Z0-9]+","-",title)}.png'
        assert window.grab().save(str(root/name))
        statuses=[]
        for label in window.tabs.currentWidget().findChildren(QLabel):
            text=label.text()
            if text and any(k in text.lower() for k in ('failed','unsupported','error','ready','saved','live','read','connected','offline')):
                statuses.append(text[:400])
        result['pages'].append({'device':active['title'],'page':title,'screenshot':name,'statuses':statuses})
        # Also show nested Gaming pages; no game or ROM selection is sent.
        if title=='Gaming':
            for tabs in window.tabs.currentWidget().findChildren(QTabWidget):
                for j in range(tabs.count()):
                    tabs.setCurrentIndex(j);app.processEvents()
                    subname=name.replace('.png','-'+tabs.tabText(j)+'.png')
                    window.grab().save(str(root/subname))
        active['at']+=1;active['phase']='page';save();QTimer.singleShot(100,capture)
    except Exception as error:
        import traceback;traceback.print_exc();result['errors'].append(str(error));save();window.close();app.exit(1)

QTimer.singleShot(250,capture)
