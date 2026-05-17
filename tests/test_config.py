"""
Prueba de humo de la configuración global.

Verifica que la importación de ``shakevision.config`` produzca una
instancia válida de ``AppConfig`` con valores razonables. Es la primera
red de seguridad y se debe ejecutar en cada commit.
"""

from __future__ import annotations

from shakevision.config import (
    DEFAULT_APP_CONFIG,
    AppConfig,
    FilterConfig,
    StationPreset,
    StreamConfig,
    TriggerConfig,
)


def test_default_config_is_app_config() -> None:
    """La configuración por defecto debe ser una instancia de ``AppConfig``."""

    assert isinstance(DEFAULT_APP_CONFIG, AppConfig)
    assert isinstance(DEFAULT_APP_CONFIG.stream, StreamConfig)
    assert isinstance(DEFAULT_APP_CONFIG.filt, FilterConfig)
    assert isinstance(DEFAULT_APP_CONFIG.trigger, TriggerConfig)


def test_default_stations_not_empty() -> None:
    """Debe existir al menos una estación predefinida (la simulada)."""

    assert len(DEFAULT_APP_CONFIG.stations) >= 1
    assert all(isinstance(s, StationPreset) for s in DEFAULT_APP_CONFIG.stations)


def test_filter_band_is_consistent() -> None:
    """El corte inferior debe ser estrictamente menor que el superior."""

    f = DEFAULT_APP_CONFIG.filt
    assert 0.0 < f.lowcut_hz < f.highcut_hz


def test_trigger_thresholds_are_ordered() -> None:
    """El umbral de activación debe ser mayor que el de desactivación."""

    t = DEFAULT_APP_CONFIG.trigger
    assert t.threshold_on > t.threshold_off > 0
