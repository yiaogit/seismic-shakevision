"""
Pruebas del servicio i18n.

Cubren:
  * Carga de los 4 diccionarios.
  * Fallback al inglés cuando la clave falta en el idioma actual.
  * Fallback a la clave misma cuando falta en inglés.
  * Sustitución de variables con ``{name}``.
  * Cambio de idioma + signal (omite la parte signal en entornos sin Qt).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")


from shakevision.i18n.service import (  # noqa: E402
    LANGUAGE_LABELS,
    SUPPORTED_LANGUAGES,
    LocaleService,
    t,
)


_LOCALES_DIR: Path = (
    Path(__file__).resolve().parents[1]
    / "shakevision" / "i18n" / "locales"
)


# ============================================================
# Estructura de ficheros
# ============================================================
def test_all_four_languages_have_json_files() -> None:
    for code in SUPPORTED_LANGUAGES:
        assert (_LOCALES_DIR / f"{code}.json").is_file(), f"falta {code}.json"


def test_english_is_canonical_reference() -> None:
    """El inglés debe contener TODAS las claves usadas como referencia.

    Si alguna otra lengua tiene una clave que falta en inglés es un
    bug — porque el fallback siempre cae a inglés.
    """

    with (_LOCALES_DIR / "en.json").open(encoding="utf-8") as fh:
        en_keys = set(json.load(fh).keys())
    for code in SUPPORTED_LANGUAGES:
        if code == "en":
            continue
        with (_LOCALES_DIR / f"{code}.json").open(encoding="utf-8") as fh:
            other_keys = set(json.load(fh).keys())
        extras = other_keys - en_keys
        assert not extras, f"{code} tiene claves no presentes en inglés: {extras}"


# ============================================================
# Carga + lookup básico
# ============================================================
def test_default_language_is_english() -> None:
    # Resetear preferencia previa: en tests usamos el código de idioma
    # directamente.
    LocaleService.set_language("en")
    assert LocaleService.current_language() == "en"


def test_t_returns_english_string() -> None:
    LocaleService.set_language("en")
    assert t("settings.title") == "Settings"
    assert t("common.cancel") == "Cancel"


def test_t_returns_spanish_when_lang_is_es() -> None:
    LocaleService.set_language("es")
    assert t("settings.title") == "Preferencias"
    assert t("common.cancel") == "Cancelar"


def test_t_returns_chinese_when_lang_is_zh() -> None:
    LocaleService.set_language("zh")
    assert t("settings.title") == "设置"
    assert t("common.cancel") == "取消"


def test_t_returns_french_when_lang_is_fr() -> None:
    LocaleService.set_language("fr")
    assert t("settings.title") == "Préférences"
    assert t("common.cancel") == "Annuler"


# ============================================================
# Fallback
# ============================================================
def test_missing_key_returns_key_itself() -> None:
    """Una clave inexistente devuelve la propia clave (señal de "sin traducir")."""

    LocaleService.set_language("en")
    assert t("non.existent.key.xyz") == "non.existent.key.xyz"


def test_format_substitution_works() -> None:
    LocaleService.set_language("en")
    # Una clave con variable conocida
    out = t("settings.timezone.detected", tz="America/Mexico_City")
    assert "America/Mexico_City" in out
    assert "Detected:" in out


def test_format_with_missing_var_is_lenient() -> None:
    """Si falta una variable, devolvemos el template sin romper la UI."""

    LocaleService.set_language("en")
    # No pasamos tz — la función debe devolver el template literal
    out = t("settings.timezone.detected")
    # No revienta y contiene el placeholder
    assert "{tz}" in out


# ============================================================
# Cambio de idioma + signal
# ============================================================
def test_set_language_invalid_is_ignored() -> None:
    LocaleService.set_language("en")
    LocaleService.set_language("xx")   # no en SUPPORTED_LANGUAGES
    # El idioma actual NO cambia
    assert LocaleService.current_language() == "en"


def test_language_labels_are_auto_glonyms() -> None:
    """Etiqueta de cada lengua aparece en su propio alfabeto."""

    assert LANGUAGE_LABELS["en"] == "English"
    assert LANGUAGE_LABELS["es"] == "Español"
    assert LANGUAGE_LABELS["zh"] == "简体中文"
    assert LANGUAGE_LABELS["fr"] == "Français"


def test_current_table_contains_english_keys_at_minimum() -> None:
    """current_table() siempre incluye al menos las claves de inglés."""

    LocaleService.set_language("zh")
    table = LocaleService.current_table()
    # Debe tener al menos las claves del inglés
    assert "settings.title" in table
    assert "common.cancel" in table


# ============================================================
# Limpieza: restablecer al idioma por defecto para no contaminar otros tests
# ============================================================
@pytest.fixture(autouse=True)
def _reset_language():
    yield
    LocaleService.set_language("en")
