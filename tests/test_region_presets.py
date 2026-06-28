"""Pruebas de ``services.region_presets``."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtCore", reason="i18n usa QSettings")

from shakevision.services import region_presets as rp  # noqa: E402


def test_bboxes_are_geographically_valid() -> None:
    for iso, (min_lat, max_lat, min_lon, max_lon) in rp.COUNTRY_BBOX.items():
        assert -90 <= min_lat < max_lat <= 90, iso
        assert -180 <= min_lon < max_lon <= 180, iso


def test_global_has_no_bbox() -> None:
    assert rp.bbox_for(rp.GLOBAL) is None


def test_bbox_for_known_country() -> None:
    box = rp.bbox_for("JP")
    assert box is not None
    assert box[0] < 35.6 < box[1]      # lat de Tokio dentro
    assert box[2] < 139.7 < box[3]     # lon de Tokio dentro


def test_display_name_localized_via_babel() -> None:
    pytest.importorskip("babel")
    assert rp.display_name("JP", "zh") == "日本"
    assert rp.display_name("JP", "es") == "Japón"


def test_global_name_is_i18n() -> None:
    # No lanza y devuelve algo no vacío (la traducción de region.global).
    assert rp.display_name(rp.GLOBAL, "en")


def test_presets_list_starts_with_global() -> None:
    items = rp.presets("en")
    assert items[0][0] == rp.GLOBAL
    keys = [k for k, _ in items]
    # Todos los del orden que tienen caja están presentes.
    assert "JP" in keys and "CL" in keys
