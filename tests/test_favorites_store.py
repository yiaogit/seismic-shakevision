"""
Pruebas de ``shakevision.services.favorites_store`` (v0.5 阶段 J).

Cubrimos:
  * add/remove/is_favorite/list para ambas categorías.
  * Re-add de estación NO duplica (devuelve False) pero actualiza meta.
  * Persistencia: round-trip por recrear el singleton.
  * Límite FIFO al saturar MAX_STATIONS / MAX_EVENTS.
  * export_to_dict / import_from_dict — incluyendo replace=True.
  * Signal ``changed`` se emite tras cada mutación.

QSettings aislado en ``tmp_path`` para no contaminar al usuario real.
"""

from __future__ import annotations

import pytest


pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))

    from shakevision.services import favorites_store as fs
    fs._reset_for_tests()
    yield
    fs._reset_for_tests()


# ============================================================
# Estaciones
# ============================================================
def test_add_station_then_check_and_list() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    assert FavoritesStore.list_stations() == []
    assert FavoritesStore.is_favorite_station("AM", "R0E05") is False

    new_added = FavoritesStore.add_station(
        "AM", "R0E05", site_name="Madrid", provider="shakenet")
    assert new_added is True
    assert FavoritesStore.is_favorite_station("AM", "R0E05") is True

    lst = FavoritesStore.list_stations()
    assert len(lst) == 1
    assert lst[0].network == "AM" and lst[0].code == "R0E05"
    assert lst[0].site_name == "Madrid"


def test_add_existing_station_returns_false_but_updates_metadata() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    FavoritesStore.add_station("AM", "R0E05", site_name="Madrid")
    again = FavoritesStore.add_station(
        "AM", "R0E05", site_name="Madrid Centro")
    assert again is False
    lst = FavoritesStore.list_stations()
    assert lst[0].site_name == "Madrid Centro"


def test_remove_station() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    FavoritesStore.add_station("AM", "R0E05")
    assert FavoritesStore.remove_station("AM", "R0E05") is True
    assert FavoritesStore.remove_station("AM", "R0E05") is False
    assert FavoritesStore.is_favorite_station("AM", "R0E05") is False


def test_station_limit_fifo() -> None:
    from shakevision.services import favorites_store as fs

    for i in range(fs.MAX_STATIONS + 3):
        fs.FavoritesStore.add_station("XX", f"S{i:04d}")
    lst = fs.FavoritesStore.list_stations()
    assert len(lst) == fs.MAX_STATIONS
    # Los 3 más antiguos deben haber sido descartados; el primero
    # restante debe ser "S0003".
    assert lst[0].code == "S0003"
    assert lst[-1].code == f"S{fs.MAX_STATIONS + 2:04d}"


# ============================================================
# Eventos
# ============================================================
def test_add_event_dedup_and_list() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    assert FavoritesStore.add_event(
        "us7000xyz", 5.4, "Tokio", 1_700_000_000.0) is True
    assert FavoritesStore.add_event(
        "us7000xyz", 5.4, "Tokio", 1_700_000_000.0) is False
    assert FavoritesStore.is_favorite_event("us7000xyz") is True
    assert len(FavoritesStore.list_events()) == 1


def test_remove_event() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    FavoritesStore.add_event("us1", 4.5, "X", 1.0)
    assert FavoritesStore.remove_event("us1") is True
    assert FavoritesStore.remove_event("us1") is False


def test_event_limit_fifo() -> None:
    from shakevision.services import favorites_store as fs

    for i in range(fs.MAX_EVENTS + 5):
        fs.FavoritesStore.add_event(f"ev{i}", 3.0, "X", float(i))
    lst = fs.FavoritesStore.list_events()
    assert len(lst) == fs.MAX_EVENTS
    assert lst[0].id == "ev5"


# ============================================================
# Persistencia
# ============================================================
def test_round_trip_via_singleton_reload() -> None:
    from shakevision.services import favorites_store as fs
    from shakevision.services.favorites_store import FavoritesStore

    FavoritesStore.add_station("AM", "R0E05", site_name="Madrid")
    FavoritesStore.add_event("us7000abc", 6.1, "Lima", 1_700_000_100.0)

    # Simular reinicio: vaciar singleton (pero NO QSettings).
    fs._instance = None

    # Tras "reinicio", FavoritesStore debe recargar desde QSettings.
    stations = FavoritesStore.list_stations()
    events = FavoritesStore.list_events()
    assert len(stations) == 1 and stations[0].code == "R0E05"
    assert len(events) == 1 and events[0].id == "us7000abc"
    assert events[0].magnitude == pytest.approx(6.1)


# ============================================================
# Export / Import
# ============================================================
def test_export_import_round_trip() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    FavoritesStore.add_station("AM", "R0E05", site_name="Madrid")
    FavoritesStore.add_event("us1", 5.0, "X", 1.0)
    payload = FavoritesStore.export_to_dict()
    assert "stations" in payload and "events" in payload

    FavoritesStore.clear_all()
    assert FavoritesStore.list_stations() == []
    added = FavoritesStore.import_from_dict(payload)
    assert added == 2
    assert FavoritesStore.is_favorite_station("AM", "R0E05")
    assert FavoritesStore.is_favorite_event("us1")


def test_import_merges_without_duplicating() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    FavoritesStore.add_station("AM", "R0E05")
    payload = {"stations": [{"network": "AM", "code": "R0E05"}],
               "events": []}
    added = FavoritesStore.import_from_dict(payload)
    assert added == 0   # ya existía


def test_import_replace_clears_existing() -> None:
    from shakevision.services.favorites_store import FavoritesStore

    FavoritesStore.add_station("OLD", "OLD")
    payload = {"stations": [{"network": "NEW", "code": "NEW"}],
               "events": []}
    added = FavoritesStore.import_from_dict(payload, replace=True)
    assert added == 1
    lst = FavoritesStore.list_stations()
    assert len(lst) == 1 and lst[0].network == "NEW"


# ============================================================
# Signal changed
# ============================================================
def test_changed_signal_fires_on_mutation(qapp_factory) -> None:
    from shakevision.services.favorites_store import FavoritesStore

    _app = qapp_factory()
    fired = []
    FavoritesStore.changed_signal().connect(lambda: fired.append(True))

    FavoritesStore.add_station("AM", "R0E05")
    FavoritesStore.add_event("us1", 5.0, "X", 1.0)
    FavoritesStore.remove_station("AM", "R0E05")
    # 3 mutaciones → al menos 3 emisiones
    assert len(fired) >= 3


@pytest.fixture(scope="session")
def qapp_factory():
    from PySide6.QtWidgets import QApplication

    def _factory():
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    return _factory
