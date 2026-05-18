"""
Pruebas de ``sources.replay``.

Cubren el núcleo puro (_ReplayClock) sin Qt, y el flujo de alto nivel
de ReplaySource con un mock de ``obspy.Stream`` construido en memoria.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

# Permite que el módulo se importe aunque PySide6 no esté presente.
pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.sources.replay import (    # noqa: E402
    DEFAULT_SPEED,
    SPEED_OPTIONS,
    ReplaySource,
    _ReplayClock,
    _slice_or_zeros,
)


# ============================================================
# _ReplayClock — núcleo puro, sin Qt
# ============================================================
def test_clock_initial_state() -> None:
    c = _ReplayClock(duration_s=10.0)
    assert c.cursor_s == 0.0
    assert c.paused is False
    assert c.speed == DEFAULT_SPEED
    assert c.at_end is False


def test_clock_tick_advances_at_real_time() -> None:
    c = _ReplayClock(duration_s=10.0, speed=1.0)
    # Primera tick: solo inicializa last_real_t, no avanza.
    c.tick(now=100.0)
    assert c.cursor_s == 0.0
    # Segunda tick: avanza dt segundos
    prev, cur = c.tick(now=101.5)
    assert prev == 0.0
    assert cur == pytest.approx(1.5)


def test_clock_tick_respects_speed_factor() -> None:
    c = _ReplayClock(duration_s=100.0, speed=10.0)
    c.tick(now=0.0)
    _, cur = c.tick(now=1.0)
    assert cur == pytest.approx(10.0)


def test_clock_does_not_advance_when_paused() -> None:
    c = _ReplayClock(duration_s=100.0, speed=10.0)
    c.tick(now=0.0)
    c.paused = True
    _, cur = c.tick(now=5.0)
    assert cur == 0.0


def test_clock_clamps_to_duration() -> None:
    c = _ReplayClock(duration_s=2.0, speed=1.0)
    c.tick(now=0.0)
    _, cur = c.tick(now=100.0)
    assert cur == 2.0
    assert c.at_end is True


def test_clock_seek() -> None:
    c = _ReplayClock(duration_s=10.0)
    c.seek_to(5.0)
    assert c.cursor_s == 5.0
    c.seek_to(-100.0)
    assert c.cursor_s == 0.0
    c.seek_to(999.0)
    assert c.cursor_s == 10.0


def test_clock_reset() -> None:
    c = _ReplayClock(duration_s=10.0)
    c.tick(now=0.0)
    c.tick(now=5.0)
    c.reset()
    assert c.cursor_s == 0.0
    assert c.last_real_t == 0.0


# ============================================================
# _slice_or_zeros
# ============================================================
def test_slice_returns_correct_chunk() -> None:
    arr = np.arange(10, dtype=np.float32)
    out = _slice_or_zeros(arr, 2, 5)
    assert out.tolist() == [2.0, 3.0, 4.0]


def test_slice_pads_beyond_end() -> None:
    arr = np.arange(5, dtype=np.float32)
    out = _slice_or_zeros(arr, 3, 8)
    # 3,4 reales + 3 ceros
    assert out.size == 5
    assert out.tolist() == [3.0, 4.0, 0.0, 0.0, 0.0]


def test_slice_none_returns_zeros() -> None:
    out = _slice_or_zeros(None, 0, 7)
    assert out.size == 7
    assert np.all(out == 0)


# ============================================================
# ReplaySource — con stream sintético
# ============================================================
def _fake_stream(sample_rate: int = 100, duration_s: float = 5.0):
    """Construye un objeto que imita obspy.Stream con 3 trazas Z/N/E."""

    n = int(duration_s * sample_rate)
    fake_start = MagicMock()
    fake_start.timestamp = 1_700_000_000.0

    traces = []
    for ch_letter in ("Z", "N", "E"):
        tr = MagicMock()
        tr.stats.channel = f"BH{ch_letter}"
        tr.stats.sampling_rate = sample_rate
        tr.stats.npts = n
        tr.stats.starttime = fake_start
        tr.data = np.sin(np.linspace(0, 6.28, n)).astype(np.float32)
        traces.append(tr)

    stream = MagicMock()
    stream.__iter__.return_value = iter(traces)
    stream.__len__.return_value = len(traces)
    # ObsPy permite stream[0]: simulamos con side_effect.
    stream.__getitem__.side_effect = lambda i: traces[i]
    return stream


def test_replay_source_constructs_from_stream(qt_app) -> None:
    stream = _fake_stream(duration_s=5.0)
    src = ReplaySource(stream=stream, speed=2.0, station_label="X")
    assert src.duration_seconds == pytest.approx(5.0)
    assert src.speed == 2.0
    assert src.station_label == "X"
    assert src.is_running is False


def test_replay_source_set_speed_updates_clock(qt_app) -> None:
    src = ReplaySource(stream=_fake_stream(), speed=1.0)
    src.set_speed(10.0)
    assert src.speed == 10.0


def test_replay_source_seek_clamps(qt_app) -> None:
    src = ReplaySource(stream=_fake_stream(duration_s=5.0))
    src.seek(2.5)
    assert src.cursor_seconds == 2.5
    src.seek(-1)
    assert src.cursor_seconds == 0.0
    src.seek(999)
    assert src.cursor_seconds == 5.0


def test_replay_source_pause_blocks_emission(qt_app) -> None:
    src = ReplaySource(stream=_fake_stream(duration_s=2.0), speed=1.0)
    src.start()
    src.pause()
    assert src.is_paused is True
    src.resume()
    assert src.is_paused is False
    src.stop()
    assert src.is_running is False


def test_replay_source_stop_resets_cursor(qt_app) -> None:
    src = ReplaySource(stream=_fake_stream(duration_s=3.0), speed=1.0)
    src.start()
    src.seek(2.0)
    src.stop()
    assert src.is_running is False
    assert src.cursor_seconds == 0.0


def test_replay_source_speed_options_constant() -> None:
    assert DEFAULT_SPEED in SPEED_OPTIONS
    assert sorted(SPEED_OPTIONS) == list(SPEED_OPTIONS)
    assert SPEED_OPTIONS[0] < SPEED_OPTIONS[-1]


# ============================================================
# Qt app fixture (compartido por todos los tests que crean QObjects)
# ============================================================
import os                                  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
