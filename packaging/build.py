#!/usr/bin/env python3
"""
ShakeVision · Driver de empaquetado multiplataforma.

Uso
---
    # En cualquiera de los 3 OS:
    python packaging/build.py

    # Solo construir, sin empaquetar al instalador final:
    python packaging/build.py --no-installer

Pipeline
--------
1. Verifica que PyInstaller esté instalado.
2. (Opcional) Ejecuta scripts/install_libs.sh para que las páginas
   web traigan ECharts y la textura terrestre embebidos.
3. Limpia ``build/`` y ``dist/`` previas.
4. Llama a PyInstaller con ``packaging/shakevision.spec`` → produce
   ``dist/ShakeVision/`` (o ``dist/ShakeVision.app/`` en macOS).
5. Post-procesado dependiente del SO:
       Windows → comprime carpeta a ``.zip`` y produce ``ShakeVision-0.1.1-windows-x64.zip``
       macOS   → crea un ``.dmg`` con ``create-dmg`` (o hdiutil fallback)
       Linux   → empaqueta en ``.AppImage`` con ``linuxdeploy`` + ``appimagetool``
6. Calcula SHA-256 de cada artefacto final en ``dist/``.

Los artefactos finales viven todos en ``dist/`` con nombres
``ShakeVision-<version>-<os>-<arch>.<ext>`` listos para subir a una
Release de GitHub.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

# ============================================================
# Compatibilidad de consola en Windows CI
# ------------------------------------------------------------
# El runner de GitHub Actions abre `stdout` en cp1252 / cp65001
# en función de cómo se invoque PowerShell. Caracteres como
# "▶", "✓", "✗", "⚠" hacen estallar `print()` con
# `UnicodeEncodeError`. Reconfiguramos a UTF-8 (Python 3.7+)
# y, si fallara, caemos a un set ASCII puro.
# ============================================================
def _stdout_supports_utf8() -> bool:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        return True
    except Exception:  # noqa: BLE001
        return False


_UTF8 = _stdout_supports_utf8()
_SYM_STEP = "▶" if _UTF8 else ">"
_SYM_OK   = "✓" if _UTF8 else "+"
_SYM_WARN = "⚠" if _UTF8 else "!"
_SYM_FAIL = "✗" if _UTF8 else "x"

# ============================================================
# Rutas y metadatos
# ============================================================
ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "shakevision.spec"
DIST = ROOT / "dist"
BUILD = ROOT / "build"

APP_NAME = "ShakeVision"


def _read_version() -> str:
    """Lee la versión desde ``shakevision/__init__.py`` sin importar el paquete."""
    init = ROOT / "shakevision" / "__init__.py"
    for line in init.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("__version__ no encontrado en shakevision/__init__.py")


VERSION = _read_version()


def _arch_label() -> str:
    """Etiqueta de arquitectura para el nombre del artefacto."""
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return m or "unknown"


# ============================================================
# Helpers de logging
# ============================================================
def _step(msg: str) -> None:
    print(f"\n\033[1;36m{_SYM_STEP} {msg}\033[0m", flush=True)


def _ok(msg: str) -> None:
    print(f"\033[1;32m{_SYM_OK}\033[0m {msg}", flush=True)


def _warn(msg: str) -> None:
    print(f"\033[1;33m{_SYM_WARN}\033[0m {msg}", flush=True)


def _die(msg: str, code: int = 1) -> None:
    print(f"\033[1;31m{_SYM_FAIL}\033[0m {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def _run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    """Wrapper de subprocess.run con traza visible y exit on failure."""
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    if result.returncode != 0:
        _die(f"comando falló (rc={result.returncode}): {' '.join(cmd)}")


# ============================================================
# Paso 1: prerequisitos
# ============================================================
def ensure_pyinstaller() -> None:
    _step("Comprobando PyInstaller")
    try:
        import PyInstaller  # noqa: F401
        _ok(f"PyInstaller {PyInstaller.__version__} detectado")
    except ImportError:
        _warn("PyInstaller no instalado — instalando…")
        _run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.5"])


def ensure_web_libs() -> None:
    """Descarga ECharts + textura Tierra si no están aún."""
    _step("Asegurando bibliotecas web (ECharts + textura)")
    libs_dir = ROOT / "shakevision" / "web" / "globe" / "lib"
    if libs_dir.is_dir() and any(libs_dir.glob("echarts*.js")):
        _ok("Bibliotecas web ya presentes")
        return
    script = ROOT / "scripts" / "install_libs.sh"
    if not script.is_file():
        _warn("scripts/install_libs.sh no encontrado; el binario "
              "dependerá del CDN en runtime")
        return
    # bash funciona en Linux/macOS; en Windows asumimos git-bash o WSL
    if sys.platform == "win32" and not shutil.which("bash"):
        _warn("bash no disponible — saltando install_libs.sh (Windows). "
              "Las páginas usarán CDN como fallback.")
        return
    _run(["bash", str(script)])


# ============================================================
# Paso 2: limpiar artefactos previos
# ============================================================
def clean_previous() -> None:
    _step("Limpiando carpetas dist/ y build/ previas")
    for d in (DIST, BUILD):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            _ok(f"borrado: {d.relative_to(ROOT)}")


# ============================================================
# Paso 3: PyInstaller
# ============================================================
def run_pyinstaller() -> None:
    _step("Ejecutando PyInstaller")
    _run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--log-level=INFO",
        str(SPEC),
    ], cwd=ROOT)
    _ok("Bundle PyInstaller generado en dist/")


# ============================================================
# Paso 4: post-procesado por plataforma
# ============================================================
def build_windows_zip() -> Path:
    """Comprime dist/ShakeVision/ a ShakeVision-VERSION-windows-x64.zip"""
    _step("Empaquetando ZIP de Windows")
    src = DIST / APP_NAME
    if not src.is_dir():
        _die(f"No se encontró carpeta {src}")
    artifact = DIST / f"{APP_NAME}-{VERSION}-windows-{_arch_label()}.zip"
    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in src.rglob("*"):
            rel = path.relative_to(src.parent)
            zf.write(path, rel)
    _ok(f"Creado {artifact.name} ({artifact.stat().st_size // (1024 * 1024)} MB)")
    return artifact


def build_macos_dmg() -> Path:
    """Crea ShakeVision-VERSION-macos-ARCH.dmg con create-dmg o hdiutil."""
    _step("Empaquetando DMG de macOS")
    app_bundle = DIST / f"{APP_NAME}.app"
    if not app_bundle.is_dir():
        _die(f"No se encontró {app_bundle} — ¿pyinstaller en macOS?")
    artifact = DIST / f"{APP_NAME}-{VERSION}-macos-{_arch_label()}.dmg"
    if artifact.exists():
        artifact.unlink()

    # Preferir create-dmg (más bonito; ventana con icono y enlace a /Applications)
    if shutil.which("create-dmg"):
        _run([
            "create-dmg",
            "--volname", f"{APP_NAME} {VERSION}",
            "--window-pos", "200", "120",
            "--window-size", "640", "400",
            "--icon-size", "100",
            "--icon", f"{APP_NAME}.app", "160", "200",
            "--hide-extension", f"{APP_NAME}.app",
            "--app-drop-link", "480", "200",
            "--no-internet-enable",
            str(artifact),
            str(app_bundle),
        ])
    else:
        _warn("create-dmg no instalado — fallback a hdiutil (DMG simple)")
        # Carpeta temporal de "staging" con .app + symlink a /Applications
        staging = DIST / "_dmg_staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        shutil.copytree(app_bundle, staging / f"{APP_NAME}.app", symlinks=True)
        (staging / "Applications").symlink_to("/Applications")
        _run([
            "hdiutil", "create",
            "-volname", f"{APP_NAME} {VERSION}",
            "-srcfolder", str(staging),
            "-ov", "-format", "UDZO",
            str(artifact),
        ])
        shutil.rmtree(staging, ignore_errors=True)

    _ok(f"Creado {artifact.name} ({artifact.stat().st_size // (1024 * 1024)} MB)")
    return artifact


def build_linux_appimage() -> Path:
    """Empaqueta dist/ShakeVision/ en un .AppImage usando appimagetool."""
    _step("Empaquetando AppImage de Linux")
    src = DIST / APP_NAME
    if not src.is_dir():
        _die(f"No se encontró {src}")
    appdir = DIST / f"{APP_NAME}.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "bin").mkdir(parents=True)
    (appdir / "usr" / "share" / "applications").mkdir(parents=True)
    (appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True)

    # 1) Copiar el árbol completo del bundle PyInstaller a usr/bin
    shutil.copytree(src, appdir / "usr" / "bin" / APP_NAME, symlinks=True)

    # 2) AppRun (entrypoint) — script bash que lanza el binario real
    apprun = appdir / "AppRun"
    apprun.write_text(
        "#!/bin/bash\n"
        'HERE="$(dirname "$(readlink -f "${0}")")"\n'
        'export LD_LIBRARY_PATH="$HERE/usr/bin/ShakeVision:${LD_LIBRARY_PATH}"\n'
        'exec "$HERE/usr/bin/ShakeVision/ShakeVision" "$@"\n',
        encoding="utf-8",
    )
    apprun.chmod(0o755)

    # 3) .desktop
    desktop = appdir / f"{APP_NAME.lower()}.desktop"
    desktop.write_text(
        "[Desktop Entry]\n"
        f"Name={APP_NAME}\n"
        f"Exec={APP_NAME}\n"
        f"Icon={APP_NAME.lower()}\n"
        "Type=Application\n"
        "Categories=Science;Education;\n"
        f"Comment=Real-time seismic monitoring with USGS + Raspberry Shake data\n",
        encoding="utf-8",
    )
    # appimagetool exige también el .desktop en usr/share/applications
    shutil.copy(desktop, appdir / "usr" / "share" / "applications" / desktop.name)

    # 4) Icono (256×256 PNG en raíz del AppDir + hicolor)
    icon_src = ROOT / "packaging" / "linux" / "icon.png"
    icon_dst = appdir / f"{APP_NAME.lower()}.png"
    if icon_src.is_file():
        shutil.copy(icon_src, icon_dst)
        shutil.copy(icon_src,
                    appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
                    / f"{APP_NAME.lower()}.png")
    else:
        # Placeholder mínimo: PNG 1×1 transparente para satisfacer a appimagetool
        _warn("packaging/linux/icon.png no existe — usando placeholder 1×1")
        icon_dst.write_bytes(_one_pixel_png())

    # 5) Buscar appimagetool
    appimagetool = shutil.which("appimagetool") or shutil.which("appimagetool-x86_64.AppImage")
    if not appimagetool:
        _die(
            "appimagetool no encontrado. Instálalo con:\n"
            "  wget https://github.com/AppImage/AppImageKit/releases/download/continuous/"
            "appimagetool-x86_64.AppImage\n"
            "  chmod +x appimagetool-x86_64.AppImage && sudo mv ./appimagetool-x86_64.AppImage "
            "/usr/local/bin/appimagetool"
        )

    artifact = DIST / f"{APP_NAME}-{VERSION}-linux-{_arch_label()}.AppImage"
    if artifact.exists():
        artifact.unlink()

    env = os.environ.copy()
    env.setdefault("ARCH", "x86_64" if _arch_label() == "x64" else _arch_label())
    cmd = [appimagetool, str(appdir), str(artifact)]
    print(f"  $ ARCH={env['ARCH']} {' '.join(cmd)}", flush=True)
    rc = subprocess.run(cmd, env=env).returncode
    if rc != 0:
        _die(f"appimagetool falló (rc={rc})")

    shutil.rmtree(appdir, ignore_errors=True)
    _ok(f"Creado {artifact.name} ({artifact.stat().st_size // (1024 * 1024)} MB)")
    return artifact


def _one_pixel_png() -> bytes:
    """PNG 1×1 transparente (usado solo si falta el icono real)."""
    return bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
    )


# ============================================================
# Paso 5: hashes
# ============================================================
def write_checksums(artifacts: list[Path]) -> Path:
    _step("Generando SHA-256 checksums")
    out = DIST / f"{APP_NAME}-{VERSION}-checksums.txt"
    lines = []
    for a in artifacts:
        h = hashlib.sha256(a.read_bytes()).hexdigest()
        lines.append(f"{h}  {a.name}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        _ok(line)
    return out


# ============================================================
# Main
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="ShakeVision · constructor multiplataforma")
    parser.add_argument("--no-installer", action="store_true",
                        help="solo correr PyInstaller, no producir .exe/.dmg/.AppImage")
    parser.add_argument("--no-libs", action="store_true",
                        help="no descargar bibliotecas web (asumirlas ya presentes)")
    args = parser.parse_args()

    print(f"\033[1;35m=== ShakeVision build v{VERSION} ({sys.platform} / {_arch_label()}) ===\033[0m")

    ensure_pyinstaller()
    if not args.no_libs:
        ensure_web_libs()
    clean_previous()
    run_pyinstaller()

    if args.no_installer:
        _ok("Compilación completada (--no-installer; no se generan .dmg/.AppImage/.zip)")
        return 0

    if sys.platform == "win32":
        artifacts = [build_windows_zip()]
    elif sys.platform == "darwin":
        artifacts = [build_macos_dmg()]
    elif sys.platform.startswith("linux"):
        artifacts = [build_linux_appimage()]
    else:
        _die(f"Plataforma no soportada: {sys.platform}")
        return 1

    write_checksums(artifacts)
    _step("Hecho")
    for a in artifacts:
        print(f"  → {a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
