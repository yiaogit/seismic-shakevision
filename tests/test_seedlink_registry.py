"""
Pruebas del mapa de servidores SeedLink y de los campos opcionales del
``StationPreset``. No requieren PySide6.
"""

from __future__ import annotations

from shakevision.config import (
    DEFAULT_SEEDLINK_HOST,
    DEFAULT_SEEDLINK_PORT,
    IRIS_SEEDLINK_HOST,
    IRIS_SEEDLINK_PORT,
    SEEDLINK_CHANNELS,
    SEEDLINK_LOCATIONS,
    SEEDLINK_SERVERS,
    StationPreset,
    seedlink_channels_for,
    seedlink_location_for,
    seedlink_server_for,
)


# ============================================================
# Mapa SEEDLINK_SERVERS
# ============================================================
def test_iris_backbone_networks_route_to_rtserve() -> None:
    """Las redes profesionales (IU/US/II/IC) van a rtserve.iris."""

    for net in ("IU", "US", "II", "IC"):
        host, port = SEEDLINK_SERVERS[net]
        assert host == IRIS_SEEDLINK_HOST
        assert port == IRIS_SEEDLINK_PORT


def test_am_network_routes_to_local_rs() -> None:
    """AM (Raspberry Shake) va a rs.local — solo LAN."""

    host, port = SEEDLINK_SERVERS["AM"]
    assert host == DEFAULT_SEEDLINK_HOST
    assert port == DEFAULT_SEEDLINK_PORT


def test_seedlink_server_for_known_network() -> None:
    assert seedlink_server_for("IU") == (IRIS_SEEDLINK_HOST, IRIS_SEEDLINK_PORT)
    assert seedlink_server_for("AM") == (DEFAULT_SEEDLINK_HOST, DEFAULT_SEEDLINK_PORT)


def test_seedlink_server_for_unknown_falls_back_to_iris() -> None:
    """Red desconocida → IRIS (asumimos público FDSN)."""

    host, port = seedlink_server_for("ZZ")
    assert host == IRIS_SEEDLINK_HOST
    assert port == IRIS_SEEDLINK_PORT


def test_iris_host_is_well_known_endpoint() -> None:
    """Sanity: el host IRIS es el endpoint público estándar."""

    assert IRIS_SEEDLINK_HOST == "rtserve.iris.washington.edu"
    assert IRIS_SEEDLINK_PORT == 18000


# ============================================================
# StationPreset con campos opcionales seedlink_host/port
# ============================================================
def test_preset_without_explicit_host_is_backwards_compatible() -> None:
    """El campo seedlink_host es opcional; los presets antiguos siguen funcionando."""

    p = StationPreset(label="x", network="AM", station="LOCAL")
    assert p.seedlink_host is None
    assert p.seedlink_port is None


def test_preset_can_carry_explicit_host_and_port() -> None:
    """Los presets construidos desde el globo llevan host/port explícito."""

    p = StationPreset(
        label="IU.ANMO — Albuquerque",
        network="IU",
        station="ANMO",
        location="*",
        channel="BHZ",
        seedlink_host="rtserve.iris.washington.edu",
        seedlink_port=18000,
    )
    assert p.seedlink_host == "rtserve.iris.washington.edu"
    assert p.seedlink_port == 18000
    assert p.channel == "BHZ"


def test_preset_is_frozen() -> None:
    """StationPreset debe seguir siendo inmutable (hashable, usable en sets)."""

    p1 = StationPreset(label="x", network="IU", station="ANMO")
    p2 = StationPreset(label="x", network="IU", station="ANMO")
    # Misma firma → mismo hash
    assert hash(p1) == hash(p2)


# ============================================================
# Canales SeedLink por red
# ============================================================
def test_am_uses_short_period_channels() -> None:
    """Raspberry Shake (AM) usa EHZ/EHN/EHE — instrumento corto."""

    assert SEEDLINK_CHANNELS["AM"] == ("EHZ", "EHN", "EHE")


def test_iris_networks_use_broadband_channels() -> None:
    """IRIS IU/US/II/IC usan BHZ/BHN/BHE — broadband 40 Hz."""

    for net in ("IU", "US", "II", "IC"):
        assert SEEDLINK_CHANNELS[net] == ("BHZ", "BHN", "BHE")


def test_seedlink_channels_for_unknown_defaults_broadband() -> None:
    """Red desconocida → broadband (asumimos red profesional)."""

    assert seedlink_channels_for("ZZ") == ("BHZ", "BHN", "BHE")


def test_seedlink_channels_for_am() -> None:
    assert seedlink_channels_for("AM") == ("EHZ", "EHN", "EHE")


# ============================================================
# Locations SeedLink por red
# ============================================================
def test_iris_locations_default_to_00() -> None:
    """IRIS IU/US/II/IC tienen el broadband en location '00'."""

    for net in ("IU", "US", "II", "IC"):
        assert SEEDLINK_LOCATIONS[net] == "00"


def test_am_location_is_empty() -> None:
    """Raspberry Shake no usa location code."""

    assert SEEDLINK_LOCATIONS["AM"] == ""


def test_seedlink_location_for_unknown_defaults_00() -> None:
    """Red desconocida → '00' (la más común en FDSN)."""

    assert seedlink_location_for("ZZ") == "00"
