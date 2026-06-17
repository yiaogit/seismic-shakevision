#!/usr/bin/env python3
"""
download_globe_assets.py — descarga los assets opcionales del globo.

Uso
---
    python3 scripts/download_globe_assets.py            # descarga solo
                                                          lo que falte
    python3 scripts/download_globe_assets.py --force    # re-descarga
                                                          aunque exista
    python3 scripts/download_globe_assets.py --only day   # solo Blue Marble
    python3 scripts/download_globe_assets.py --only borders   # solo GeoJSON

Qué descarga
------------
1. ``earth-day.jpg`` — NASA Blue Marble (2048×1024 JPG, ~700 KB).
   Activa el modo "día" de alta calidad. Sin él, el modo día usa
   la textura topológica gris (funciona pero menos bonito).

2. ``world.json`` — Natural Earth ne_110m countries (~200 KB).
   Activa las fronteras de país cyan en modo profesional. Sin él,
   el modo profesional solo muestra la esfera holográfica.

Política de fallback
--------------------
Cada asset tiene 2-3 mirrors. El script intenta uno tras otro hasta
encontrar uno que responda. Si TODOS fallan (sin red, GitHub caído…)
imprime el error y sigue con el siguiente asset — no aborta entero.

Validación
----------
Tras la descarga verificamos:
  * tamaño mínimo (alguien podría haber descargado HTML de error)
  * para JSON: que parsee como FeatureCollection
  * para JPG: que los primeros bytes sean magic SOI (FF D8 FF)
Si la validación falla, borramos el archivo y reportamos.

Compatible con Python 3.8+ (stdlib).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


# ============================================================
# Configuración
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = PROJECT_ROOT / "shakevision" / "web" / "globe" / "lib"


# Cada asset tiene fallbacks ordenados por preferencia.
ASSETS = {
    "day": {
        "filename": "earth-day.jpg",
        "min_size": 50_000,        # 50 KB mínimo (sanity)
        "max_size": 5_000_000,     # 5 MB máximo (evitar bajarse un panorama)
        "mirrors": [
            # ECharts examples mirror — pequeño, optimizado, sirve bien
            "https://echarts.apache.org/examples/data-gl/asset/data/earth.jpg",
            # NASA Visible Earth oficial (más grande, 2048×1024)
            "https://eoimages.gsfc.nasa.gov/images/imagerecords/"
            "73000/73580/world.topo.bathy.200401.3x2048x1024.jpg",
            # GitHub mirror de uno de los samples populares de Three.js
            "https://raw.githubusercontent.com/mrdoob/three.js/dev/"
            "examples/textures/planets/earth_atmos_2048.jpg",
        ],
        "validator": "jpg",
    },
    # v12.3: re-descarga earth-night.jpg con un mirror MEJOR — el de
    # three-globe (que viene por default en install_libs.sh) es una
    # textura de 1024×512 con luces muy débiles. Las alternativas
    # listadas son NASA Black Marble auténticos a 2048×1024.
    "night": {
        "filename": "earth-night.jpg",
        "min_size": 100_000,
        "max_size": 6_000_000,
        "mirrors": [
            # NASA Earth Observatory Black Marble 2016 (3 km/pixel, 2k JPG)
            # — la versión Apolo del look "Earth at Night".
            "https://eoimages.gsfc.nasa.gov/images/imagerecords/"
            "144000/144898/BlackMarble_2016_3km_geo.jpg",
            # NASA City Lights 2012 (alternativa clásica, alta resolución)
            "https://eoimages.gsfc.nasa.gov/images/imagerecords/"
            "79000/79765/dnb_land_ocean_ice.2012.3600x1800.jpg",
            # Three.js earth_lights — alternativa más pequeña pero
            # con luces visibles (NASA-derived, ~270 KB)
            "https://raw.githubusercontent.com/mrdoob/three.js/dev/"
            "examples/textures/planets/earth_lights_2048.png",
        ],
        "validator": "jpg",   # acepta también png (header check abajo)
    },
    "borders": {
        "filename": "world.json",
        "min_size": 30_000,        # 30 KB mínimo
        "max_size": 8_000_000,     # 8 MB máximo
        "mirrors": [
            # Natural Earth 1:110M (~200 KB) — perfecto para nuestra escala
            "https://raw.githubusercontent.com/nvkelso/"
            "natural-earth-vector/master/geojson/"
            "ne_110m_admin_0_countries.geojson",
            # Mirror alternativo (mismo repo, branch release)
            "https://raw.githubusercontent.com/nvkelso/"
            "natural-earth-vector/v5.1.2/geojson/"
            "ne_110m_admin_0_countries.geojson",
        ],
        "validator": "geojson",
    },
}


# ============================================================
# Utilidades
# ============================================================
def _human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.0f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.0f} TB"


def _download(url: str, dest: Path, timeout: int = 30) -> Optional[int]:
    """Intenta descargar ``url`` a ``dest``. Devuelve bytes escritos
    o None si falla. Usa un User-Agent normalillo porque algunos
    mirrors rechazan a Python por defecto."""

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SeismicGuard-AssetDownloader/0.6 "
                          "(+https://github.com/yiaogit/SeismicGuard)",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Tamaño total declarado (puede no estar disponible)
            total = resp.headers.get("Content-Length")
            total_int = int(total) if total and total.isdigit() else 0

            # Volcar a disco con barra de progreso simple en stderr
            written = 0
            chunk = 65536
            with open(dest, "wb") as f:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    written += len(buf)
                    if total_int:
                        pct = 100 * written / total_int
                        sys.stderr.write(
                            f"\r    descargando {_human_size(written)}"
                            f" / {_human_size(total_int)} ({pct:5.1f}%)"
                        )
                    else:
                        sys.stderr.write(
                            f"\r    descargando {_human_size(written)}"
                        )
                    sys.stderr.flush()
            sys.stderr.write("\n")
            return written
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        sys.stderr.write(f"\n    ✗ {url}: {exc}\n")
        return None


def _validate(dest: Path, kind: str) -> bool:
    """Validación del archivo descargado. Devuelve True si OK."""

    if not dest.is_file():
        return False
    if kind == "jpg":
        # v12.3: acepta JPG (FF D8 FF) o PNG (89 50 4E 47) — algunos
        # mirrors de night-lights son PNG aunque el archivo destino
        # se llame .jpg (ECharts carga por contenido, no por extensión).
        with open(dest, "rb") as f:
            head = f.read(4)
        return head[:3] == b"\xff\xd8\xff" or head == b"\x89PNG"
    if kind == "geojson":
        try:
            with open(dest, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if not isinstance(obj, dict):
                return False
            if obj.get("type") != "FeatureCollection":
                return False
            if not isinstance(obj.get("features"), list):
                return False
            return len(obj["features"]) > 0
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return False
    return True


def _within_size_bounds(dest: Path, min_size: int, max_size: int) -> bool:
    if not dest.is_file():
        return False
    sz = dest.stat().st_size
    return min_size <= sz <= max_size


# ============================================================
# Lógica principal
# ============================================================
def fetch_asset(key: str, *, force: bool = False) -> bool:
    """Descarga un asset. True si terminó con archivo válido."""

    spec = ASSETS[key]
    dest = LIB_DIR / spec["filename"]
    print(f"\n▸ {key} → {dest.relative_to(PROJECT_ROOT)}")

    if dest.exists() and not force:
        if _within_size_bounds(dest, spec["min_size"], spec["max_size"]) \
                and _validate(dest, spec["validator"]):
            print(f"  ✓ ya existe y es válido "
                  f"({_human_size(dest.stat().st_size)})  — saltando")
            return True
        else:
            print("  ! existe pero está dañado/incompleto — re-descargando")
            dest.unlink(missing_ok=True)

    # Intentar mirrors en orden
    tmp = dest.with_suffix(dest.suffix + ".part")
    for i, url in enumerate(spec["mirrors"], 1):
        print(f"  [{i}/{len(spec['mirrors'])}] {url}")
        written = _download(url, tmp)
        if written is None:
            continue

        # Tamaño correcto?
        if not (spec["min_size"] <= written <= spec["max_size"]):
            print(f"    ✗ tamaño fuera de rango ({_human_size(written)})")
            tmp.unlink(missing_ok=True)
            continue

        # Contenido válido?
        if not _validate(tmp, spec["validator"]):
            print(f"    ✗ validación fallida (no parece un "
                  f"{spec['validator']} legítimo)")
            tmp.unlink(missing_ok=True)
            continue

        # ¡Listo! Mover al destino final
        shutil.move(tmp, dest)
        print(f"  ✓ guardado en {dest.relative_to(PROJECT_ROOT)} "
              f"({_human_size(written)})")
        return True

    print(f"  ✗ TODOS los mirrors fallaron para {key}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Descarga los assets opcionales del globo "
                    "(Blue Marble + fronteras GeoJSON).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-descargar aunque el archivo ya exista y sea válido",
    )
    parser.add_argument(
        "--only", choices=["day", "night", "borders"], default=None,
        help="Descargar solo un asset (por defecto: todos)",
    )
    args = parser.parse_args()

    LIB_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {LIB_DIR}")

    keys = [args.only] if args.only else list(ASSETS.keys())
    results = {k: fetch_asset(k, force=args.force) for k in keys}

    print("\n" + "═" * 50)
    n_ok = sum(1 for v in results.values() if v)
    print(f"Resultado: {n_ok}/{len(results)} asset(s) listos")
    for k, ok in results.items():
        mark = "✓" if ok else "✗"
        print(f"  {mark} {k}  ({ASSETS[k]['filename']})")
    print("═" * 50)

    if n_ok < len(results):
        print("\nAlgunos descargas fallaron. La app sigue funcional con "
              "los fallbacks de cada modo. Detalles en la salida de arriba.")
        return 1
    print("\nReinicia la app y disfruta de Blue Marble + fronteras Pro!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
