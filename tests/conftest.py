"""Fixtures compartidas de la suite.

Aísla TODOS los almacenes basados en ``QSettings`` en ficheros ``.ini``
temporales, una vez por test, de modo que la suite **nunca** lea ni borre los
datos reales del usuario (favoritos, métricas de uso, login de GitHub, presets
LAN Shake).

Por qué hace falta
------------------
El constructor ``QSettings(org, app)`` NO respeta ``setPath`` /
``setDefaultFormat`` de forma fiable entre plataformas: en macOS sigue leyendo
el *plist* nativo REAL del usuario. Eso contaminaba los tests (un favorito real
se colaba en ``list_stations()``) y, peor aún, ``_reset_for_tests()`` →
``clear_all()`` BORRABA los datos reales en el teardown. La única forma fiable
es parchear la fábrica ``_settings`` de cada módulo para que devuelva un
``QSettings`` ligado a un fichero concreto dentro de ``tmp_path``.

No-op en entornos sin PySide6 (p. ej. el sandbox sin Qt): los tests puros
siguen ejecutándose igual.
"""

from __future__ import annotations

import importlib

import pytest


# (módulo, nombre de fichero .ini) — todos exponen ``_settings`` y
# ``_reset_for_tests``.
_STORE_MODULES = [
    ("shakevision.services.favorites_store", "favorites"),
    ("shakevision.services.usage_tracker", "usage"),
    ("shakevision.services.github_auth", "github_auth"),
    ("shakevision.services.shake_presets", "shake_presets"),
]


@pytest.fixture(autouse=True)
def _isolate_qsettings_stores(tmp_path, monkeypatch):
    try:
        from PySide6.QtCore import QSettings
    except Exception:
        # Sin Qt no hay almacenes que aislar (y nada que importar romperá).
        yield
        return

    def _factory(path: str):
        # IIFE para fijar ``path`` (evita late-binding en el bucle).
        return lambda: QSettings(path, QSettings.IniFormat)

    resets = []
    for modname, fname in _STORE_MODULES:
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        if hasattr(mod, "_settings"):
            monkeypatch.setattr(
                mod, "_settings", _factory(str(tmp_path / f"{fname}.ini")))
        reset = getattr(mod, "_reset_for_tests", None)
        if callable(reset):
            reset()
            resets.append(reset)

    yield

    # Teardown: monkeypatch sigue activo aquí (se revierte después), así que
    # estos resets escriben en el .ini aislado, nunca en el almacén real.
    for reset in resets:
        try:
            reset()
        except Exception:
            pass
