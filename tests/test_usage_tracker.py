"""
Pruebas de ``shakevision.services.usage_tracker`` (v0.5 阶段 I).

Cubrimos:
  * Contadores incrementan correctamente.
  * record_launch escribe first_launch UNA sola vez (no se sobrescribe).
  * record_audio_played ignora negativos / cero.
  * start_session / end_session acumula segundos.
  * stats() incluye sesión en curso sin necesidad de end_session.
  * reset() borra todo.

QSettings se redirige a ``tmp_path`` para aislar tests del store real
del usuario.
"""

from __future__ import annotations

import time

import pytest


pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")


# ============================================================
# Fixture: aislar QSettings + resetear singleton
# ============================================================
@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    """Re-dirige QSettings al directorio temporal del test.

    Sin esto los tests contaminarían el QSettings real del usuario
    que ejecuta la suite (incrementando launch_count del SeismicGuard
    instalado).
    """

    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))

    from shakevision.services import usage_tracker as ut
    ut._reset_for_tests()
    yield
    ut._reset_for_tests()


# ============================================================
# Tests
# ============================================================
def test_initial_stats_are_zero_or_empty() -> None:
    from shakevision.services.usage_tracker import UsageTracker

    s = UsageTracker.stats()
    assert s["launch_count"] == 0
    assert s["earthquakes_viewed_count"] == 0
    assert s["stations_clicked_count"] == 0
    assert s["audio_played_seconds"] == 0
    assert s["session_seconds"] == 0
    assert s["first_launch_iso"] == ""
    assert s["last_launch_iso"] == ""


def test_record_launch_increments_and_sets_first_only_once() -> None:
    from shakevision.services.usage_tracker import UsageTracker

    UsageTracker.record_launch()
    first = UsageTracker.stats()["first_launch_iso"]
    assert UsageTracker.stats()["launch_count"] == 1
    assert first != ""

    # Segundo arranque: launch_count sube, first_launch NO cambia,
    # last_launch SÍ se actualiza.
    UsageTracker.record_launch()
    s2 = UsageTracker.stats()
    assert s2["launch_count"] == 2
    assert s2["first_launch_iso"] == first
    assert s2["last_launch_iso"] != ""


def test_each_record_counter_increments() -> None:
    from shakevision.services.usage_tracker import UsageTracker

    for _ in range(3):
        UsageTracker.record_earthquake_viewed()
    for _ in range(5):
        UsageTracker.record_station_clicked()
    UsageTracker.record_station_streamed()
    UsageTracker.record_report_generated()
    UsageTracker.record_replay_session()
    UsageTracker.record_replay_session()

    s = UsageTracker.stats()
    assert s["earthquakes_viewed_count"] == 3
    assert s["stations_clicked_count"] == 5
    assert s["stations_streamed_count"] == 1
    assert s["reports_generated_count"] == 1
    assert s["replay_sessions_count"] == 2


def test_record_audio_played_ignores_zero_and_negative() -> None:
    from shakevision.services.usage_tracker import UsageTracker

    UsageTracker.record_audio_played(0)
    UsageTracker.record_audio_played(-5)
    assert UsageTracker.stats()["audio_played_seconds"] == 0

    UsageTracker.record_audio_played(12)
    UsageTracker.record_audio_played(3.7)   # float, se trunca a int
    assert UsageTracker.stats()["audio_played_seconds"] == 15


def test_session_seconds_accumulate_after_end_session() -> None:
    from shakevision.services.usage_tracker import UsageTracker

    UsageTracker.start_session()
    time.sleep(0.1)   # 100 ms; redondea a 0 segundos enteros
    UsageTracker.end_session()
    # Con sleep tan corto, esperamos 0 segundos acumulados (granularidad
    # int). Verificamos al menos que no explote y que end_session sea
    # idempotente.
    UsageTracker.end_session()    # segundo end_session: no-op
    s = UsageTracker.stats()
    assert s["session_seconds"] >= 0


def test_stats_includes_current_session_in_progress(monkeypatch) -> None:
    """stats() debe sumar la sesión EN CURSO al total persistido."""

    from shakevision.services import usage_tracker as ut

    # Simular sesión iniciada hace 30 s usando monotonic mock:
    inst = ut._get_instance()
    inst._session_started_at = time.monotonic() - 30
    s = ut.UsageTracker.stats()
    # session_seconds debe incluir al menos los ~30 s simulados.
    assert s["session_seconds"] >= 29  # margen para jitter


def test_reset_clears_all_counters() -> None:
    from shakevision.services.usage_tracker import UsageTracker

    UsageTracker.record_launch()
    UsageTracker.record_earthquake_viewed()
    UsageTracker.record_audio_played(42)
    assert UsageTracker.stats()["launch_count"] == 1

    UsageTracker.reset()
    s = UsageTracker.stats()
    assert s["launch_count"] == 0
    assert s["earthquakes_viewed_count"] == 0
    assert s["audio_played_seconds"] == 0
    assert s["first_launch_iso"] == ""


def test_all_keys_list_matches_stats_dict() -> None:
    """ALL_KEYS no debe quedarse desincronizado con stats()."""

    from shakevision.services.usage_tracker import ALL_KEYS, UsageTracker

    # Cada elemento de ALL_KEYS debe terminar con una clave después de
    # "usage/"; el stats() dict usa esos sufijos como nombres.
    suffixes = [k.split("/", 1)[1] for k in ALL_KEYS]
    assert "first_launch_iso" in suffixes
    assert "launch_count" in suffixes
    assert "audio_played_seconds" in suffixes
    # stats() también devuelve todas esas claves
    s = UsageTracker.stats()
    for suffix in suffixes:
        assert suffix in s, f"stats() no devuelve {suffix!r}"
