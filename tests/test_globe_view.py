"""
Pruebas de la capa Python del globo.

Validamos las funciones de serialización Python → JSON (no requieren
Qt) y la presencia de los archivos web. El widget Qt completo se
prueba en CI con QT_QPA_PLATFORM=offscreen.
"""

from __future__ import annotations

import json

import pytest

# globe_view importa PySide6 en cabecera; saltamos si no está
pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.services.data_models import (  # noqa: E402
    Earthquake,
    PagerLevel,
    ShakeStation,
)


# ============================================================
# Serializadores (no requieren PySide6 cargado)
# ============================================================
def test_serialize_stations_returns_expected_keys() -> None:
    from shakevision.ui.globe_view import serialize_stations

    s = [
        ShakeStation(network="AM", code="R0E05",
                     latitude=40.4, longitude=-3.7, elevation_m=650.0,
                     site_name="Madrid"),
    ]
    out = serialize_stations(s)
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["network"] == "AM"
    assert out[0]["code"] == "R0E05"
    assert out[0]["lat"] == pytest.approx(40.4)
    assert out[0]["lng"] == pytest.approx(-3.7)
    assert out[0]["elevation"] == pytest.approx(650.0)
    assert out[0]["site"] == "Madrid"


def test_serialize_earthquakes_keys_and_pager_handling() -> None:
    from shakevision.ui.globe_view import serialize_earthquakes

    quakes = [
        Earthquake(
            id="us123", timestamp_unix=1700000000.0,
            longitude=-122.4, latitude=37.8,
            depth_km=10.0, magnitude=5.4, place="SF",
            url="https://...",
            pager=PagerLevel.YELLOW, significance=480,
        ),
        Earthquake(
            id="ci456", timestamp_unix=1700000100.0,
            longitude=10.0, latitude=20.0,
            depth_km=5.0, magnitude=3.1, place="X",
            url="",
            pager=None, significance=10,
        ),
    ]
    out = serialize_earthquakes(quakes)
    assert len(out) == 2
    assert out[0]["id"] == "us123"
    assert out[0]["mag"] == 5.4
    assert out[0]["depth"] == 10.0
    assert out[0]["pager"] == "yellow"
    assert out[1]["pager"] is None
    # Todo el resultado debe ser JSON-serializable sin custom encoder
    json.dumps(out)


def test_serialize_handles_empty_lists() -> None:
    from shakevision.ui.globe_view import serialize_earthquakes, serialize_stations

    assert serialize_stations([]) == []
    assert serialize_earthquakes([]) == []


# ============================================================
# Recursos web presentes
# ============================================================
def test_web_globe_files_exist() -> None:
    from shakevision.ui.globe_view import WEB_GLOBE_DIR

    assert WEB_GLOBE_DIR.is_dir()
    for name in ("index.html", "globe.js", "styles.css"):
        path = WEB_GLOBE_DIR / name
        assert path.is_file(), f"falta {name}"
        assert path.stat().st_size > 0


def test_index_html_references_required_components() -> None:
    """El HTML debe cargar Globe.gl, qwebchannel y nuestro globe.js."""

    from shakevision.ui.globe_view import WEB_GLOBE_DIR

    html = (WEB_GLOBE_DIR / "index.html").read_text(encoding="utf-8")
    assert "globe.gl" in html.lower()
    assert "qwebchannel" in html.lower()
    assert "globe.js" in html
    # Contenedor con id="globe"
    assert 'id="globe"' in html


def test_globe_js_exposes_window_api() -> None:
    """globe.js debe exponer setDevices/setEarthquakes/setLayer."""

    from shakevision.ui.globe_view import WEB_GLOBE_DIR

    js = (WEB_GLOBE_DIR / "globe.js").read_text(encoding="utf-8")
    for name in ("setDevices", "setEarthquakes", "setLayer", "shakevisionGlobe"):
        assert name in js, f"globe.js no expone {name}"


# ============================================================
# Bridge slots (sin instanciar QObject completo: solo introspección)
# ============================================================
def test_globe_bridge_signal_names() -> None:
    """Verificamos los nombres de las señales para no romper la API JS."""

    pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")

    from shakevision.ui.globe_view import GlobeBridge

    # Las señales deben existir como atributos de clase
    for sig in ("station_clicked", "earthquake_clicked",
                "layer_changed", "globe_ready"):
        assert hasattr(GlobeBridge, sig), f"falta señal {sig}"
