from types import SimpleNamespace
import pytest
from PyQt5.QtCore import QObject,pyqtSignal
from PyQt5.QtWidgets import QMainWindow,QMessageBox
from kle_serial import Key
from vi_al_addons.xwhatsit.editor import Controller
from vi_al_addons.xwhatsit.protocol import Client
from test_protocol import Handle,keyboard

class Layout(QObject):
    changed=pyqtSignal()
    choice=0
    def get_choice(self,index):return self.choice

def key(col,option=-1):
    item=Key();item.row=0;item.col=col;item.layout_index=0 if option>=0 else -1;item.layout_option=option
    item.x=col;item.y=0
    return item

@pytest.fixture
def controller(qtbot):
    from PyQt5 import sip
    window=QMainWindow();window.layout_editor=Layout()
    control=Controller(window)
    def shutdown(widget):
        if sip.isdeleted(control):
            return
        control.closing=True;control.deactivate()
        if control.worker is not None:
            qtbot.waitUntil(lambda:control.worker is None,timeout=5000)
    # pytest-qt deletes registered windows before fixture finalizers. Drain the
    # worker first, just as the real add-on's before_close() does.
    qtbot.addWidget(window,before_close_func=shutdown)
    yield window,control
    shutdown(window)

def connect(control,qtbot,extended=True):
    h=Handle(extended);kb=keyboard(h)
    kb.keys=[key(0),key(1,0),key(2,1)];kb.encoders=[]
    kb.layout={(0,0,0):'KC_A',(0,0,1):'KC_B',(0,0,2):'KC_C'}
    control.bind(SimpleNamespace(keyboard=kb))
    control.activate('calibration')
    qtbot.waitUntil(lambda:control.client is not None and control.worker is None,timeout=5000)
    control.timer.stop()
    return h,kb

def test_readback_and_layout_changes_do_not_save(controller,qtbot):
    window,c=controller;h,kb=connect(c,qtbot)
    assert c.readouts['sample'].text()=='3 steps'
    assert [k.desc.col for k in c.preview.widgets]==[0,1]
    window.layout_editor.choice=1;window.layout_editor.changed.emit()
    assert [k.desc.col for k in c.preview.widgets]==[0,2]
    assert h.saves==0
    c.show_snapshot((0,0),{(0,2)},340)
    assert c.position==(0,2) and c.preview.pressed_positions=={(0,2)}
    c.show_snapshot((0,2),{(0,2)},220)
    c.show_snapshot((0,2),set(),340)
    assert 'Held 220' in c.sensor_summary.text() and 'Released 340' in c.sensor_summary.text()

def test_live_persistence_is_debounced_and_verified(controller,qtbot):
    _,c=controller;h,kb=connect(c,qtbot)
    c.sliders['settle'].setValue(9);c.sliders['settle'].setValue(10)
    assert h.saves==0
    qtbot.waitUntil(lambda:h.saves==1 and c.worker is None,timeout=5000)
    assert h.settings.settle==10 and c.client.settings==h.settings
    assert 'verified' in c.status.text()
    qtbot.wait(100);assert h.saves==1

def test_held_key_defers_save_then_release_applies_once(controller,qtbot):
    _,c=controller;h,kb=connect(c,qtbot);h.held=True
    c.sliders['margin'].setValue(120)
    qtbot.waitUntil(lambda:'Release all keys' in c.status.text(),timeout=5000)
    assert h.saves==0
    h.held=False
    qtbot.waitUntil(lambda:h.saves==1 and c.worker is None,timeout=5000)
    assert h.settings.margin==120

def test_legacy_firmware_monitoring_and_boot_without_fake_sliders(controller,qtbot):
    _,c=controller;h,kb=connect(c,qtbot,False)
    assert all(not slider.isEnabled()for slider in c.sliders.values())
    assert c.boot.isEnabled() and not c.defaults.isEnabled()
    c.boot.click();qtbot.waitUntil(lambda:h.booted and c.worker is None,timeout=5000)
    assert all(call[3]<0x30 for call in h.calls)

