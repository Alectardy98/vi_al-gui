"""Repeated launches activate the owner before a second window opens HID."""
import uuid
from PyQt5.QtWidgets import QApplication,QMainWindow
from app_instance import AppInstance


def test_second_launch_activates_existing_window_and_owner_releases_lock(qtbot,tmp_path):
    app=QApplication.instance();name='Vi_al-test-'+uuid.uuid4().hex
    first=AppInstance(app,tmp_path,name);second=AppInstance(app,tmp_path,name)
    window=QMainWindow();qtbot.addWidget(window)
    try:
        assert first.acquire()
        first.set_window(window)
        assert not window.isVisible()
        assert not second.acquire()
        qtbot.waitUntil(window.isVisible,timeout=2000)
        second.close()
        first.close()
        assert second.acquire(), 'A cleanly closed owner left the app locked'
    finally:
        second.close();first.close()


def test_launch_during_startup_defers_activation_until_window_is_ready(qtbot,tmp_path):
    app=QApplication.instance();name='Vi_al-test-'+uuid.uuid4().hex
    first=AppInstance(app,tmp_path,name);second=AppInstance(app,tmp_path,name)
    window=QMainWindow();qtbot.addWidget(window)
    try:
        assert first.acquire() and not second.acquire()
        qtbot.waitUntil(lambda:first.activation_pending,timeout=2000)
        first.set_window(window)
        assert window.isVisible() and not first.activation_pending
    finally:
        second.close();first.close()
