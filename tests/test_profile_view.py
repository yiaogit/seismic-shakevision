"""
Pruebas de ProfileView (v0.5 阶段 L).

Cubrimos:
  * Helpers de formato (format_duration_seconds + format_iso_short).
  * i18n: 19 claves profile.* en los 4 idiomas.
  * Construcción del widget sin crash (QT_QPA_PLATFORM=offscreen).
  * refresh_all rellena los stat cards con valores actuales del
    UsageTracker (mockeado).
  * Identidad cambia entre "Guest" y datos de GitHub según
    GitHubAuthService.is_authenticated.
  * Favoritos: añadir una estación + un evento → la lista no está
    vacía tras refresh.
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
    "header.action.profile_tooltip",
    "profile.tab_title",
    "profile.guest_name",
    "profile.guest_handle",
    "profile.member_since",
    "profile.btn.sign_in",
    "profile.btn.logout",
    "profile.stats.title",
    "profile.stat.launches",
    "profile.stat.session_time",
    "profile.stat.quakes_viewed",
    "profile.stat.stations_clicked",
    "profile.stat.audio_listened",
    "profile.stat.reports_generated",
    "profile.favorites.title",
    "profile.favorites.stations",
    "profile.favorites.events",
    "profile.favorites.empty_stations",
    "profile.favorites.empty_events",
)


# ============================================================
# Helpers de formato (sin Qt)
# ============================================================
def test_format_duration_under_minute() -> None:
    from shakevision.ui.profile_view import format_duration_seconds
    assert format_duration_seconds(0) == "0s"
    assert format_duration_seconds(45) == "45s"


def test_format_duration_minutes_seconds() -> None:
    from shakevision.ui.profile_view import format_duration_seconds
    assert format_duration_seconds(60) == "1m 00s"
    assert format_duration_seconds(125) == "2m 05s"


def test_format_duration_hours_minutes() -> None:
    from shakevision.ui.profile_view import format_duration_seconds
    assert format_duration_seconds(3600) == "1h 00m"
    assert format_duration_seconds(3725) == "1h 02m"
    assert format_duration_seconds(7384) == "2h 03m"


def test_format_duration_handles_negative() -> None:
    from shakevision.ui.profile_view import format_duration_seconds
    assert format_duration_seconds(-10) == "0s"


def test_format_iso_short() -> None:
    from shakevision.ui.profile_view import format_iso_short
    assert format_iso_short("") == "—"
    assert format_iso_short("2026-05-18T12:34:56Z") == "2026-05-18"


# ============================================================
# i18n
# ============================================================
@pytest.mark.parametrize("locale", ["en", "es", "zh", "fr"])
def test_profile_i18n_keys_present(locale: str) -> None:
    data = json.loads((LOCALES_DIR / f"{locale}.json").read_text("utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in data]
    assert not missing, f"{locale}.json falta: {missing}"
    for k in REQUIRED_KEYS:
        assert data[k].strip(), f"{locale}.{k} está vacío"


def test_member_since_has_date_placeholder() -> None:
    for loc in ("en", "es", "zh", "fr"):
        data = json.loads((LOCALES_DIR / f"{loc}.json").read_text("utf-8"))
        assert "{date}" in data["profile.member_since"], (
            f"{loc}: member_since sin {{date}}")


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Aísla QSettings + reset singletons de stage I/J/K."""

    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    monkeypatch.delenv("SEISMICGUARD_GITHUB_CLIENT_ID", raising=False)

    from shakevision.services import (
        favorites_store as fs,
        github_auth as ga,
        usage_tracker as ut,
    )
    ut._reset_for_tests()
    fs._reset_for_tests()
    ga._reset_for_tests()
    yield
    ut._reset_for_tests()
    fs._reset_for_tests()
    ga._reset_for_tests()


@pytest.fixture(scope="session")
def qapp_factory():
    from PySide6.QtWidgets import QApplication

    def _factory():
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    return _factory


