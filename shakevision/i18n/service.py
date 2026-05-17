"""
``LocaleService`` — singleton de idioma + función ``t()``.

Diseño
------
* Idiomas soportados: ``en``, ``es``, ``zh``, ``fr``.
* Idioma por defecto al primer arranque: ``en``.
* La elección persiste en ``QSettings`` (clave ``locale/language``).
* Cambiar idioma emite ``language_changed`` para que la UI reaccione
  sin reiniciar.
* ``t(key, **kwargs)`` busca en este orden:
    1. tabla del idioma actual
    2. tabla en inglés (fallback)
    3. la clave misma (señal visible de "string sin traducir")
* Soporta interpolación de variables vía ``str.format``: ``t("foo",
  name="x")`` con valor ``"Hola {name}"`` → ``"Hola x"``.

No depende de Qt salvo para emitir la señal — los .json y la lectura
funcionan sin ``QSettings`` (modo headless / tests).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal


logger = logging.getLogger(__name__)


# Idiomas soportados en este release. El orden importa para el
# desplegable del UI (inglés primero porque es el default).
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "es", "zh", "fr")

# Etiqueta humana de cada idioma — siempre se muestra en su PROPIO
# idioma (auto-glónimo) para que un usuario que no sepa inglés
# reconozca su lengua en la lista. Estos labels no se traducen.
LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "es": "Español",
    "zh": "简体中文",
    "fr": "Français",
}

# Idioma por defecto al primer arranque.
DEFAULT_LANGUAGE: str = "en"

# Directorio donde viven los .json. Se calcula relativo a este archivo
# para que funcione tanto instalado como en desarrollo.
_LOCALES_DIR: Path = Path(__file__).resolve().parent / "locales"


# Clave QSettings (organización, app, clave). Las dos primeras coinciden
# con las que ya usa ProWindow para no proliferar settings.
_QSETTINGS_ORG: str = "ShakeVision"
_QSETTINGS_APP: str = "Locale"
_QSETTINGS_KEY: str = "locale/language"


class _Singleton(QObject):
    """Implementación concreta. ``LocaleService`` lo expone como módulo."""

    language_changed = Signal(str)  # nuevo código de idioma

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._tables: dict[str, dict[str, str]] = {}
        self._current: str = DEFAULT_LANGUAGE
        # Inicial: leer la preferencia persistida (si existe).
        self._load_persisted_language()
        # Pre-cargar siempre inglés (fallback obligatorio) + idioma actual.
        self._load_table("en")
        if self._current != "en":
            self._load_table(self._current)

    # ------------------------------------------------------------------
    # Estado público
    # ------------------------------------------------------------------
    def current_language(self) -> str:
        return self._current

    def set_language(self, lang: str) -> None:
        """Cambia el idioma activo. Idempotente."""

        if lang not in SUPPORTED_LANGUAGES:
            logger.warning("Idioma no soportado: %s — ignorado", lang)
            return
        with self._lock:
            if lang == self._current:
                return
            self._current = lang
            self._load_table(lang)
            self._persist_language(lang)
        # Emit fuera del lock para evitar dead-locks con receptores
        self.language_changed.emit(lang)

    def available_languages(self) -> tuple[str, ...]:
        return SUPPORTED_LANGUAGES

    # ------------------------------------------------------------------
    # Lookup principal
    # ------------------------------------------------------------------
    def t(self, key: str, **kwargs: Any) -> str:
        """Traduce ``key`` al idioma actual, con fallback a inglés."""

        with self._lock:
            primary = self._tables.get(self._current, {})
            value = primary.get(key)
            if value is None and self._current != "en":
                value = self._tables.get("en", {}).get(key)
        if value is None:
            # Última red de seguridad: devolver la clave para que sea
            # obvio en la UI cuál falta. Esto facilita depurar.
            value = key

        if kwargs:
            try:
                value = value.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                # Variable faltante o llave huérfana — devolver el
                # template sin sustituir, no romper la UI.
                pass
        return value

    # Atajo para uso en JS / web views: devolver TODO el diccionario.
    def current_table(self) -> dict[str, str]:
        """Devuelve la tabla COMPLETA del idioma actual (con fallback).

        Útil para pasarla en bloque a un ``QWebEngineView`` y permitir
        que el JS haga ``window.shakevisionI18n.t(key)`` sin más
        llamadas al puente.
        """

        with self._lock:
            base = dict(self._tables.get("en", {}))
            if self._current != "en":
                base.update(self._tables.get(self._current, {}))
            return base

    # ------------------------------------------------------------------
    # Carga de ficheros
    # ------------------------------------------------------------------
    def _load_table(self, lang: str) -> None:
        if lang in self._tables:
            return
        path = _LOCALES_DIR / f"{lang}.json"
        try:
            with path.open(encoding="utf-8") as fh:
                self._tables[lang] = json.load(fh)
        except FileNotFoundError:
            logger.warning("Diccionario «%s» no encontrado en %s", lang, path)
            self._tables[lang] = {}
        except json.JSONDecodeError as exc:
            logger.error("Diccionario «%s» mal formado: %s", lang, exc)
            self._tables[lang] = {}

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------
    def _load_persisted_language(self) -> None:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            saved = settings.value(_QSETTINGS_KEY, DEFAULT_LANGUAGE, type=str)
            if saved in SUPPORTED_LANGUAGES:
                self._current = saved
        except Exception:  # noqa: BLE001
            # Sin Qt aún (modo test / headless): quedarse con DEFAULT
            self._current = DEFAULT_LANGUAGE

    def _persist_language(self, lang: str) -> None:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            settings.setValue(_QSETTINGS_KEY, lang)
        except Exception:  # noqa: BLE001
            pass


# ============================================================
# Singleton público (lazy)
# ============================================================
_instance: Optional[_Singleton] = None
_instance_lock = threading.Lock()


def _get_instance() -> _Singleton:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = _Singleton()
    return _instance


class LocaleService:
    """Fachada estática del singleton — sin clase que instanciar."""

    @staticmethod
    def current_language() -> str:
        return _get_instance().current_language()

    @staticmethod
    def set_language(lang: str) -> None:
        _get_instance().set_language(lang)

    @staticmethod
    def available_languages() -> tuple[str, ...]:
        return _get_instance().available_languages()

    @staticmethod
    def language_changed_signal():
        """Devuelve el Signal para que la UI conecte slots."""

        return _get_instance().language_changed

    @staticmethod
    def current_table() -> dict[str, str]:
        return _get_instance().current_table()

    @staticmethod
    def label_for(lang: str) -> str:
        return LANGUAGE_LABELS.get(lang, lang)


def t(key: str, **kwargs: Any) -> str:
    """Atajo top-level: ``from shakevision.i18n import t``."""

    return _get_instance().t(key, **kwargs)
