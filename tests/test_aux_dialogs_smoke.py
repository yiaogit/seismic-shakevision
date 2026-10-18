"""Smoke de construcción para diálogos auxiliares (sin red ni hardware)."""

from __future__ import annotations

import pytest

try:
    from PySide6.QtWidgets import QApplication
except Exception as exc:  # noqa: BLE001
    pytest.skip(f"PySide6 no disponible ({exc})", allow_module_level=True)

from shakevision.services.updater import UpdateInfo
from shakevision.ui.add_shake_dialog import AddShakeDialog
from shakevision.ui.github_login_dialog import GitHubLoginDialog
from shakevision.ui.onboarding_wizard import OnboardingWizard
from shakevision.ui.settings_dialog import SettingsDialog
from shakevision.ui.update_dialog import UpdateDialog


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_aux_dialogs_construct(qapp) -> None:
    dialogs = [
        AddShakeDialog(),
        GitHubLoginDialog(),
        SettingsDialog(),
    ]
    for dlg in dialogs:
        assert dlg.windowTitle() != ""
        dlg.close()
        dlg.deleteLater()
    qapp.processEvents()


def test_update_dialog_construct(qapp) -> None:
    info = UpdateInfo(
        version="0.9.1", tag="v0.9.1", notes="notes", html_url="",
        assets=(), checksums_url="")
    dlg = UpdateDialog(info)
    assert dlg.windowTitle() != ""
    assert dlg.download_btn.isEnabled() is False
    dlg.close()
    dlg.deleteLater()


def test_onboarding_construct(qapp) -> None:
    # No ejecutamos exec(): solo comprobamos que el wizard se construye y
    # puede cerrarse sin tocar QSettings del usuario.
    dlg = OnboardingWizard()
    assert dlg is not None
    dlg.close()
    dlg.deleteLater()
    qapp.processEvents()
