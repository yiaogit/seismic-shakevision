"""
``SettingsBackup`` — export / import de TODA la configuración (v0.5 阶段 M).

Caso de uso
-----------
El usuario quiere migrar SeismicGuard a otra máquina sin perder:

  * Preferencias de tema, idioma, zona horaria, modo de capa.
  * Su libreta de Raspberry Shakes LAN.
  * Estaciones y sismos favoritos.
  * Estadísticas de uso acumuladas (no se pierden los "1238 sismos
    vistos" ganados con sudor).
  * Identidad GitHub (login + avatar URL, **NO el token**).
  * Banderas de onboarding (para que no le vuelva a aparecer la
    pantalla de bienvenida en la nueva máquina).

Formato
-------
Un único JSON con ``schema_version: 1`` para futuras migraciones:

    {
      "schema_version": 1,
      "exported_at_iso": "2026-05-18T12:34:56Z",
      "app_version": "0.5.0",
      "theme": {"mode": "auto"},
      "layer": {"mode": "standard"},
      "locale": {"language": "en"},
      "timezone": {"iana": "America/New_York", "address": ""},
      "shake_presets": [{...}, {...}],
      "favorites": {"stations": [...], "events": [...]},
      "usage": {...},
      "github": {"client_id": "...", "profile": {...}},
      "onboarding": {
        "localizame_completed": true,
        "wizard_completed": true
      }
    }

Seguridad
---------
**El access_token de GitHub NO se incluye en el export.** El nuevo
equipo deberá volver a iniciar sesión. Esto es intencional: un JSON
de configuración suele acabar en backups, repos privados, Slack del
laboratorio, etc., y un access_token reusable sería una bomba.

Robustez del import
-------------------
Cada sección se aplica en su propio try/except. Si una sección está
corrupta o falta, se ignora con log warning. Esto significa que un
JSON parcial (p. ej. exportado por una versión antigua que solo tenía
theme + locale) es perfectamente válido — los campos ausentes
simplemente se mantienen con los valores actuales.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from shakevision import __version__


logger = logging.getLogger(__name__)


SCHEMA_VERSION: int = 1


def _now_iso_utc() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# ============================================================
# Export
# ============================================================
def export_settings_to_dict() -> dict:
    """Recoge el estado de todos los servicios y devuelve un dict.

    Cada sección está envuelta en su propio try/except para que un
    fallo aislado (p.ej. ThemeManager no inicializado en una pyqt
    headless de tests) no rompa el export entero.
    """

    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "exported_at_iso": _now_iso_utc(),
        "app_version": __version__,
    }

    # ── Theme ────────────────────────────────────────────────
    try:
        from shakevision.ui.theme_manager import ThemeManager
        payload["theme"] = {"mode": ThemeManager.mode()}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: theme skip (%s)", exc)

    # ── Layer mode ───────────────────────────────────────────
    try:
        from shakevision.ui.layer_mode_manager import LayerModeManager
        payload["layer"] = {"mode": LayerModeManager.current_mode()}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: layer skip (%s)", exc)

    # ── Locale ───────────────────────────────────────────────
    try:
        from shakevision.i18n import LocaleService
        payload["locale"] = {"language": LocaleService.current_language()}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: locale skip (%s)", exc)

    # ── Timezone ─────────────────────────────────────────────
    try:
        from shakevision.services.timezone_service import TimezoneService
        payload["timezone"] = {
            "iana": TimezoneService.current_iana(),
            "address": TimezoneService.address(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: timezone skip (%s)", exc)

    # ── Shake presets (LAN Raspberry Shakes) ────────────────
    try:
        from shakevision.services.shake_presets import ShakePresetStore
        payload["shake_presets"] = [asdict(p) for p in ShakePresetStore.all()]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: shake_presets skip (%s)", exc)

    # ── Favorites ────────────────────────────────────────────
    try:
        from shakevision.services.favorites_store import FavoritesStore
        payload["favorites"] = FavoritesStore.export_to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: favorites skip (%s)", exc)

    # ── Usage stats ──────────────────────────────────────────
    try:
        from shakevision.services.usage_tracker import UsageTracker
        payload["usage"] = UsageTracker.stats()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: usage skip (%s)", exc)

    # ── GitHub (sin access_token) ────────────────────────────
    try:
        from shakevision.services.github_auth import GitHubAuthService
        payload["github"] = {
            "client_id": GitHubAuthService.client_id(),
            "profile": GitHubAuthService.current_user(),
            # NB: access_token deliberadamente OMITIDO.
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: github skip (%s)", exc)

    # ── Onboarding flags ────────────────────────────────────
    try:
        from shakevision.ui.localizame_view import (
            has_been_completed as loc_done,
        )
        from shakevision.ui.onboarding_wizard import (
            has_been_completed as wiz_done,
        )
        payload["onboarding"] = {
            "localizame_completed": loc_done(),
            "wizard_completed": wiz_done(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backup: onboarding skip (%s)", exc)

    return payload


def export_to_file(path: Path) -> Path:
    """Serializa a JSON con indentación. Devuelve el Path final escrito."""

    path = Path(path)
    payload = export_settings_to_dict()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


# ============================================================
# Import
# ============================================================
def import_settings_from_dict(payload: dict, *, replace: bool = False) -> dict:
    """Aplica las secciones del dict a los servicios singleton.

    ``replace`` solo afecta a colecciones (favoritos, shake presets):
    si es True las VACÍA antes de importar; si es False fusiona.

    Devuelve un dict con un resumen ``{section: status}`` para que la
    UI pueda mostrar al usuario qué entró bien:

        {"theme": "ok", "favorites": "ok",
         "shake_presets": "skipped: invalid"}

    Cada sección con error mantiene los valores actuales sin lanzar.
    """

    summary: dict = {}
    if not isinstance(payload, dict):
        return {"_error": "payload_no_es_dict"}

    sv = payload.get("schema_version", 0)
    if not isinstance(sv, int) or sv > SCHEMA_VERSION:
        # Futuro: si llega un schema_version más alto, intentamos
        # importar lo que reconocemos y avisamos al usuario.
        summary["_schema_warning"] = (
            f"schema_version {sv} > soportado {SCHEMA_VERSION} "
            f"— importando con compatibilidad parcial")

    # ── Theme ────────────────────────────────────────────────
    try:
        sect = payload.get("theme") or {}
        mode = sect.get("mode")
        if mode in ("auto", "light", "dark"):
            from shakevision.ui.theme_manager import ThemeManager
            ThemeManager.set_mode(mode)
            summary["theme"] = "ok"
    except Exception as exc:  # noqa: BLE001
        summary["theme"] = f"skip:{exc}"

    # ── Layer ────────────────────────────────────────────────
    try:
        sect = payload.get("layer") or {}
        mode = sect.get("mode")
        if mode in ("standard", "professional"):
            from shakevision.ui.layer_mode_manager import LayerModeManager
            LayerModeManager.set_mode(mode)
            summary["layer"] = "ok"
    except Exception as exc:  # noqa: BLE001
        summary["layer"] = f"skip:{exc}"

    # ── Locale ───────────────────────────────────────────────
    try:
        sect = payload.get("locale") or {}
        lang = sect.get("language")
        if lang:
            from shakevision.i18n import LocaleService
            LocaleService.set_language(lang)
            summary["locale"] = "ok"
    except Exception as exc:  # noqa: BLE001
        summary["locale"] = f"skip:{exc}"

    # ── Timezone ─────────────────────────────────────────────
    try:
        sect = payload.get("timezone") or {}
        iana = sect.get("iana")
        address = sect.get("address", "")
        if iana:
            from shakevision.services.timezone_service import TimezoneService
            TimezoneService.set_timezone(iana)
            if address:
                TimezoneService.set_address(address)
            summary["timezone"] = "ok"
    except Exception as exc:  # noqa: BLE001
        summary["timezone"] = f"skip:{exc}"

    # ── Shake presets ────────────────────────────────────────
    try:
        from shakevision.services.shake_presets import (
            LanShakePreset,
            ShakePresetStore,
        )
        sect = payload.get("shake_presets") or []
        if isinstance(sect, list):
            if replace:
                ShakePresetStore.clear()
            added = 0
            for entry in sect:
                if not isinstance(entry, dict):
                    continue
                try:
                    p = LanShakePreset.from_dict(entry)
                    if not p.host:
                        continue
                    if ShakePresetStore.add(p):
                        added += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Backup: shake entry skip (%s)", exc)
            summary["shake_presets"] = f"ok ({added} added)"
    except Exception as exc:  # noqa: BLE001
        summary["shake_presets"] = f"skip:{exc}"

    # ── Favorites ────────────────────────────────────────────
    try:
        from shakevision.services.favorites_store import FavoritesStore
        sect = payload.get("favorites") or {}
        if isinstance(sect, dict):
            added = FavoritesStore.import_from_dict(sect, replace=replace)
            summary["favorites"] = f"ok ({added} added)"
    except Exception as exc:  # noqa: BLE001
        summary["favorites"] = f"skip:{exc}"

    # ── Usage stats ──────────────────────────────────────────
    # Restaurar stats no es tan trivial como llamar a setters: el
    # tracker solo expone "record_*" (incrementos). Para soportar
    # restore exponemos las claves directamente al QSettings. Si la
    # política es "fusionar", **no sobrescribimos** porque sumar mal
    # stats de dos máquinas distintas sería confuso. Solo si replace
    # restauramos.
    if replace:
        try:
            from shakevision.services import usage_tracker as ut
            sect = payload.get("usage") or {}
            if isinstance(sect, dict):
                _restore_usage_stats(sect)
                ut._instance = None    # forzar rehydrate desde QSettings
                summary["usage"] = "ok"
        except Exception as exc:  # noqa: BLE001
            summary["usage"] = f"skip:{exc}"
    else:
        summary["usage"] = "skipped: requires replace=True"

    # ── GitHub (solo client_id + profile; nunca el token) ────
    try:
        from shakevision.services.github_auth import GitHubAuthService
        sect = payload.get("github") or {}
        cid = sect.get("client_id", "")
        if cid:
            GitHubAuthService.set_client_id(cid)
        profile = sect.get("profile") or {}
        if isinstance(profile, dict) and profile.get("login"):
            GitHubAuthService.save_profile(profile)
        summary["github"] = "ok (token NOT imported — sign in again)"
    except Exception as exc:  # noqa: BLE001
        summary["github"] = f"skip:{exc}"

    # ── Onboarding flags ────────────────────────────────────
    try:
        sect = payload.get("onboarding") or {}
        if sect.get("localizame_completed"):
            from shakevision.ui.localizame_view import (
                mark_completed as loc_mark,
            )
            loc_mark()
        if sect.get("wizard_completed"):
            from shakevision.ui.onboarding_wizard import (
                mark_completed as wiz_mark,
            )
            wiz_mark()
        summary["onboarding"] = "ok"
    except Exception as exc:  # noqa: BLE001
        summary["onboarding"] = f"skip:{exc}"

    return summary


def import_from_file(path: Path, *, replace: bool = False) -> dict:
    """Lee el JSON del disco e invoca ``import_settings_from_dict``."""

    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    return import_settings_from_dict(payload, replace=replace)


# ============================================================
# Helpers internos
# ============================================================
def _restore_usage_stats(stats: dict) -> None:
    """Escribe directamente las claves de UsageTracker en QSettings.

    Solo se invoca con replace=True. Bypasses ``record_*`` porque
    esos métodos solo incrementan; aquí queremos sobrescribir.
    """

    try:
        from shakevision.services import usage_tracker as ut
        from PySide6.QtCore import QSettings
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"usage restore unavailable: {exc}")

    s = QSettings(ut._QSETTINGS_ORG, ut._QSETTINGS_APP)
    # ── Strings ──
    for key_attr, dict_key in (
        ("KEY_FIRST_LAUNCH_ISO", "first_launch_iso"),
        ("KEY_LAST_LAUNCH_ISO",  "last_launch_iso"),
    ):
        full_key = getattr(ut, key_attr)
        val = stats.get(dict_key, "")
        if val:
            s.setValue(full_key, str(val))
    # ── Ints ──
    for key_attr, dict_key in (
        ("KEY_LAUNCH_COUNT",       "launch_count"),
        ("KEY_SESSION_SECONDS",    "session_seconds"),
        ("KEY_EARTHQUAKES_VIEWED", "earthquakes_viewed_count"),
        ("KEY_STATIONS_CLICKED",   "stations_clicked_count"),
        ("KEY_STATIONS_STREAMED",  "stations_streamed_count"),
        ("KEY_AUDIO_SECONDS",      "audio_played_seconds"),
        ("KEY_REPORTS_COUNT",      "reports_generated_count"),
        ("KEY_REPLAY_COUNT",       "replay_sessions_count"),
    ):
        full_key = getattr(ut, key_attr)
        try:
            val = int(stats.get(dict_key, 0))
        except (TypeError, ValueError):
            val = 0
        s.setValue(full_key, val)


# ============================================================
# Façade simple para tests / UI
# ============================================================
class SettingsBackup:
    """Fachada estática (los métodos son puros — no hay singleton)."""

    SCHEMA_VERSION = SCHEMA_VERSION

    @staticmethod
    def export_to_dict() -> dict:
        return export_settings_to_dict()

    @staticmethod
    def export_to_file(path: Path) -> Path:
        return export_to_file(path)

    @staticmethod
    def import_from_dict(payload: dict, *, replace: bool = False) -> dict:
        return import_settings_from_dict(payload, replace=replace)

    @staticmethod
    def import_from_file(path: Path, *, replace: bool = False) -> dict:
        return import_from_file(path, replace=replace)
