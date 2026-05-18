"""
ClearCacheService — borra TODO el estado persistente del usuario
(v0.7 阶段 C).

Concepto
--------
"Clear cache" en este contexto significa: restaurar la app al estado de
primera instalación. Tras llamar a ``clear_all()`` y reiniciar la app
el usuario verá el splash + onboarding wizard otra vez, sin idioma /
zona horaria / tema / favoritos / estaciones LAN / cualquier
preferencia personalizada.

Qué se borra
------------
1. **QSettings (organización "SeismicGuard")** — TODAS las apps:
   * ``Locale``     (idioma)
   * ``Theme``      (tema claro/oscuro/auto)
   * ``Layer``      (modo estándar/profesional)
   * ``Onboarding`` (flag de wizard completado + Localízame)
   * ``Usage``      (UsageTracker — lanzamientos, métricas)
   * ``Favorites``  (FavoritesStore — eventos + estaciones)
   * ``Shakes``     (My Shakes LAN presets)
   * ``GitHub``     (token + perfil de OAuth)
   * ``Pro``        (geometría de ventana Pro / Workbench)

2. **Caché de disco** — todo el árbol ``~/.cache/shakevision/``:
   * GeoJSON cacheado de USGS / ShakeNet
   * Reportes HTML/PDF generados
   * Cualquier mini-SEED grabado por el recorder

3. **Nada más** — NO se tocan archivos de música, documentos del
   usuario, ni nada fuera del cache y QSettings de la app.

Política
--------
* Idempotente. Si una sección ya está vacía, no es error.
* Mejor esfuerzo. Si una sección falla (permisos, IO error) se loggea
  warning y se sigue con las demás — siempre mejor borrar parcial que
  no borrar nada.
* No reinicia la app. El UI que llama a ``clear_all()`` debe hacer
  ``QApplication.quit()`` justo después; el usuario tiene que volver
  a lanzar la app manualmente para ver el efecto.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QSettings


logger = logging.getLogger(__name__)


# ============================================================
# Inventario de QSettings apps bajo la organización SeismicGuard.
# Mantener sincronizado con los _QSETTINGS_APP de cada módulo:
#   shakevision/i18n/service.py            → "Locale"
#   shakevision/ui/theme_manager.py        → "Theme"
#   shakevision/ui/layer_mode_manager.py   → "Layer"
#   shakevision/ui/onboarding_wizard.py    → "Onboarding"
#   shakevision/services/usage_tracker.py  → "Usage"
#   shakevision/services/favorites_store.py→ "Favorites"
#   shakevision/services/shake_presets.py  → "Shakes"
#   shakevision/services/github_auth.py    → "GitHub"
#   shakevision/ui/pro_window.py           → "Pro"
# ============================================================
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APPS: tuple[str, ...] = (
    "Locale",
    "Theme",
    "Layer",
    "Onboarding",
    "Usage",
    "Activity",
    "Favorites",
    "Shakes",
    "GitHub",
    "Pro",
)

# Carpeta de caché de disco — debe coincidir con DEFAULT_CACHE_DIR
# de services/cache.py.
_DEFAULT_CACHE_DIR: Path = Path.home() / ".cache" / "shakevision"


def clear_qsettings(apps: Iterable[str] = _QSETTINGS_APPS) -> dict[str, str]:
    """Borra QSettings para cada app dada. Devuelve resumen por app.

    Cada valor del dict resultante es "ok" o un mensaje de error.
    Idempotente — borrar un QSettings vacío también devuelve "ok".
    """

    results: dict[str, str] = {}
    for app in apps:
        try:
            s = QSettings(_QSETTINGS_ORG, app)
            s.clear()
            s.sync()
            results[app] = "ok"
            logger.info("clear_cache: QSettings(%s/%s) borrado",
                        _QSETTINGS_ORG, app)
        except Exception as exc:  # noqa: BLE001
            results[app] = f"error: {exc!s}"
            logger.warning("clear_cache: borrar QSettings(%s/%s) falló (%s)",
                           _QSETTINGS_ORG, app, exc)
    return results


def clear_disk_cache(cache_dir: Path | None = None) -> dict[str, str]:
    """Borra recursivamente la carpeta de caché de disco.

    Si la carpeta no existe, devuelve {"cache": "no existía"}.
    Si existe pero algún archivo no se puede borrar, devuelve un
    resumen del error.
    """

    target = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    if not target.exists():
        logger.info("clear_cache: %s no existía", target)
        return {"cache": "no existía"}
    try:
        shutil.rmtree(target)
        # Re-crear la carpeta vacía para que el próximo arranque no
        # tenga que crearla y caché-init no falle.
        target.mkdir(parents=True, exist_ok=True)
        logger.info("clear_cache: %s recreado vacío", target)
        return {"cache": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("clear_cache: borrar %s falló (%s)", target, exc)
        return {"cache": f"error: {exc!s}"}


def clear_all(cache_dir: Path | None = None) -> dict[str, str]:
    """Borra QSettings + disco cache. Devuelve resumen unificado."""

    summary: dict[str, str] = {}
    summary.update(clear_qsettings())
    summary.update(clear_disk_cache(cache_dir))
    return summary
