"""
Pruebas del cliente ShakeNet (FDSN format=text).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shakevision.services.cache import FileCache
from shakevision.services.shakenet import (
    ShakeNetClient,
    ShakeNetError,
    parse_fdsn_text,
)


# ============================================================
# Fixture: respuesta FDSN realista (3 estaciones)
# ============================================================
def _sample_fdsn_text() -> bytes:
    return (
        b"#Network|Station|Latitude|Longitude|Elevation|SiteName|StartTime|EndTime\n"
        b"AM|R0E05|40.4168|-3.7038|650.0|Madrid backyard|2018-01-01T00:00:00|2599-12-31T23:59:59\n"
        b"AM|RB5E8|41.9028|12.4964|45.0|Roma terrazza|2019-03-12T10:00:00|2599-12-31T23:59:59\n"
        b"AM|R7FA5|37.7749|-122.4194|10.0|San Francisco|2020-07-01T00:00:00|2599-12-31T23:59:59\n"
    )


# ============================================================
# parse_fdsn_text
# ============================================================
def test_parse_returns_three_stations() -> None:
    stations = parse_fdsn_text(_sample_fdsn_text())
    assert len(stations) == 3


def test_parse_extracts_all_fields() -> None:
    s = parse_fdsn_text(_sample_fdsn_text())[0]
    assert s.network == "AM"
    assert s.code == "R0E05"
    assert s.latitude == pytest.approx(40.4168)
    assert s.longitude == pytest.approx(-3.7038)
    assert s.elevation_m == pytest.approx(650.0)
    assert "Madrid" in s.site_name
    assert s.nslc_prefix == "AM.R0E05"


def test_parse_skips_comment_and_blank_lines() -> None:
    raw = (
        b"#cabecera\n"
        b"\n"
        b"AM|X|0.0|0.0|0.0\n"
        b"# otro comentario\n"
        b"AM|Y|1.0|2.0|3.0|nombre\n"
    )
    stations = parse_fdsn_text(raw)
    assert len(stations) == 2
    assert {s.code for s in stations} == {"X", "Y"}


def test_parse_ignores_malformed_rows() -> None:
    raw = (
        b"#hdr\n"
        b"AM|TOOSHORT\n"                                # falta lat/lon
        b"AM|BADNUM|not_a_number|0.0|0.0|nombre\n"      # lat inválida
        b"AM|GOOD|10.0|20.0|30.0|ok\n"
    )
    stations = parse_fdsn_text(raw)
    assert len(stations) == 1
    assert stations[0].code == "GOOD"


def test_parse_empty_response_with_header_returns_empty() -> None:
    raw = b"#Network|Station|Latitude|Longitude|Elevation\n"
    assert parse_fdsn_text(raw) == []


def test_parse_no_header_no_data_raises() -> None:
    """Sin cabecera y sin filas válidas asumimos respuesta corrupta."""

    with pytest.raises(ShakeNetError):
        parse_fdsn_text(b"este texto no tiene nada que ver")


# ============================================================
# Cliente con caché
# ============================================================
def test_client_uses_cache_when_fresh(tmp_path: Path) -> None:
    cache = FileCache(cache_dir=tmp_path, default_ttl_s=3600)
    cache.set("shakenet__AM__stations", _sample_fdsn_text())

    client = ShakeNetClient(cache=cache, ttl_s=3600)
    stations = client.fetch_stations(network="AM")
    assert len(stations) == 3
    assert stations[1].code == "RB5E8"
