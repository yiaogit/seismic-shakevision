"""
Pruebas de ``shakevision.services.settings_backup`` (v0.5 阶段 M).

Cubrimos:
  * Export devuelve un dict con schema_version + secciones esperadas.
  * Export → import round-trip recupera favoritos y shake presets.
  * Import con replace=True restaura usage stats; sin replace los deja.
  * Import a un dict vacío/parcial no rompe ni borra nada.
  * GitHub access_token NUNCA aparece en el export (seguridad).
  * i18n: 13 claves settings.backup.* en los 4 idiomas.
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

# v0.7-C: el tab "Backup" fue reemplazado por "Reset" (clear cache).
# Las claves settings.backup.* desaparecen del JSON; en su lugar
# están settings.reset.*. Mantenemos los tests del módulo
# SettingsBackup en sí (siguen existiendo como API, solo no expuestos
# en la UI), pero los tests de presencia i18n apuntan a las claves
# nuevas.
REQUIRED_KEYS = (
    "settings.tab.reset",
    "settings.reset.heading",
    "settings.reset.help",
    "settings.reset.button",
    "settings.reset.confirm_title",
    "settings.reset.confirm_body",
    "settings.reset.ok",
    "settings.reset.partial",
    "settings.reset.error",
)


# ============================================================
# Fixture: aislar QSettings + reset singletons
# ============================================================
@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    monkeypatch.delenv("SEISMICGUARD_GITHUB_CLIENT_ID", raising=False)

    from shakevision.services import (
        favorites_store as fs,
        github_auth as ga,
        shake_presets as sp,
        usage_tracker as ut,
    )
    ut._reset_for_tests()
    fs._reset_for_tests()
    ga._reset_for_tests()
    sp._reset_for_tests()
    yield
    ut._reset_for_tests()
    fs._reset_for_tests()
    ga._reset_for_tests()
    sp._reset_for_tests()


# ============================================================
# i18n
# ============================================================
@pytest.mark.parametrize("locale", ["en", "es", "zh", "fr"])
def test_backup_i18n_keys_present(locale: str) -> None:
    data = json.loads((LOCALES_DIR / f"{locale}.json").read_text("utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in data]
    assert not missing, f"{locale}: missing {missing}"


def test_reset_format_strings_have_placeholders() -> None:
    """v0.7-C: settings.reset.partial debe tener {errors};
    settings.reset.error debe tener {error}."""

    for loc in ("en", "es", "zh", "fr"):
        d = json.loads((LOCALES_DIR / f"{loc}.json").read_text("utf-8"))
        assert "{errors}" in d["settings.reset.partial"]
        assert "{error}" in d["settings.reset.error"]


# ============================================================
# Export: schema + contenido + seguridad
# ============================================================
def test_export_returns_schema_version_and_timestamp() -> None:
    from shakevision.services.settings_backup import (
        SCHEMA_VERSION,
        SettingsBackup,
    )

    payload = SettingsBackup.export_to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["exported_at_iso"].endswith("Z")
    assert "app_version" in payload


def test_export_never_includes_github_access_token() -> None:
    """**Crítico**: el token jamás debe aparecer en el JSON exportado."""

    from shakevision.services.github_auth import GitHubAuthService
    from shakevision.services.settings_backup import SettingsBackup

    GitHubAuthService.save_token("ghp_SECRET_TOKEN_xxx")
    GitHubAuthService.save_profile({
        "login": "yiaogit",
        "name": "Yiao",
    })
    payload = SettingsBackup.export_to_dict()

    # Búsqueda agresiva: el string del token NO debe aparecer en
    # ninguna parte del payload serializado.
    blob = json.dumps(payload, ensure_ascii=False)
    assert "ghp_SECRET_TOKEN_xxx" not in blob
    # Pero sí debe haber login + name (eso no es sensible)
    assert "yiaogit" in blob


def test_export_includes_all_known_sections() -> None:
    """Tras setup mínimo, el export debe tener todas las secciones."""

    from shakevision.services.favorites_store import FavoritesStore
    from shakevision.services.usage_tracker import UsageTracker
    from shakevision.services.settings_backup import SettingsBackup

    UsageTracker.record_launch()
    FavoritesStore.add_station("AM", "R0E05", site_name="Madrid")

    payload = SettingsBackup.export_to_dict()
    # No exigimos todas (algunas pueden faltar si el servicio no
    # está inicializado en el entorno de test) pero sí las mínimas:
    assert "favorites" in payload
    assert "usage" in payload
    assert payload["favorites"]["stations"][0]["network"] == "AM"
    assert payload["usage"]["launch_count"] == 1


# ============================================================
# Import: round-trip
# ============================================================
def test_round_trip_favorites_and_presets() -> None:
    from shakevision.services.favorites_store import FavoritesStore
    from shakevision.services.shake_presets import (
        LanShakePreset,
        ShakePresetStore,
    )
    from shakevision.services.settings_backup import SettingsBackup

    FavoritesStore.add_station("AM", "R0E05", site_name="Madrid")
    FavoritesStore.add_event("us7000abc", 5.4, "Lima", 1_700_000_000.0)
    ShakePresetStore.add(LanShakePreset(
        label="Casa", host="192.168.1.50", station="R0E05"))

    payload = SettingsBackup.export_to_dict()

    # Vaciar todo en memoria + QSettings
    FavoritesStore.clear_all()
    ShakePresetStore.clear()
    assert FavoritesStore.list_stations() == []
    assert ShakePresetStore.all() == []

    # Re-importar
    summary = SettingsBackup.import_from_dict(payload, replace=False)
    assert summary["favorites"].startswith("ok")
    assert summary["shake_presets"].startswith("ok")
    assert any(s.code == "R0E05" for s in FavoritesStore.list_stations())
    assert any(p.host == "192.168.1.50" for p in ShakePresetStore.all())
    assert any(e.id == "us7000abc" for e in FavoritesStore.list_events())


def test_import_partial_dict_does_not_crash() -> None:
    """Un dict con SOLO theme debe importarse sin tocar el resto."""

    from shakevision.services.favorites_store import FavoritesStore
    from shakevision.services.settings_backup import SettingsBackup

    FavoritesStore.add_station("AM", "EXISTING")
    SettingsBackup.import_from_dict(
        {"schema_version": 1, "theme": {"mode": "dark"}})
    # No debe haber claves de favoritos en el summary (no se procesó)
    # y los favoritos existentes deben permanecer.
    assert any(s.code == "EXISTING" for s in FavoritesStore.list_stations())


def test_import_handles_non_dict_payload_gracefully() -> None:
    from shakevision.services.settings_backup import SettingsBackup

    summary = SettingsBackup.import_from_dict("not a dict")  # type: ignore
    assert "_error" in summary


def test_import_usage_only_with_replace() -> None:
    """Sin replace=True, usage NO se restaura (sumar mal es peor que perder)."""

    from shakevision.services.usage_tracker import UsageTracker
    from shakevision.services.settings_backup import SettingsBackup

    # Estado origen: 5 launches
    for _ in range(5):
        UsageTracker.record_launch()
    payload = SettingsBackup.export_to_dict()
    assert payload["usage"]["launch_count"] == 5

    # Estado destino: 2 launches
    UsageTracker.reset()
    UsageTracker.record_launch()
    UsageTracker.record_launch()

    # Sin replace → no se restaura
    summary = SettingsBackup.import_from_dict(payload, replace=False)
    assert "skipped" in summary["usage"]
    assert UsageTracker.stats()["launch_count"] == 2

    # Con replace → se sobrescribe a 5
    summary2 = SettingsBackup.import_from_dict(payload, replace=True)
    assert summary2["usage"] == "ok"
    assert UsageTracker.stats()["launch_count"] == 5


def test_round_trip_via_file(tmp_path) -> None:
    from shakevision.services.favorites_store import FavoritesStore
    from shakevision.services.settings_backup import SettingsBackup

    FavoritesStore.add_station("AM", "R0E05", site_name="Madrid")
    path = tmp_path / "backup.json"
    SettingsBackup.export_to_file(path)
    assert path.exists()
    data = json.loads(path.read_text("utf-8"))
    assert "favorites" in data

    FavoritesStore.clear_all()
    summary = SettingsBackup.import_from_file(path)
    assert summary["favorites"].startswith("ok")
    assert any(s.code == "R0E05" for s in FavoritesStore.list_stations())


def test_import_higher_schema_version_warns_but_continues() -> None:
    """Versión futura → warning + import lo conocido."""

    from shakevision.services.favorites_store import FavoritesStore
    from shakevision.services.settings_backup import SettingsBackup

    payload = {
        "schema_version": 999,
        "favorites": {
            "stations": [{"network": "AM", "code": "FROM_FUTURE"}],
            "events": [],
        },
    }
    summary = SettingsBackup.import_from_dict(payload)
    assert "_schema_warning" in summary
    assert any(s.code == "FROM_FUTURE"
               for s in FavoritesStore.list_stations())
