"""
Pruebas del cliente IRIS / USGS.

Validan que las estaciones devueltas estén etiquetadas con
``provider="usgs"`` y que la caché funcione igual que la de ShakeNet.
"""

from __future__ import annotations

from pathlib import Path

from shakevision.services.cache import FileCache
from shakevision.services.iris import IRISClient


# ============================================================
# Fixture: respuesta FDSN IRIS realista (3 estaciones IU)
# ============================================================
def _sample_iris_text() -> bytes:
    return (
        b"#Network|Station|Latitude|Longitude|Elevation|SiteName|StartTime|EndTime\n"
        b"IU|ANMO|34.946|-106.457|1820.0|Albuquerque, New Mexico|1990-01-01T00:00:00|2599-12-31T23:59:59\n"
        b"IU|PMSA|-64.774|-64.049|40.0|Palmer Station, Antarctica|1995-01-01T00:00:00|2599-12-31T23:59:59\n"
        b"US|LRAL|33.032|-87.001|209.0|Lake Lurleen State Park, Alabama|2002-01-01T00:00:00|2599-12-31T23:59:59\n"
    )


# ============================================================
# Cliente
# ============================================================
def test_iris_tags_stations_as_usgs(tmp_path: Path) -> None:
    """Todas las estaciones devueltas deben llevar provider='usgs'."""

    cache = FileCache(cache_dir=tmp_path, default_ttl_s=3600)
    cache.set("iris__IU_US__stations", _sample_iris_text())

    client = IRISClient(cache=cache, ttl_s=3600)
    stations = client.fetch_stations(networks="IU,US")

    assert len(stations) == 3
    assert all(s.provider == "usgs" for s in stations)


def test_iris_preserves_network_codes(tmp_path: Path) -> None:
    """Los códigos IU y US deben mantenerse separados (no normalizar a AM)."""

    cache = FileCache(cache_dir=tmp_path, default_ttl_s=3600)
    cache.set("iris__IU_US__stations", _sample_iris_text())
    client = IRISClient(cache=cache, ttl_s=3600)
    stations = client.fetch_stations(networks="IU,US")
    networks = {s.network for s in stations}
    assert networks == {"IU", "US"}


def test_iris_extracts_coordinates(tmp_path: Path) -> None:
    cache = FileCache(cache_dir=tmp_path, default_ttl_s=3600)
    cache.set("iris__IU_US__stations", _sample_iris_text())
    anmo = next(
        s for s in IRISClient(cache=cache, ttl_s=3600).fetch_stations()
        if s.code == "ANMO"
    )
    assert anmo.latitude == 34.946
    assert anmo.longitude == -106.457
    assert anmo.elevation_m == 1820.0
    assert "Albuquerque" in anmo.site_name


def test_iris_default_networks_constant() -> None:
    """La constante por defecto debe incluir IU y US."""

    from shakevision.services.iris import DEFAULT_USGS_NETWORKS
    assert "IU" in DEFAULT_USGS_NETWORKS
    assert "US" in DEFAULT_USGS_NETWORKS
