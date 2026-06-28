"""Pruebas de ``services.fdsn_event`` — construcción de consulta (pura)."""

from __future__ import annotations

import urllib.parse

import pytest

pytest.importorskip("PySide6.QtCore", reason="i18n usa QSettings")

from shakevision.services.fdsn_event import (  # noqa: E402
    FDSN_MAX_LIMIT,
    build_count_url,
    build_query_params,
    build_query_url,
    cache_key_for_url,
)


def _qs(url: str) -> dict:
    return dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))


def test_eventid_overrides_everything() -> None:
    p = build_query_params(eventid="us7000abcd", min_magnitude=5.0,
                           starttime=0)
    assert p == {"format": "geojson", "eventid": "us7000abcd"}


def test_epoch_times_become_iso_utc() -> None:
    # 1700000000 = 2023-11-14 22:13:20 UTC
    p = build_query_params(starttime=1700000000.0, endtime=1700003600.0)
    assert p["starttime"] == "2023-11-14T22:13:20"
    assert p["endtime"] == "2023-11-14T23:13:20"


def test_string_times_passthrough() -> None:
    p = build_query_params(starttime="2011-01-01", endtime="2012-01-01")
    assert p["starttime"] == "2011-01-01"
    assert p["endtime"] == "2012-01-01"


def test_bbox_and_magnitude_params() -> None:
    p = build_query_params(
        min_magnitude=4.5, max_magnitude=7.0,
        min_latitude=30.0, max_latitude=46.0,
        min_longitude=129.0, max_longitude=146.0)
    assert p["minmagnitude"] == 4.5
    assert p["maxmagnitude"] == 7.0
    assert p["minlatitude"] == 30.0
    assert p["maxlongitude"] == 146.0


def test_orderby_falls_back_to_time_on_garbage() -> None:
    assert build_query_params(orderby="bogus")["orderby"] == "time"
    assert build_query_params(orderby="magnitude")["orderby"] == "magnitude"


def test_limit_is_clamped() -> None:
    assert build_query_params(limit=999999)["limit"] == FDSN_MAX_LIMIT
    assert build_query_params(limit=0)["limit"] == 1


def test_offset_only_when_above_one() -> None:
    assert "offset" not in build_query_params(offset=1)
    assert build_query_params(offset=501)["offset"] == 501


def test_url_is_wellformed() -> None:
    url = build_query_url(min_magnitude=5.0, orderby="magnitude", limit=100)
    assert url.startswith(
        "https://earthquake.usgs.gov/fdsnws/event/1/query?")
    q = _qs(url)
    assert q["format"] == "geojson"
    assert q["minmagnitude"] == "5.0"
    assert q["orderby"] == "magnitude"


def test_cache_key_is_short_fixed_length() -> None:
    """La clave de caché NO debe crecer con la URL (evita 'File name too long')."""

    long_url = build_query_url(
        starttime="2025-06-22T02:39:25", endtime="2026-06-22T02:39:25",
        min_magnitude=4.5, max_magnitude=10.0,
        min_latitude=24.0, max_latitude=46.0,
        min_longitude=122.0, max_longitude=146.0, limit=500)
    key = cache_key_for_url(long_url)
    assert key.startswith("fdsn__")
    assert len(key) == len("fdsn__") + 64       # sha256 hex
    # Distintas URLs → distintas claves; misma URL → misma clave (estable).
    assert key == cache_key_for_url(long_url)
    assert key != cache_key_for_url(long_url + "&x=1")
    # Seguro como nombre de fichero (sin separadores ni longitud excesiva).
    assert "/" not in key and len(key) < 100


def test_count_url_points_to_count_endpoint() -> None:
    url = build_count_url(
        min_magnitude=4.5, starttime="2020-01-01", endtime="2021-01-01",
        min_latitude=24.0, max_latitude=46.0)
    assert url.startswith(
        "https://earthquake.usgs.gov/fdsnws/event/1/count?")
    q = _qs(url)
    # Filtros conservados, pero sin format/limit/orderby.
    assert q["minmagnitude"] == "4.5"
    assert q["starttime"] == "2020-01-01"
    assert "format" not in q and "limit" not in q and "orderby" not in q


def test_parser_reused_on_sample_geojson() -> None:
    """El cliente reutiliza parse_usgs_geojson: validamos con una muestra."""

    from shakevision.services.usgs import parse_usgs_geojson
    sample = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"id":"us7000test","properties":{"mag":6.1,"place":"Tokyo, Japan",'
        b'"time":1700000000000,"url":"http://x","alert":"green","sig":600},'
        b'"geometry":{"type":"Point","coordinates":[139.7,35.6,30.0]}}]}'
    )
    quakes = parse_usgs_geojson(sample)
    assert len(quakes) == 1
    assert quakes[0].id == "us7000test"
    assert quakes[0].magnitude == 6.1
    assert quakes[0].depth_km == 30.0
