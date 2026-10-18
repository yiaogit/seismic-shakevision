"""Migración de entradas antiguas sin station/place/mag."""

from __future__ import annotations

import json

from shakevision.services import activity_log


class _FakeSettings:
    def __init__(self, value: str) -> None:
        self.value_text = value
        self.saved: str | None = None

    def value(self, _key, default="", type=str):  # noqa: A002
        return self.value_text if self.value_text else default

    def setValue(self, _key, value) -> None:  # noqa: N802
        self.saved = str(value)


def test_removes_legacy_placeholders(monkeypatch) -> None:
    entries = [
        {"ts": 1, "kind": "station_clicked", "params": {"station": "?"}},
        {"ts": 2, "kind": "quake_viewed",
         "params": {"place": "?", "mag": "?"}},
        {"ts": 3, "kind": "station_clicked",
         "params": {"station": "IU.PAB"}},
        {"ts": 4, "kind": "quake_viewed",
         "params": {"place": "Tokyo", "mag": "5.4"}},
    ]
    fake = _FakeSettings(json.dumps(entries))
    monkeypatch.setattr(activity_log, "_settings", lambda: fake)
    activity_log.ActivityLog._reset_for_tests()
    recent = activity_log.ActivityLog.list_recent(10)
    assert [e["ts"] for e in recent] == [4, 3]
    assert fake.saved is not None
    assert len(json.loads(fake.saved)) == 2
