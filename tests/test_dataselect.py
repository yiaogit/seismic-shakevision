"""
Pruebas de ``services.dataselect``.

Mockean ``urllib.request.urlopen`` para validar:
  * Construcción correcta de la URL FDSN (parámetros + ``loc="--"``).
  * Caching (segundo fetch no golpea la red).
  * 204 / 404 lanzan ``NoDataAvailable``.
  * Duración > MAX se rechaza antes de tocar la red.
  * Fallo de red sin caché → ``DataselectError``.
  * Fallo de red con caché obsoleta → devuelve caché vieja.
"""

from __future__ import annotations

import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from shakevision.services.cache import FileCache
from shakevision.services.dataselect import (
    DATASELECT_URL,
    DataselectClient,
    DataselectError,
    MAX_DURATION_S,
    NoDataAvailable,
)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def cache(tmp_path: Path) -> FileCache:
    return FileCache(cache_dir=tmp_path)


@pytest.fixture
def client(cache: FileCache) -> DataselectClient:
    return DataselectClient(cache=cache)


def _utc(year=2024, month=1, day=1, hour=0, minute=0, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _fake_response(status: int = 200, body: bytes = b"MSEEDDATA") -> MagicMock:
    """Mock context manager replicando urllib.urlopen()."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


# ============================================================
# URL building
# ============================================================
def test_url_includes_all_fdsn_params(client: DataselectClient) -> None:
    """La URL construida debe llevar net/sta/loc/cha/start/end + format=miniseed."""

    captured = {}
    def fake_open(req, timeout=None):
        captured["url"] = req.full_url
        return _fake_response(200, b"DATA")

    with patch("urllib.request.urlopen", side_effect=fake_open):
        client.fetch_miniseed(
            "IU", "ANMO", "00", "BHZ",
            _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5),
        )

    url = captured["url"]
    assert url.startswith(DATASELECT_URL)
    assert "net=IU" in url
    assert "sta=ANMO" in url
    assert "loc=00" in url
    assert "cha=BHZ" in url
    assert "starttime=2024-01-01T00%3A00%3A00" in url   # ":" url-encoded
    assert "endtime=2024-01-01T00%3A05%3A00" in url
    assert "format=miniseed" in url
    assert "nodata=404" in url


def test_url_empty_location_serializes_as_double_dash(client: DataselectClient) -> None:
    """FDSN exige ``loc=--`` para location vacío."""

    captured = {}
    def fake_open(req, timeout=None):
        captured["url"] = req.full_url
        return _fake_response(200, b"X")

    with patch("urllib.request.urlopen", side_effect=fake_open):
        client.fetch_miniseed(
            "AM", "R0E05", "", "EHZ",
            _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 1),
        )
    assert "loc=--" in captured["url"]


# ============================================================
# Validación de parámetros
# ============================================================
def test_endtime_before_starttime_raises(client: DataselectClient) -> None:
    with pytest.raises(DataselectError, match="posterior"):
        client.fetch_miniseed(
            "IU", "ANMO", "00", "BHZ",
            _utc(2024, 1, 1, 1), _utc(2024, 1, 1, 0),
        )


def test_duration_above_max_raises(client: DataselectClient) -> None:
    start = _utc(2024, 1, 1)
    end = start + timedelta(seconds=MAX_DURATION_S + 60)
    with pytest.raises(DataselectError, match="supera"):
        client.fetch_miniseed("IU", "ANMO", "00", "BHZ", start, end)


# ============================================================
# Errores HTTP
# ============================================================
def test_404_raises_no_data_available(client: DataselectClient) -> None:
    def fake_open(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "No Data", {}, None)

    with patch("urllib.request.urlopen", side_effect=fake_open):
        with pytest.raises(NoDataAvailable):
            client.fetch_miniseed(
                "IU", "ANMO", "00", "BHZ",
                _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5),
            )


def test_500_raises_dataselect_error(client: DataselectClient) -> None:
    def fake_open(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable",
                                      {}, None)

    with patch("urllib.request.urlopen", side_effect=fake_open):
        # v0.7.6: error message goes through i18n (t("error.dataselect.contact"));
        # match on "dataselect" which is stable across all 4 locales (EN/ES/FR/ZH).
        with pytest.raises(DataselectError, match="dataselect"):
            client.fetch_miniseed(
                "IU", "ANMO", "00", "BHZ",
                _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5),
            )


def test_204_status_treated_as_no_data(client: DataselectClient) -> None:
    """Algunos despliegues FDSN devuelven 204 No Content en lugar de 404."""

    with patch("urllib.request.urlopen", return_value=_fake_response(204, b"")):
        with pytest.raises(NoDataAvailable):
            client.fetch_miniseed(
                "IU", "ANMO", "00", "BHZ",
                _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5),
            )


# ============================================================
# Caching
# ============================================================
def test_second_call_hits_cache(client: DataselectClient) -> None:
    body = b"SOMEMSEED"
    call_count = {"n": 0}

    def fake_open(req, timeout=None):
        call_count["n"] += 1
        return _fake_response(200, body)

    args = ("IU", "ANMO", "00", "BHZ",
            _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5))

    with patch("urllib.request.urlopen", side_effect=fake_open):
        a = client.fetch_miniseed(*args)
        b = client.fetch_miniseed(*args)
    assert a == body
    assert b == body
    assert call_count["n"] == 1, "second call should hit cache, not network"


def test_force_refresh_skips_cache(client: DataselectClient) -> None:
    call_count = {"n": 0}

    def fake_open(req, timeout=None):
        call_count["n"] += 1
        return _fake_response(200, b"X")

    args = ("IU", "ANMO", "00", "BHZ",
            _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5))

    with patch("urllib.request.urlopen", side_effect=fake_open):
        client.fetch_miniseed(*args)
        client.fetch_miniseed(*args, force_refresh=True)
    assert call_count["n"] == 2


def test_network_failure_with_stale_cache_returns_stale(
    cache: FileCache, tmp_path: Path,
) -> None:
    """Si IRIS está caído y hay caché vieja, devolverla en lugar de fallar."""

    # TTL muy corto + sembramos caché manualmente.
    client = DataselectClient(cache=cache, ttl_s=0.01)
    args = ("IU", "ANMO", "00", "BHZ",
            _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5))

    # Primera llamada: éxito → guarda en caché
    with patch("urllib.request.urlopen", return_value=_fake_response(200, b"OLD")):
        client.fetch_miniseed(*args)

    # Pasada la TTL, segunda llamada con red caída
    import time
    time.sleep(0.05)

    def boom(req, timeout=None):
        raise urllib.error.URLError("Network is unreachable")

    with patch("urllib.request.urlopen", side_effect=boom):
        result = client.fetch_miniseed(*args)
    assert result == b"OLD"


# ============================================================
# Acepta float Unix timestamps además de datetime
# ============================================================
def test_accepts_unix_timestamp(client: DataselectClient) -> None:
    captured = {}
    def fake_open(req, timeout=None):
        captured["url"] = req.full_url
        return _fake_response(200, b"X")

    ts_start = _utc(2024, 1, 1).timestamp()
    ts_end = _utc(2024, 1, 1, 0, 5).timestamp()

    with patch("urllib.request.urlopen", side_effect=fake_open):
        client.fetch_miniseed("IU", "ANMO", "00", "BHZ", ts_start, ts_end)
    assert "starttime=2024-01-01T00%3A00%3A00" in captured["url"]