# ============================================================
# Widget tests
# ============================================================
def test_profile_view_constructs_without_crash(qapp_factory) -> None:
    from shakevision.ui.profile_view import ProfileView

    _app = qapp_factory()
    view = ProfileView()
    try:
        assert view is not None
        # Stat cards existen
        assert view._card_launches is not None
        assert view._card_session_time is not None
    finally:
        view.deleteLater()


def test_profile_view_refresh_pulls_usage_stats(qapp_factory) -> None:
    from shakevision.services.usage_tracker import UsageTracker
    from shakevision.ui.profile_view import ProfileView

    # Preparar estado
    UsageTracker.record_launch()
    UsageTracker.record_launch()
    UsageTracker.record_earthquake_viewed()
    UsageTracker.record_station_clicked()

    _app = qapp_factory()
    view = ProfileView()
    try:
        view.refresh_all()
        # _card_launches refleja launch_count=2
        assert view._card_launches._value_label.text() == "2"
        assert view._card_quakes_viewed._value_label.text() == "1"
        assert view._card_stations._value_label.text() == "1"
    finally:
        view.deleteLater()


def test_profile_view_shows_guest_when_not_signed_in(qapp_factory) -> None:
    from shakevision.ui.profile_view import ProfileView

    _app = qapp_factory()
    view = ProfileView()
    try:
        view.refresh_all()
        # _name_label contiene la traducción de profile.guest_name
        # (no validamos el texto exacto porque depende del idioma actual
        # del runner; sí validamos que NO está vacío y NO es "?")
        assert view._name_label.text().strip()
        assert view._name_label.text() != "?"
    finally:
        view.deleteLater()


def test_profile_view_shows_github_user_when_signed_in(qapp_factory) -> None:
    from shakevision.services.github_auth import GitHubAuthService
    from shakevision.ui.profile_view import ProfileView

    GitHubAuthService.save_token("ghp_test")
    GitHubAuthService.save_profile({
        "login": "yiaogit",
        "name": "Yiao",
        "avatar_url": "",   # vacío → no intenta descargar
    })

    _app = qapp_factory()
    view = ProfileView()
    try:
        view.refresh_all()
        assert view._name_label.text() == "Yiao"
        assert view._handle_label.text() == "@yiaogit"
    finally:
        view.deleteLater()


def test_profile_view_lists_favorites(qapp_factory) -> None:
    from shakevision.services.favorites_store import FavoritesStore
    from shakevision.ui.profile_view import ProfileView

    FavoritesStore.add_station(
        "AM", "R0E05", site_name="Madrid", provider="shakenet")
    FavoritesStore.add_event(
        "us7000abc", 5.4, "Tokio", 1_700_000_000.0)

    _app = qapp_factory()
    view = ProfileView()
    try:
        view.refresh_all()
        assert view._stations_list.count() == 1
        assert "R0E05" in view._stations_list.item(0).text()
        assert view._events_list.count() == 1
        assert "Tokio" in view._events_list.item(0).text()
    finally:
        view.deleteLater()


def test_profile_view_empty_favorites_show_helper_text(qapp_factory) -> None:
    from shakevision.ui.profile_view import ProfileView

    _app = qapp_factory()
    view = ProfileView()
    try:
        view.refresh_all()
        # Sin favoritos: cada lista tiene UN item de placeholder.
        assert view._stations_list.count() == 1
        assert view._events_list.count() == 1
    finally:
        view.deleteLater()


def test_app_header_emits_profile_clicked(qapp_factory) -> None:
    """El nuevo botón de perfil debe emitir profile_clicked."""

    from shakevision.ui.app_header import AppHeader

    _app = qapp_factory()
    header = AppHeader("SeismicGuard", "0.5.0")
    fired = []
    header.profile_clicked.connect(lambda: fired.append(True))
    try:
        header._profile_button.click()
        assert fired == [True]
    finally:
        header.deleteLater()
