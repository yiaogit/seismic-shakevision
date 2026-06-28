"""Pruebas de ``processing.event_filter`` (puro, sin Qt)."""

from __future__ import annotations

from dataclasses import dataclass

from shakevision.processing.event_filter import (
    filter_quakes,
    fold,
    passes,
    structured_tokens,
    text_matches,
)


@dataclass
class _Q:
    magnitude: float
    timestamp_unix: float
    place: str
    depth_km: float = 10.0


_QUAKES = [
    _Q(2.1, 1_000.0, "Off the coast of Japan"),
    _Q(4.8, 2_000.0, "Central Chile"),
    _Q(6.2, 3_000.0, "Tokyo, Japan"),
    _Q(3.0, 4_000.0, "Nevada"),
]


def test_no_filters_returns_all() -> None:
    assert filter_quakes(_QUAKES) == _QUAKES


def test_min_magnitude() -> None:
    out = filter_quakes(_QUAKES, min_mag=4.0)
    assert [q.magnitude for q in out] == [4.8, 6.2]


def test_time_range_inclusive() -> None:
    out = filter_quakes(_QUAKES, t_from=2_000.0, t_to=3_000.0)
    assert [q.timestamp_unix for q in out] == [2_000.0, 3_000.0]


def test_query_is_case_insensitive_substring() -> None:
    out = filter_quakes(_QUAKES, query="japan")
    assert {q.place for q in out} == {
        "Off the coast of Japan", "Tokyo, Japan"}


def test_filters_combine_as_and() -> None:
    out = filter_quakes(_QUAKES, min_mag=5.0, query="japan")
    assert [q.place for q in out] == ["Tokyo, Japan"]


def test_passes_predicate_direct() -> None:
    assert passes(magnitude=5.0, timestamp_unix=10.0, place="X", min_mag=4.0)
    assert not passes(magnitude=3.0, timestamp_unix=10.0, place="X", min_mag=4.0)
    assert not passes(
        magnitude=5.0, timestamp_unix=10.0, place="X", t_from=20.0)


# ----------------------------------------------------------------------
# Búsqueda multilingüe + plegado de acentos + tokens
# ----------------------------------------------------------------------
def test_fold_strips_accents_and_case() -> None:
    assert fold("Japón") == "japon"
    assert fold("Île-de-France") == "ile-de-france"
    assert fold("中文") == "中文"          # CJK intacto


def test_text_matches_all_tokens_and() -> None:
    fields = ["Tokyo, Japan", "日本", "本州东岸"]
    assert text_matches("japan", fields)
    assert text_matches("日本", fields)          # campo localizado
    assert text_matches("tokyo japan", fields)   # AND de 2 tokens
    assert not text_matches("japan chile", fields)
    assert text_matches("", fields)              # vacío → todo pasa


def test_query_accent_insensitive() -> None:
    qs = [_Q(4.0, 1.0, "Central Chile"), _Q(4.0, 2.0, "Sur de España")]
    # buscar sin tilde encuentra "España"
    out = filter_quakes(qs, query="espana")
    assert [q.place for q in out] == ["Sur de España"]


def test_extra_text_enables_localized_search() -> None:
    qs = [_Q(5.0, 1.0, "Off the coast of Japan"),
          _Q(5.0, 2.0, "Central Chile")]
    loc = {"Off the coast of Japan": ["日本以东海域", "日本"],
           "Central Chile": ["智利中部", "智利"]}
    out = filter_quakes(qs, query="日本", extra_text=lambda ev: loc[ev.place])
    assert [q.place for q in out] == ["Off the coast of Japan"]
    out2 = filter_quakes(qs, query="智利", extra_text=lambda ev: loc[ev.place])
    assert [q.place for q in out2] == ["Central Chile"]


def test_depth_range() -> None:
    qs = [_Q(4.0, 1.0, "shallow", depth_km=5.0),
          _Q(4.0, 2.0, "mid", depth_km=70.0),
          _Q(4.0, 3.0, "deep", depth_km=300.0)]
    out = filter_quakes(qs, min_depth=50.0, max_depth=100.0)
    assert [q.place for q in out] == ["mid"]


def test_max_magnitude() -> None:
    out = filter_quakes(_QUAKES, max_mag=4.0)
    assert sorted(q.magnitude for q in out) == [2.1, 3.0]


# ----------------------------------------------------------------------
# structured_tokens — confirmar evento por ID / magnitud / año / profundidad
# ----------------------------------------------------------------------
def test_structured_tokens_contents() -> None:
    toks = structured_tokens(
        eventid="us7000abcd", magnitude=6.1,
        timestamp_unix=1700000000.0, depth_km=30.0)
    assert "us7000abcd" in toks
    assert "m6.1" in toks and "6.1" in toks
    assert "2023" in toks
    assert "30km" in toks


def test_search_by_id_and_year_via_extra_text() -> None:
    qs = [_Q(6.1, 1700000000.0, "Tokyo, Japan"),
          _Q(4.0, 1300000000.0, "Central Chile")]
    ids = {qs[0].place: "us7000abcd", qs[1].place: "cl123"}
    def extra(ev):
        return [ev.place] + structured_tokens(
            eventid=ids[ev.place], magnitude=ev.magnitude,
            timestamp_unix=ev.timestamp_unix, depth_km=ev.depth_km)
    # por ID
    assert [q.place for q in filter_quakes(
        qs, query="us7000abcd", extra_text=extra)] == ["Tokyo, Japan"]
    # por año
    assert [q.place for q in filter_quakes(
        qs, query="2023", extra_text=extra)] == ["Tokyo, Japan"]
    # combinado: lugar + magnitud
    assert [q.place for q in filter_quakes(
        qs, query="japan 6", extra_text=extra)] == ["Tokyo, Japan"]


def test_structured_tokens_handles_missing() -> None:
    assert structured_tokens() == []
    assert structured_tokens(magnitude=None, depth_km=None) == []