def test_defaults_and_full_erase_are_separate_actions(controller,qtbot,monkeypatch):
    _,c=controller;h,kb=connect(c,qtbot)
    c.sliders['margin'].setValue(130)
    qtbot.waitUntil(lambda:h.saves==1 and c.worker is None,timeout=5000)
    c.defaults.click();qtbot.waitUntil(lambda:h.saves==2 and c.worker is None,timeout=5000)
    assert h.settings.margin==96
    assert not any(call[3]==0x18 for call in h.calls)
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**kw:QMessageBox.No)
    c.erase.click();assert not any(call[3]==0x18 for call in h.calls)
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**kw:QMessageBox.Yes)
    c.erase.click();qtbot.waitUntil(lambda:c.worker is None,timeout=5000)
    assert len([call for call in h.calls if call[3]==0x18])==1


def test_leaving_page_keeps_debounced_save(controller,qtbot):
    _,c=controller;h,kb=connect(c,qtbot)
    c.sliders['margin'].setValue(125)
    c.deactivate()
    qtbot.waitUntil(lambda:h.saves==1 and c.worker is None,timeout=5000)
    assert h.settings.margin==125


def test_reset_supersedes_uncommitted_edit(controller,qtbot):
    _,c=controller;h,kb=connect(c,qtbot)
    c.sliders['margin'].setValue(160)
    c.defaults.click()
    qtbot.waitUntil(lambda:h.saves==1 and c.worker is None,timeout=5000)
    qtbot.wait(650)
    assert h.saves==1 and h.settings.margin==96


def test_keyboard_fits_small_viewport(controller,qtbot):
    _,c=controller;connect(c,qtbot)
    c.preview.resize(320,100);c.preview.update_layout()
    assert c.preview.width*c.preview.scale<=320.01
    from PyQt5.QtWidgets import QWidget
    assert c.preview.height*c.preview.scale<=QWidget.height(c.preview)


def test_navigation_waits_for_pending_save_and_explicit_busy(qtbot):
    from PyQt5.QtWidgets import QComboBox,QPushButton,QTabWidget
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import Qt,QEvent,QPointF
    from vi_al_addons.xwhatsit.provider import XwhatsitSession
    window=QMainWindow();window.layout_editor=Layout();qtbot.addWidget(window)
    window.combobox_devices=QComboBox(window)
    window.btn_refresh_devices=QPushButton(window)
    window.tabs=QTabWidget(window)
    locked=[]
    window.autorefresh=SimpleNamespace(_lock=lambda:locked.append(True),_unlock=lambda:locked.pop())
    session=XwhatsitSession(window,None);c=session.controller
    h,k=connect(c,qtbot);h.held=True
    c.sliders['margin'].setValue(125)
    event=QMouseEvent(QEvent.MouseButtonPress,QPointF(2,2),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier)
    assert session.filter_event(window.combobox_devices,event)
    qtbot.waitUntil(lambda:c.pending is not None and c.worker is None,timeout=5000)
    assert len(session.deferred)==1 and h.saves==0
    h.held=False
    qtbot.waitUntil(lambda:h.saves==1 and c.worker is None and not session.deferred,timeout=5000)
    assert not locked
    c.sliders['margin'].setValue(135)
    assert session.before_close() is False
    assert c.section is None and not c.timer.isActive()
    qtbot.waitUntil(lambda:h.saves==2 and c.worker is None,timeout=5000)
    assert session.before_close() is True


