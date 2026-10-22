"""Regression: an available update must reach the notification dialog.

The old implementation imported ``__version__`` inside another branch of
``_on_update_check_done``; Python then treated it as a local variable and
the dialog path raised UnboundLocalError before showing anything.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6 import QtWidgets

import shakevision.ui.main_window as mw
from shakevision.services.updater import UpdateInfo


class _FakeSettings:
    def value(self, *_a, **_kw):
        return ""

    def setValue(self, *_a, **_kw):
        pass


class _FakeButton:
    pass


class _FakeMessageBox:
    AcceptRole = object()
    RejectRole = object()
    DestructiveRole = object()

    instances: list["_FakeMessageBox"] = []

    def __init__(self, *_a, **_kw):
        self.buttons: list[tuple[str, object]] = []
        self.exec_called = False
        self._later = _FakeButton()
        _FakeMessageBox.instances.append(self)

    def setWindowTitle(self, _text):
        pass

    def setText(self, _text):
        pass

    def addButton(self, text, role):
        self.buttons.append((text, role))
        return self._later if role is self.RejectRole else _FakeButton()

    def setDefaultButton(self, _button):
        pass

    def exec(self):
        self.exec_called = True

    def clickedButton(self):
        return self._later


def test_update_available_shows_notification(monkeypatch) -> None:
    _FakeMessageBox.instances.clear()
    monkeypatch.setattr(QtWidgets, "QMessageBox", _FakeMessageBox)
    monkeypatch.setattr(mw, "QSettings", lambda *_a, **_kw: _FakeSettings())
    fake_self = SimpleNamespace(
        _update_checking=True,
        _dialog_parent=lambda: None,
    )
    info = UpdateInfo(
        version="9.9.9", tag="v9.9.9", notes="notes",
        html_url="https://example.invalid/release", assets=(), checksums_url="",
    )
    mw.MainWindow._on_update_check_done(fake_self, (False, info, ""))
    assert fake_self._update_checking is False
    assert len(_FakeMessageBox.instances) == 1
    box = _FakeMessageBox.instances[0]
    assert box.exec_called
    assert len(box.buttons) == 3
