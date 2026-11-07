"""Exercise the compiled core's real Add-ons menu and modal install workflow."""
import json,os
from pathlib import Path
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFileDialog,QMessageBox,QDialog
from addon_runtime.packages import read_index

window=WINDOW;app=APP
root=Path(os.environ['VI_AL_VALIDATION_DIR'])
packages=iter(sorted(Path(os.environ['VI_AL_PACKAGE_DIR']).glob('*.zip')))
report={'installed':[],'dialogs':[]}
current=None

def choose(*args,**kwargs):
    dialog=QFileDialog(window,'Install Vi_al add-on',str(current.parent),'Vi_al add-on (*.zip)')
    dialog.setOption(QFileDialog.DontUseNativeDialog,True)
    dialog.setFileMode(QFileDialog.ExistingFile)
    dialog.selectFile(str(current))
    def accept():
        dialog.grab().save(str(root/('install-'+current.stem+'-file-picker.png')))
        dialog.accept()
    QTimer.singleShot(250,accept)
    return (dialog.selectedFiles()[0],'Vi_al add-on (*.zip)') if dialog.exec_()==QDialog.Accepted else ('','')

QFileDialog.getOpenFileName=choose

def confirm():
    for dialog in app.topLevelWidgets():
        if isinstance(dialog,QMessageBox) and dialog.isVisible():
            report['dialogs'].append({'title':dialog.windowTitle(),'text':dialog.text()})
            dialog.grab().save(str(root/('install-'+current.stem+'-'+dialog.windowTitle().replace(' ','-')+'.png')))
            button=dialog.button(QMessageBox.Yes) or dialog.button(QMessageBox.Ok)
            if button:button.click()

timer=QTimer(window);timer.timeout.connect(confirm);timer.start(100)

def install_next():
    global current
    try:
        current=next(packages,None)
        if current is None:
            timer.stop()
            report['index']=read_index()
            assert len(report['index'])==3 and all(r['enabled'] for r in report['index'].values())
            assert not window.addon_manager.sessions,'New packages must not hot-load before restart'
            report['passed']=True
            (root/'menu-install.json').write_text(json.dumps(report,indent=2)+'\n')
            window.close();app.quit();return
        menu=next(a.menu() for a in window.menuBar().actions() if a.text()=='Add-ons')
        action=next(a for a in menu.actions() if a.text()=='Install from ZIP…')
        action.trigger()
        assert not any(d['title']=='Cannot install add-on' for d in report['dialogs'])
        report['installed'].append(current.name)
        QTimer.singleShot(100,install_next)
    except Exception as error:
        import traceback;traceback.print_exc()
        report['error']=str(error)
        (root/'menu-install.json').write_text(json.dumps(report,indent=2)+'\n')
        app.exit(1)

assert not window.addon_manager.sessions
QTimer.singleShot(200,install_next)
