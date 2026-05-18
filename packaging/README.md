# Packaging · ShakeVision

Esta carpeta contiene todo lo necesario para producir los binarios
distribuibles de ShakeVision en los tres sistemas soportados.

| Archivo                       | Función                                                       |
|-------------------------------|---------------------------------------------------------------|
| `shakevision.spec`            | Configuración compartida de PyInstaller (onedir + datos web). |
| `build.py`                    | Driver Python multiplataforma — único punto de entrada.       |
| `macos/icon.icns` *(opcional)* | Icono del bundle `.app` y del `.dmg`.                         |
| `windows/icon.ico` *(opcional)* | Icono del `.exe`.                                              |
| `linux/icon.png` *(opcional)*  | Icono del AppImage (PNG 256×256).                              |

> Si los iconos no existen el build sigue funcionando pero el binario
> usará el icono genérico de PySide6 / Qt.

---

## Build local

Requisitos comunes:

* Python 3.10+ con `pip install -e ".[dev]"` ya ejecutado.
* Que `scripts/install_libs.sh` se haya corrido al menos una vez
  (`build.py` lo invoca automáticamente si las carpetas `lib/` están vacías).

### Windows · genera un `.zip`

```powershell
python packaging\build.py
```

Salida → `dist\ShakeVision-0.1.1-windows-x64.zip` (~250 MB).

### macOS · genera un `.dmg`

```bash
# Opcional: brew install create-dmg   (si no, se usa hdiutil)
python packaging/build.py
```

Salida → `dist/ShakeVision-0.1.1-macos-{x64|arm64}.dmg`.
El bundle interno es un `.app` notarizable; sin firma sale como
"app de desarrollador no identificado" hasta que el usuario haga
right-click → Abrir la primera vez.

### Linux · genera un `.AppImage`

```bash
# Una vez:
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool

python packaging/build.py
```

Salida → `dist/ShakeVision-0.1.1-linux-x64.AppImage` autoejecutable.

---

## Release automático con GitHub Actions

El workflow `.github/workflows/release.yml` se dispara al hacer push
de un tag `vX.Y.Z`:

```bash
# 1. Asegurarse de tener la versión correcta en
#      shakevision/__init__.py        →  __version__ = "0.1.1"
#      pyproject.toml                  →  version = "0.1.1"
#      packaging/shakevision.spec      →  version = "0.1.1"  (BUNDLE)
#    y una sección [0.1.1] en CHANGELOG.md
#
# 2. Hacer el tag y empujarlo
git tag -a v0.1.1 -m "ShakeVision v0.1.1 — binarios pre-empaquetados"
git push origin v0.1.1
```

GitHub Actions lanza tres jobs en paralelo
(`windows-latest`, `macos-13` Intel + `macos-14` Apple Silicon,
`ubuntu-22.04`), cada uno ejecuta `python packaging/build.py`, sube
sus artefactos y un cuarto job (`publish`) los reúne en una Release
nueva con el cuerpo extraído de `CHANGELOG.md` y una tabla de
SHA-256 checksums.

### Pre-releases

Para builds de prueba taggea con sufijo `-rc1`, `-beta`, `-alpha`,
`-dev` o `-pre`:

```bash
git tag -a v0.2.0-rc1 -m "v0.2.0 release candidate 1"
git push origin v0.2.0-rc1
```

El job `publish` detecta el sufijo y marca la Release como
`prerelease: true` automáticamente.

### Lanzar manualmente sin tag

Desde GitHub → Actions → **Release** → Run workflow (opcionalmente con
un nombre de tag). Solo se construirán los artefactos; no se publicará
una Release porque la condición `if: startsWith(github.ref, 'refs/tags/')`
solo se cumple con un tag real.

---

## Tamaños orientativos

| Plataforma | Artefacto         | Tamaño aprox. |
|------------|-------------------|---------------|
| Windows    | `.zip`            | 230–260 MB    |
| macOS      | `.dmg`            | 200–230 MB    |
| Linux      | `.AppImage`       | 240–270 MB    |

La mayor parte es PySide6 + QtWebEngine (Chromium embebido).
