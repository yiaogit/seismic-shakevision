"""Tests del listado de grabaciones locales (puro, sin ObsPy ni Qt)."""

from __future__ import annotations

from shakevision.processing.recorder import (
    build_event_filename_local,
    list_recordings,
    parse_recording_name,
)


def test_parse_recording_name_roundtrip():
    name = build_event_filename_local("IU", "KONO", 1781661778.0)
    ts, net, sta = parse_recording_name(name)
    assert net == "IU" and sta == "KONO"
    assert abs(ts - 1781661778.0) < 1.0


def test_parse_recording_name_station_with_underscore_kept():
    # La estación puede contener guiones bajos; la red es el primer campo.
    parsed = parse_recording_name("20260101T000000_AM_R0E_05.mseed")
    assert parsed is not None
    _ts, net, sta = parsed
    assert net == "AM" and sta == "R0E_05"


def test_parse_recording_name_rejects_junk():
    assert parse_recording_name("notes.txt") is None
    assert parse_recording_name("bad.mseed") is None
    assert parse_recording_name("99999999T999999_IU_X.mseed") is None


def test_list_recordings_sorted_recent_first(tmp_path):
    (tmp_path / "20200101T000000_IU_AAA.mseed").write_bytes(b"x")
    (tmp_path / "20260101T000000_IU_BBB.mseed").write_bytes(b"x")
    (tmp_path / "ignore.txt").write_bytes(b"x")
    recs = list_recordings(tmp_path)
    assert [r.station for r in recs] == ["BBB", "AAA"]   # reciente primero


def test_list_recordings_missing_dir(tmp_path):
    assert list_recordings(tmp_path / "nope") == []
