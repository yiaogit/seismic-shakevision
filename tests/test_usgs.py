"""
Pruebas del cliente USGS y del parser GeoJSON.

Usamos un fixture local en lugar de la red real para que sean
deterministas y rápidas.
"""

from __future__ import annotations

import json

import pytest

from shakevision.services.data_models import PagerLevel
from shakevision.services.usgs import USGSError, parse_usgs_geojson


# ============================================================
# Fixture: GeoJSON USGS sintético pero realista
# ============================================================
def _sample_geojson_bytes() -> bytes:
    doc = {
        "type": "FeatureCollection",
        "metadata": {"generated": 1715600000000, "title": "USGS All Day"},
        "features": [
            {
                "type": "Feature",
                "id": "us7000m9p2",
                "properties": {
                    "mag": 5.6,
                    "place": "26 km W of Anchorage",
                    "time": 1715599800000,   # ms UNIX
                    "url": "https://earthquake.usgs.gov/event/us7000m9p2",
                    "alert": "yellow",
                    "sig": 480,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [-150.13, 61.20, 28.5],
                },
            },
            {
                "type": "Feature",
                "id": "ci40123",
                "properties": {
                    "mag": 3.1,
                    "place": "10 km E of Ridgecrest, CA",
                    "time": 1715593200000,
                    "url": "",
                    "alert": None,
                    "sig": 120,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [-117.5, 35.6, 5.0],
                },
            },
        ],
    }
    return json.dumps(doc).encode("utf-8")


# ============================================================
# parse_usgs_geojson
# ============================================================
def test_parse_returns_list_in_reverse_chronological_order() -> None:
    quakes = parse_usgs_geojson(_sample_geojson_bytes())
    assert len(quakes) == 2
    # El más reciente (ts mayor) debe quedar primero
    assert quakes[0].timestamp_unix > quakes[1].timestamp_unix


def test_parse_extracts_all_fields_correctly() -> None:
    quakes = parse_usgs_geojson(_sample_geojson_bytes())
    q = quakes[0]
    assert q.id == "us7000m9p2"
    assert q.magnitude == 5.6
    assert q.depth_km == 28.5
    assert q.longitude == pytest.approx(-150.13)
    assert q.latitude == pytest.approx(61.20)
    assert q.pager is PagerLevel.YELLOW
    assert q.significance == 480
    assert q.timestamp_unix == 1715599800.0


def test_parse_handles_missing_alert() -> None:
    quakes = parse_usgs_geojson(_sample_geojson_bytes())
    minor = next(q for q in quakes if q.id == "ci40123")
    assert minor.pager is None


def test_parse_skips_malformed_features() -> None:
    """Una feature sin coordenadas o sin tiempo se ignora silenciosamente."""

    doc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature", "id": "broken1",
                "properties": {"mag": 4.0, "place": "X", "time": 1715600000000,
                               "url": ""},
                "geometry": {"type": "Point", "coordinates": [10.0]},  # incompleto
            },
            {
                "type": "Feature", "id": "broken2",
                "properties": {"mag": 4.0, "place": "Y", "url": ""},  # falta time
                "geometry": {"type": "Point", "coordinates": [10.0, 20.0, 5.0]},
            },
            {
                "type": "Feature", "id": "good",
                "properties": {"mag": 4.0, "place": "Z", "time": 1715600000000,
                               "url": ""},
                "geometry": {"type": "Point", "coordinates": [10.0, 20.0, 5.0]},
            },
        ],
    }
    quakes = parse_usgs_geojson(json.dumps(doc).encode())
    assert len(quakes) == 1
    assert quakes[0].id == "good"


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(USGSError):
        parse_usgs_geojson(b"not json at all")


def test_parse_missing_features_array_raises() -> None:
    bad = json.dumps({"type": "FeatureCollection"}).encode()
    with pytest.raises(USGSError):
        parse_usgs_geojson(bad)


def test_parse_empty_features_returns_empty_list() -> None:
    doc = {"type": "FeatureCollection", "features": []}
    assert parse_usgs_geojson(json.dumps(doc).encode()) == []


# ============================================================
# Cliente con caché (sin tocar la red)
# ============================================================
def test_usgs_client_uses_cache_when_fresh(tmp_path) -> None:
    """Si la caché tiene contenido fresco, fetch_recent NO debe pegar a la red."""

    from shakevision.services.cache import FileCache
    from shakevision.services.usgs import USGSClient

    cache = FileCache(cache_dir=tmp_path, default_ttl_s=3600)
    cache.set("usgs__all_day__geojson", _sample_geojson_bytes())

    client = USGSClient(cache=cache, ttl_s=3600)
    quakes = client.fetch_recent(period="all_day")
    assert len(quakes) == 2
    assert quakes[0].magnitude == 5.6


def test_usgs_client_unknown_period_raises(tmp_path) -> None:
    from shakevision.services.cache import FileCache
    from shakevision.services.usgs import USGSClient

    client = USGSClient(cache=FileCache(cache_dir=tmp_path))
    with pytest.raises(USGSError):
        client.fetch_recent(period="not_a_real_feed")
