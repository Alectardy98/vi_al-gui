# SPDX-License-Identifier: GPL-2.0-or-later
"""One desktop instance per user, before any keyboard discovery starts."""
import hashlib
from pathlib import Path

from PyQt5.QtCore import QObject, QDir, QLockFile, QStandardPaths
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


class AppInstance(QObject):
    def __init__(self, app, directory=None, name=None):
        super().__init__(app)
        identity = hashlib.sha256(QDir.homePath().encode()).hexdigest()[:16]
        self.name = name or 'Vi_al-' + identity
        root = Path(directory or QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation)
                    or QDir.tempPath())
        root.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(root / (self.name + '.lock')))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.window = None
        self.activation_pending = False
        self.primary = False
        app.aboutToQuit.connect(self.close)

    def acquire(self):
        if not self.lock.tryLock(0):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(500):
                socket.write(b'activate\n')
                socket.waitForBytesWritten(500)
                socket.disconnectFromServer()
            return False
        # Only the lock owner may remove a stale socket left by a crashed app.
        if not self.server.listen(self.name):
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.lock.unlock()
                raise RuntimeError('Cannot create the Vi_al application connection.')
        self.primary = True
        self.server.newConnection.connect(self.activate)
        return True

    def set_window(self, window):
        self.window = window
        if self.activation_pending:
            self.activate()

    def activate(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.close()
            socket.deleteLater()
        if self.window is None:
            self.activation_pending = True
            return
        self.activation_pending = False
        if self.window.isMinimized():
            self.window.showNormal()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def close(self):
        if self.primary:
            self.server.close()
            self.lock.unlock()
            self.primary = False
