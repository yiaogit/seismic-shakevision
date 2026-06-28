"""
Pruebas del ``TimezoneService``.

Cubren:
  * Detección del sistema (best effort — algunas CI no tienen tz data).
  * Validación de nombres IANA.
  * Format helpers.
  * Persistencia (en memoria via singleton).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.services.timezone_service import (  # noqa: E402
    TimezoneService,
    available_timezones,
    detect_system_timezone,
)


# ============================================================
# Detección
# ============================================================
def test_detect_returns_string_or_none() -> None:
    """detect_system_timezone() siempre devuelve str o None, nunca lanza."""

    result = detect_system_timezone()
    assert result is None or isinstance(result, str)


def test_available_timezones_includes_utc() -> None:
    tzs = available_timezones()
    assert "UTC" in tzs


def test_available_timezones_is_long_enough() -> None:
    """En sistemas con tzdata hay cientos; con fallback al menos 1."""

    tzs = available_timezones()
    assert len(tzs) >= 1


# ============================================================
# set_timezone
# ============================================================
def test_set_timezone_accepts_valid_iana() -> None:
    ok = TimezoneService.set_timezone("America/Mexico_City")
    assert ok is True
    assert TimezoneService.current_iana() == "America/Mexico_City"


def test_set_timezone_rejects_garbage() -> None:
    """Nombres inválidos no cambian el estado."""

    TimezoneService.set_timezone("UTC")  # baseline conocido
    assert TimezoneService.set_timezone("Not/A_Timezone_123") is False
    assert TimezoneService.current_iana() == "UTC"


def test_set_timezone_is_idempotent() -> None:
    TimezoneService.set_timezone("UTC")
    # Una segunda llamada con el mismo valor no falla
    assert TimezoneService.set_timezone("UTC") is True


# ============================================================
# Formatters
# ============================================================
def test_format_local_returns_string() -> None:
    TimezoneService.set_timezone("UTC")
    formatted = TimezoneService.format_local(1700000000.0)
    # Año 2023
    assert "2023" in formatted


def test_to_iso_local_uses_user_tz() -> None:
    """ISO de timestamp Unix incluye offset de la zona."""

    TimezoneService.set_timezone("UTC")
    iso_utc = TimezoneService.to_iso_local(1700000000.0)
    assert "+00:00" in iso_utc

    TimezoneService.set_timezone("America/Mexico_City")
    iso_mx = TimezoneService.to_iso_local(1700000000.0)
    # México central es UTC-6 (sin DST en noviembre 2023)
    assert "-06:00" in iso_mx or "-05:00" in iso_mx


def test_format_utc_ignores_user_tz_and_labels() -> None:
    """format_utc() siempre rinde UTC con etiqueta, sin importar la zona."""

    TimezoneService.set_timezone("America/Mexico_City")  # NO debe afectar
    out = TimezoneService.format_utc(1700000000.0)
    # 2023-11-14 22:13:20 UTC
    assert out.endswith("UTC")
    assert "2023-11-14" in out
    assert "22:13:20" in out


def test_to_iso_utc_has_z_suffix() -> None:
    TimezoneService.set_timezone("America/Mexico_City")
    iso = TimezoneService.to_iso_utc(1700000000.0)
    assert iso == "2023-11-14T22:13:20Z"


# ============================================================
# Address (free text)
# ============================================================
def test_address_is_persisted_in_session() -> None:
    TimezoneService.set_address("Mexico City")
    assert TimezoneService.address() == "Mexico City"


def test_address_strips_whitespace() -> None:
    TimezoneService.set_address("  CDMX  ")
    assert TimezoneService.address() == "CDMX"


def test_address_can_be_cleared() -> None:
    TimezoneService.set_address("X")
    TimezoneService.set_address("")
    assert TimezoneService.address() == ""


# ============================================================
# Limpieza
# ============================================================
@pytest.fixture(autouse=True)
def _reset_tz():
    yield
    TimezoneService.set_timezone("UTC")
    TimezoneService.set_address("")
