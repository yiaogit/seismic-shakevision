"""
Pruebas del OnboardingWizard (v0.5 阶段 H).

Cubrimos:
  * Presencia de las 28 claves i18n en los 4 idiomas.
  * Persistencia de la bandera "wizard completado".
  * Construcción del wizard sin crash en QT_QPA_PLATFORM=offscreen.
  * Navegación: next / back / skip / counter actualizan correctamente.
  * Aplicación inmediata de cada selección (language, theme, layer).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")


LOCALES_DIR = (
    Path(__file__).resolve().parent.parent
    / "shakevision" / "i18n" / "locales"
)

REQUIRED_KEYS = (
    "onboarding.counter",
    "onboarding.btn.back",
    "onboarding.btn.skip",
    "onboarding.btn.next",
    "onboarding.btn.finish",
    "onboarding.step.welcome",
    "onboarding.step.language",
    "onboarding.step.timezone",
    "onboarding.step.theme",
    "onboarding.step.layer",
    "onboarding.step.done",
    "onboarding.welcome.tagline",
    "onboarding.welcome.privacy",
    "onboarding.language.heading",
    "onboarding.language.help",
    "onboarding.timezone.heading",
    "onboarding.timezone.help",
    "onboarding.theme.heading",
    "onboarding.theme.help",
    "onboarding.theme.auto",
    "onboarding.theme.light",
    "onboarding.theme.dark",
    "onboarding.layer.heading",
    "onboarding.layer.help",
    "onboarding.layer.standard",
    "onboarding.layer.professional",
    "onboarding.done.heading",
    "onboarding.done.body",
)


# ============================================================
# i18n
# ============================================================
@pytest.mark.parametrize("locale", ["en", "es", "zh", "fr"])
def test_onboarding_i18n_keys_present(locale: str) -> None:
    """Cada uno de los 4 idiomas debe declarar las 28 claves."""

    data = json.loads((LOCALES_DIR / f"{locale}.json").read_text("utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in data]
    assert not missing, f"{locale}.json falta: {missing}"
    # Ninguna debería estar vacía
    for k in REQUIRED_KEYS:
        assert data[k].strip(), f"{locale}.{k} está vacío"


def test_onboarding_counter_has_placeholders() -> None:
    """``onboarding.counter`` debe usar {current} y {total}."""

    for loc in ("en", "es", "zh", "fr"):
        data = json.loads(
            (LOCALES_DIR / f"{loc}.json").read_text("utf-8"))
        tpl = data["onboarding.counter"]
        assert "{current}" in tpl, f"{loc}: counter sin {{current}}: {tpl!r}"
        assert "{total}" in tpl, f"{loc}: counter sin {{total}}: {tpl!r}"


# ============================================================
# Persistencia QSettings
# ============================================================
def test_completed_flag_round_trip(tmp_path) -> None:
    """mark_completed + has_been_completed forman un par estable."""

    from PySide6.QtCore import QCoreApplication, QSettings
    from shakevision.ui import onboarding_wizard as w

    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))

    w._reset_for_tests()
    w.mark_completed()
    assert w.has_been_completed() is True
    w._reset_for_tests()


# ============================================================
# Wizard widget — requiere QApplication
# ============================================================
def test_wizard_constructs_with_six_pages(qapp_factory) -> None:
    """El wizard debe tener exactamente 6 páginas en su QStackedWidget."""

    from shakevision.ui.onboarding_wizard import OnboardingWizard, STEP_KEYS

    _app = qapp_factory()
    wiz = OnboardingWizard()
    try:
        assert wiz._stack.count() == 6
        assert len(STEP_KEYS) == 6
        assert wiz._stack.currentIndex() == 0
    finally:
        wiz.close()


def test_wizard_next_back_navigates_indices(qapp_factory) -> None:
    """Next avanza, Back retrocede; los índices no se desbordan."""

    from shakevision.ui.onboarding_wizard import OnboardingWizard

    _app = qapp_factory()
    wiz = OnboardingWizard()
    try:
        assert wiz._stack.currentIndex() == 0
        wiz._on_next()
        assert wiz._stack.currentIndex() == 1
        wiz._on_next()
        assert wiz._stack.currentIndex() == 2
        wiz._on_back()
        assert wiz._stack.currentIndex() == 1
        # Avanzar hasta el final
        for _ in range(10):
            wiz._on_next()
        # En la última página, el siguiente click llama _finish que
        # cierra el dialog; el índice queda en 5 (la última).
        assert wiz._stack.currentIndex() == 5 or wiz.result() != 0
    finally:
        wiz.close()


def test_wizard_skip_marks_completed_and_emits_signal(
    qapp_factory, tmp_path,
) -> None:
    """Skip debe marcar completado + emitir finished_setup."""

    from PySide6.QtCore import QCoreApplication, QSettings
    from shakevision.ui import onboarding_wizard as w
    from shakevision.ui.onboarding_wizard import OnboardingWizard

    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    w._reset_for_tests()

    _app = qapp_factory()
    wiz = OnboardingWizard()
    fired = []
    wiz.finished_setup.connect(lambda: fired.append(True))
    try:
        wiz._on_skip()
        assert fired == [True]
        assert wiz.was_skipped is True
        assert w.has_been_completed() is True
    finally:
        w._reset_for_tests()


def test_wizard_theme_radio_applies_immediately(qapp_factory) -> None:
    """Cambiar el radio del tema debe llamar a ThemeManager.set_mode."""

    from unittest.mock import patch
    from shakevision.ui.onboarding_wizard import OnboardingWizard

    _app = qapp_factory()
    wiz = OnboardingWizard()
    try:
        with patch(
            "shakevision.ui.theme_manager.ThemeManager.set_mode"
        ) as mock_set:
            # Seleccionar dark (puede que ya esté checked si es el
            # tema actual; en ese caso forzamos toggle vía auto→dark)
            wiz._theme_buttons["auto"].setChecked(True)
            wiz._theme_buttons["dark"].setChecked(True)
            # Tras el último toggle, ThemeManager.set_mode("dark") debió
            # invocarse al menos una vez.
            calls_dark = [
                c for c in mock_set.call_args_list
                if c.args and c.args[0] == "dark"
            ]
            assert len(calls_dark) >= 1
    finally:
        wiz.close()


def test_wizard_language_radio_applies_immediately(qapp_factory) -> None:
    """Cambiar el radio del idioma debe llamar a LocaleService.set_language."""

    from unittest.mock import patch
    from shakevision.ui.onboarding_wizard import OnboardingWizard

    _app = qapp_factory()
    wiz = OnboardingWizard()
    try:
        with patch(
            "shakevision.i18n.LocaleService.set_language"
        ) as mock_set:
            # Forzar selección de un idioma distinto al actual:
            # Si el actual es "es", seleccionamos "en" y viceversa.
            from shakevision.i18n import LocaleService
            cur = LocaleService.current_language()
            target = "en" if cur != "en" else "es"
            wiz._lang_buttons[target].setChecked(True)
            calls = [
                c for c in mock_set.call_args_list
                if c.args and c.args[0] == target
            ]
            assert len(calls) >= 1
    finally:
        wiz.close()


# ============================================================
# Fixture
# ============================================================
@pytest.fixture(scope="session")
def qapp_factory():
    from PySide6.QtWidgets import QApplication

    def _factory():
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    return _factory
