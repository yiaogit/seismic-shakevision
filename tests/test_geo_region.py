"""
Pruebas de ``services.geo_region``.

El sandbox del asistente NO tiene ``obspy`` ni ``reverse_geocoder`` → esas
rutas deben degradar a ``None`` sin lanzar. La localización de país (babel)
sí es verificable aquí.
"""

from __future__ import annotations

import pytest

from shakevision.services import geo_region as gr


# ----------------------------------------------------------------------
# Localización de país (babel / CLDR) — autoritativa, sin traducir a mano
# ----------------------------------------------------------------------
def test_localized_country_name_multilingual() -> None:
    pytest.importorskip("babel", reason="babel no instalado")
    assert gr.localized_country_name("JP", "zh") == "日本"
    assert gr.localized_country_name("JP", "es") == "Japón"
    assert gr.localized_country_name("JP", "fr") == "Japon"
    assert gr.localized_country_name("CL", "zh") == "智利"


def test_localized_country_name_falls_back_to_iso() -> None:
    # Código no presente en CLDR → devuelve el propio código, nunca lanza.
    assert gr.localized_country_name("QQ", "en") == "QQ"
    # Cualquier ISO no vacío produce una cadena no vacía.
    assert gr.localized_country_name("JP", "en")


def test_localized_country_name_empty_is_none() -> None:
    assert gr.localized_country_name("", "en") is None


# ----------------------------------------------------------------------
# Degradación elegante cuando faltan obspy / reverse_geocoder
# ----------------------------------------------------------------------
def test_fe_region_none_without_obspy() -> None:
    """Sin obspy, fe_region devuelve None (no lanza). Con obspy, una tupla."""

    result = gr.fe_region(35.0, 139.0)
    assert result is None or (
        isinstance(result, tuple) and isinstance(result[0], int))


def test_country_iso_none_without_rg() -> None:
    result = gr.country_iso(35.0, 139.0)
    assert result is None or isinstance(result, str)


def test_search_fields_always_includes_place() -> None:
    """Aunque falten obspy/rg, place EN siempre está presente y buscable."""

    fields = gr.search_fields_for(35.0, 139.0, "zh", place="Tokyo, Japan")
    assert "Tokyo, Japan" in fields
    # Todas las piezas son cadenas no vacías.
    assert all(isinstance(f, str) and f for f in fields)