def test_prox_style_calibration_and_stacked_sensors(controller,qtbot):
    from PyQt5.QtWidgets import QWidget,QTabWidget
    from PyQt5.QtCore import QPoint
    window,c=controller;h,k=connect(c,qtbot)
    tabs=QTabWidget();calibration=QWidget();calibration.setLayout(c.calibration)
    sensors=QWidget();sensors.setLayout(c.sensors)
    tabs.addTab(calibration,'Calibration');tabs.addTab(sensors,'Live Sensors')
    window.setCentralWidget(tabs);window.resize(1400,950);window.show()
    qtbot.wait(50)
    top=c.preview.mapTo(window,QPoint())
    table=c.values.mapTo(window,QPoint())
    actions=c.defaults.mapTo(window,QPoint())
    assert table.x()>top.x()+QWidget.width(c.preview)
    assert actions.y()>top.y()+QWidget.height(c.preview)
    assert not hasattr(c,'recalibrate')
    group=c.calibration_controls
    center=c.defaults.mapTo(group,QPoint(c.defaults.width()//2,0)).x()
    assert abs(center-group.width()/2)<4
    c.show_snapshot((0,0),set(),340)
    assert c.preview.widgets[0].text=='340'
    assert h.saves==0
    tabs.setCurrentIndex(1);qtbot.wait(50)
    graph=c.graph.mapTo(window,QPoint());matrix=c.matrix.mapTo(window,QPoint())
    assert matrix.y()>=graph.y()+QWidget.height(c.graph)
    assert abs(QWidget.height(c.graph)-QWidget.height(c.matrix))<50
    c.graph.set_line('minimum',True);c.graph.set_line('maximum',True)
    assert not c.graph.grab().isNull()
    assert h.saves==0


def test_rotating_readings_fill_keys_without_saving(controller,qtbot):
    _,c=controller;h,k=connect(c,qtbot)
    c.poll();qtbot.waitUntil(lambda:c.worker is None,timeout=5000)
    c.poll();qtbot.waitUntil(lambda:c.worker is None,timeout=5000)
    assert (0,0)in c.last_samples and (0,1)in c.last_samples
    assert all(key.text=='340'for key in c.preview.widgets)
    assert h.saves==0


def test_calibration_button_is_queued_during_sensor_read(controller,qtbot,monkeypatch):
    import time
    _,c=controller;h,k=connect(c,qtbot)
    read=c.client.read_signal
    def slower(position):
        time.sleep(.02)
        return read(position)
    monkeypatch.setattr(c.client,'read_signal',slower)
    c.poll();c.defaults.click()
    assert c.pending==('defaults',None)
    qtbot.waitUntil(lambda:h.saves==1 and c.worker is None,timeout=5000)
    assert c.client.settings==c.client.defaults


def test_slow_initial_connect_still_starts_sensor_refresh(controller,qtbot,monkeypatch):
    import time
    _,c=controller
    h=Handle();kb=keyboard(h);kb.keys=[key(0),key(1)];kb.encoders=[]
    kb.layout={(0,0,0):'KC_A',(0,0,1):'KC_B'}
    connect_client=Client.connect
    def slow(client):
        time.sleep(.18)
        return connect_client(client)
    monkeypatch.setattr(Client,'connect',slow)
    c.bind(SimpleNamespace(keyboard=kb));c.activate('calibration')
    qtbot.waitUntil(lambda:len(c.last_samples)>1,timeout=5000)
    c.timer.stop()
    assert h.saves==0


def test_sensor_refresh_resumes_after_persistent_save(controller,qtbot):
    _,c=controller;h,k=connect(c,qtbot)
    c.sliders['margin'].setValue(125)
    qtbot.waitUntil(lambda:h.saves==1 and len(c.last_samples)>1,timeout=5000)
    c.timer.stop()
    assert c.client.settings.margin==125


def test_all_sliders_have_visible_explanations(controller,qtbot):
    _,c=controller;h,k=connect(c,qtbot)
    assert set(c.explanations)==set(c.sliders)
    assert all(label.text() and label.wordWrap()for label in c.explanations.values())
    assert 'scan' in c.explanations['settle'].text()
    assert 'calibration takes longer' in c.explanations['per_key'].text()
    assert 'miss presses' in c.explanations['margin'].text()
    assert h.saves==0
