# ============================================================
# ShakeVision · PyInstaller spec compartido entre Windows / macOS / Linux
# ------------------------------------------------------------
# Estrategia: **onedir** (no onefile). Razones:
#   * PySide6 + QtWebEngine son enormes (~250 MB). onefile descomprime
#     todo a un tmp en cada arranque → ~3 s de arranque y antivirus
#     en Windows lo señalan como sospechoso.
#   * onedir es una carpeta `dist/ShakeVision/` con el .exe / binario y
#     todas las DLLs al lado, instantánea de arrancar y mucho más
#     fácil de empaquetar luego en .dmg / .AppImage / instalador.
#
# Llamada desde `packaging/build.py` (no se invoca a mano):
#   pyinstaller --noconfirm --clean packaging/shakevision.spec
#
# Salida: `dist/ShakeVision/` (carpeta) y, dentro,
#   * Windows  → `ShakeVision.exe`
#   * macOS    → `ShakeVision.app/Contents/MacOS/ShakeVision`
#   * Linux    → `ShakeVision` (ELF)
# ============================================================

# noqa: F821 (PyInstaller inyecta Analysis/PYZ/EXE/BUNDLE en este scope)

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files  # noqa: F401

# El spec se ejecuta desde la raíz del repo cuando se llama vía
# `pyinstaller packaging/shakevision.spec`. Calculamos rutas absolutas
# para que no dependa del cwd.
ROOT = Path(SPECPATH).resolve().parent          # noqa: F821
APP_PKG = ROOT / "shakevision"

# ------------------------------------------------------------
# Datos no-código a empaquetar
# ------------------------------------------------------------
# PyInstaller necesita (src, dst_dir_relativo_al_bundle).
# Nota: PyInstaller resuelve estos paths copiando recursivamente
# si src es una carpeta. Excluimos los __pycache__.
datas = [
    # Fuentes empaquetadas (Inter + JetBrains Mono)
    (str(APP_PKG / "assets" / "fonts"), "shakevision/assets/fonts"),
    # Iconos (puede estar vacío en algunas builds; se ignora si no existe)
    (str(APP_PKG / "assets"), "shakevision/assets"),
    # Diccionarios i18n
    (str(APP_PKG / "i18n" / "locales"), "shakevision/i18n/locales"),
    # Páginas web: Globe, Dashboard, Report (incluye sus lib/ con ECharts)
    (str(APP_PKG / "web" / "globe"), "shakevision/web/globe"),
    (str(APP_PKG / "web" / "dashboard"), "shakevision/web/dashboard"),
    (str(APP_PKG / "web" / "report"), "shakevision/web/report"),
]

# v0.7.6 fix — incluir el CA bundle de certifi para que el .dmg de
# macOS pueda validar certificados HTTPS. Sin esto, el bundle no
# trae ningún CA chain y TODO urlopen() a https:// falla con
# CERTIFICATE_VERIFY_FAILED (problema específico de macOS, ver
# shakevision/__main__.py para el contexto completo).
datas += collect_data_files("certifi")

# ------------------------------------------------------------
# Hidden imports — módulos que PyInstaller no descubre por análisis
# estático porque se importan dinámicamente (importlib, plugins, etc.).
# ------------------------------------------------------------
hiddenimports = [
    # v0.7.6 — certifi explícito (lo importa __main__.py al arrancar
    # para fijar el CA bundle del SSL context en macOS).
    "certifi",
    # ObsPy carga plugins por entry_points en runtime
    "obspy.io.mseed",
    "obspy.io.xseed",
    "obspy.io.stationxml",
    "obspy.clients.fdsn",
    "obspy.clients.seedlink",
    # tzdata es runtime-only en Windows; lo incluimos siempre por
    # seguridad — coste casi nulo (~1 MB).
    "tzdata",
    # zoneinfo a veces necesita pisarse explícitamente
    "zoneinfo",
    # tzlocal y sus dependencias internas — sin esto la detección
    # de zona horaria de Windows falla silenciosamente en el bundle.
    "tzlocal",
    "tzlocal.utils",
    "tzlocal.windows_tz",
    # PySide6 sub-módulos que QtWebEngine activa por su cuenta
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",
    "PySide6.QtPositioning",
]

# ------------------------------------------------------------
# Módulos que NO queremos arrastrar (recorta ~150 MB en Linux)
# ------------------------------------------------------------
excludes = [
    "tkinter",
    "matplotlib.tests",
    "numpy.tests",
    "scipy.tests",
    "PIL.tests",
    "pytest",
    "_pytest",
    "ruff",
    "pyinstaller",
]

# ------------------------------------------------------------
# Análisis (recorre imports desde __main__)
# ------------------------------------------------------------
a = Analysis(
    [str(APP_PKG / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)                               # noqa: F821

# ------------------------------------------------------------
# Icono por plataforma
# ------------------------------------------------------------
ICON_PATH = None
if sys.platform == "darwin":
    candidate = ROOT / "packaging" / "macos" / "icon.icns"
    if candidate.is_file():
        ICON_PATH = str(candidate)
elif sys.platform == "win32":
    candidate = ROOT / "packaging" / "windows" / "icon.ico"
    if candidate.is_file():
        ICON_PATH = str(candidate)
else:
    candidate = ROOT / "packaging" / "linux" / "icon.png"
    if candidate.is_file():
        ICON_PATH = str(candidate)

# ------------------------------------------------------------
# Recurso VS_VERSIONINFO para Windows (reduce el warning de
# SmartScreen porque el PE deja de ser anónimo).
# ------------------------------------------------------------
WIN_VERSION_INFO = None
if sys.platform == "win32":
    candidate = ROOT / "packaging" / "windows" / "version_info.txt"
    if candidate.is_file():
        WIN_VERSION_INFO = str(candidate)

# ------------------------------------------------------------
# EXE (entrada de la carpeta onedir)
# ------------------------------------------------------------
exe = EXE(                                       # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShakeVision",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # UPX rompe firmas en macOS y dispara AV en Windows
    console=False,            # GUI, sin consola negra detrás
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
    version=WIN_VERSION_INFO,  # solo se aplica en Windows
)

# ------------------------------------------------------------
# COLLECT (junta exe + binarios + datas en dist/ShakeVision/)
# ------------------------------------------------------------
coll = COLLECT(                                  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ShakeVision",
)

# ------------------------------------------------------------
# macOS: además del COLLECT envolvemos en .app bundle
# ------------------------------------------------------------
if sys.platform == "darwin":
    app = BUNDLE(                                # noqa: F821
        coll,
        name="ShakeVision.app",
        icon=ICON_PATH,
        bundle_identifier="org.shakevision.app",
        version="0.7.6.1",
        info_plist={
            "CFBundleName": "ShakeVision",
            "CFBundleDisplayName": "ShakeVision",
            "CFBundleShortVersionString": "0.7.6.1",
            "CFBundleVersion": "0.7.6.1",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "© 2025 ShakeVision contributors — MIT License",
            "NSPrincipalClass": "NSApplication",
            # QtWebEngine necesita acceso a red para tiles / CDN fallback
            "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
        },
    )
