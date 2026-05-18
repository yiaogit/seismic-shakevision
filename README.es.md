<div align="center">

# 🌐 SeismicGuard

[简体中文](README.md) · [English](README.en.md) · **Español** · [Français](README.fr.md)

> Antes conocido como **ShakeVision OpenData Monitor**. La v0.7.0 incorpora
> el rebrand a SeismicGuard, un rediseño de tema al estilo macOS Sonoma,
> i18n completo en 4 idiomas, asistente de incorporación, página de perfil
> con línea de tiempo de actividad, detección de ubicación por IP y muchas
> mejoras de usabilidad. Las versiones binarias antiguas (v0.1.x) siguen
> en la página de Releases bajo el nombre `ShakeVision-*`.

**Estación de monitoreo sísmico de escritorio, código abierto**
*Cross-platform desktop seismic monitoring workbench*

Consume datos en tiempo real de la red ciudadana global de sismología
(Raspberry Shake) más redes profesionales (USGS / IRIS), y unifica
globo 3D · panel de datos · análisis de formas de onda / espectrograma /
disparo en una sola aplicación de escritorio.

[![CI](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml)
[![Release](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platform-windows%20%7C%20macos%20arm64%20%7C%20linux-lightgrey)](https://github.com/yiaogit/seismic-shakevision/releases/latest)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20ES%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20FR-brightgreen)](shakevision/i18n/locales/)

[**Descargar instaladores**](#-descargar) · [**Ejecutar desde el código**](#-ejecutar-desde-el-código) · [**Funciones**](#-funciones) · [**Arquitectura**](#-arquitectura) · [**Publicación**](#-publicación)

</div>

---

## ✨ Funciones

| Módulo                     | Descripción                                                                                                                       |
|----------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| 🌍 **Globo 3D**            | Renderizado en tiempo real con ECharts-GL, 600+ estaciones ciudadanas Raspberry Shake + 400+ estaciones de la red dorsal USGS / IRIS, sismos coloreados por magnitud, click-zoom + añadir al banco Pro |
| 📊 **Panel de datos**      | 7 gráficas ECharts enlazadas: top países, histogramas magnitud / profundidad, línea temporal 24 h (burbujas de densidad), radar PAGER (filtro por región), buckets autoadaptativos, dispersión profundidad × magnitud |
| 🔬 **Banco Pro**           | Ventana flotante: forma de onda 3 canales + espectrograma + helicórder 24 h + movimiento de partícula N-E + grabación STA/LTA + tarjeta de intensidad MMI |
| 🔊 **Sonificación**        | Reproduce los últimos 60 segundos del movimiento del suelo como audio audible a velocidad 1× – 60×                                |
| 🌐 **i18n**                | Pila completa de 4 idiomas (EN / ES / 简中 / FR) con cambio instantáneo, incluidas vistas web, internos de gráficas, tooltips y reportes HTML |
| 🕒 **Conciencia de zona**  | Auto-detección de zona horaria del sistema + override manual; todas las marcas de tiempo se renderizan en la zona del usuario     |
| 📄 **Reportes**            | Exportación a un único archivo HTML (con línea de tiempo SVG) + exportación PDF vía `QWebEngine.printToPdf`                       |
| ⚡ **SeedLink en vivo**    | Conexión directa a IRIS `rtserve.iris.washington.edu:18000`, enrutamiento automático IU/US/II/IC, estado de conexión por fases, cancelable en cualquier momento |
| 👤 **Perfil**              | OAuth GitHub (Device Flow), estadísticas de uso, **línea de tiempo de actividad reciente** (últimos 50 eventos con timestamps relativos, almacenados localmente) |
| 📍 **Ubicación**           | Geolocalización por IP (un click, nunca en segundo plano) que sugiere estaciones cercanas y actualiza la zona horaria             |

---

## 📦 Descargar

> **Recomendado para usuarios finales.** Los binarios se compilan en
> GitHub Actions en cada tag; las sumas SHA-256 también se suben
> automáticamente.

Última versión → **[Latest Release](https://github.com/yiaogit/seismic-shakevision/releases/latest)**

| Plataforma                            | Archivo                                        | Cómo instalar                                                |
|---------------------------------------|------------------------------------------------|--------------------------------------------------------------|
| 🪟 **Windows 10 / 11 x64**            | `ShakeVision-X.Y.Z-windows-x64.zip`            | Descomprimir → doble click `ShakeVision.exe` (SmartScreen al primer arranque, ver abajo) |
| 🍎 **macOS Apple Silicon (M1–M5)**    | `ShakeVision-X.Y.Z-macos-arm64.dmg`            | Abrir DMG → arrastrar a `/Applications` → primera vez click derecho → Abrir              |
| 🐧 **Linux x64**                      | `ShakeVision-X.Y.Z-linux-x64.AppImage`         | `chmod +x ShakeVision-*.AppImage` → doble click                                          |

#### 🛡 Aviso del primer arranque (Windows SmartScreen / macOS Gatekeeper)

SeismicGuard **aún no está firmado** (certificado EV ≈ $300/año —
previsto para v1.0). El sistema operativo te avisará al primer
arranque:

<details>
<summary><b>🪟 Windows — "Windows protected your PC"</b></summary>

Tras descomprimir y hacer doble click en `ShakeVision.exe`, aparece un
diálogo azul:

```
Windows protected your PC
Microsoft Defender SmartScreen prevented an unrecognized app from starting.
```

Qué hacer:

1. Pulsa **"More info"** (enlace pequeño, abajo a la izquierda)
2. Aparece un botón **"Run anyway"** — púlsalo
3. Los siguientes arranques no preguntan más

> Solo una vez. Una vez que SmartScreen confía en tu copia local, no
> vuelve a molestar. Si prefieres no pulsar "Run anyway", ejecuta
> desde el código fuente (ver [Ejecutar desde el código](#-ejecutar-desde-el-código)).

</details>

<details>
<summary><b>🍎 macOS — "ShakeVision can't be opened because Apple cannot check it for malicious software"</b></summary>

Tras arrastrar el `.app` a `/Applications`, el primer arranque queda
bloqueado por Gatekeeper:

1. **No** hagas doble click; haz **click derecho (o Ctrl-click)** en
   `ShakeVision.app`
2. Elige **"Open"** del menú
3. Confirma **"Open"** otra vez en el diálogo
4. A partir de ahí, doble click funciona normalmente

</details>

> 🍎 **Usuarios de Mac Intel**: ya no se publican binarios Intel
> (Apple Silicon es mainstream desde hace 4+ años). Compila localmente
> — ver [Ejecutar desde el código](#-ejecutar-desde-el-código).

Verificación opcional de checksums:

```bash
# Tras descargar SHA256SUMS.txt de la página de release
sha256sum -c SHA256SUMS.txt        # Linux
shasum -a 256 -c SHA256SUMS.txt    # macOS
certutil -hashfile <file> SHA256   # Windows PowerShell
```

---

## 💻 Ejecutar desde el código

Para desarrolladores, usuarios de Mac Intel, y quien quiera contribuir.

### Requisitos previos

| SO         | Necesario                                                                                                |
|------------|----------------------------------------------------------------------------------------------------------|
| Todos      | Python ≥ 3.10 (recomendado 3.11 / 3.12) + Git                                                            |
| **Linux**  | `libegl1 libxkbcommon0 libxcb-cursor0 libxcb-icccm4 libgl1 libdbus-1-3` (Ubuntu/Debian `apt install`)    |
| **macOS**  | Xcode Command Line Tools (`xcode-select --install`)                                                      |
| **Windows**| Visual C++ Redistributable (normalmente incluido en el PySide6 que instala pip)                          |

### Arranque en un comando

```bash
# 1) Clonar + entrar
git clone https://github.com/yiaogit/seismic-shakevision.git
cd seismic-shakevision

# 2) Entorno virtual + instalación (con extras de desarrollo)
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"

# 3) Descarga única de assets (~10 MB: ECharts + fuentes + texturas de globo)
bash scripts/install_libs.sh
bash scripts/install_fonts.sh

# 4) Lanzar
python -m shakevision
```

> 🪟 En Windows, ejecuta el paso 3 con Git Bash / WSL, o descarga
> manualmente las URLs listadas en el script.
> 🍎 Usuarios macOS: `pip install -e ".[macos]"` añade pyobjc para la
> barra de título translúcida.

---

## 🚀 Primeros pasos

```
Lanzar → entra por defecto a la vista 🌍 Globo
  ├── Click en cualquier punto USGS → diálogo "¿Añadir a Pro?" → ✅ → aparece en el panel Pro
  ├── Cambiar a 📊 Datos → 7 gráficas enlazadas + filtros de periodo / región
  └── Arriba derecha 🔬 Pro → abre la ventana profesional independiente
                              ├── Selecciona la estación USGS recién añadida
                              ├── Click Conectar → stream SeedLink en vivo
                              └── Mira forma de onda / espectrograma / helicórder / movimiento de partícula

Arriba derecha ⚙ Ajustes → cambia idioma + zona horaria, aplicado al instante, sin reiniciar
Arriba derecha 👤 Perfil → tarjeta de identidad + estadísticas + línea de tiempo de actividad
```

---

## 🏗 Arquitectura

### Flujo de datos

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ USGS GeoJSON │ ──► │   Worker     │ ──► │  data_models │ ──► │   Globo      │
│ IRIS FDSN    │     │ (async,      │     │ (Earthquake, │     │ Dashboard    │
│ ShakeNet     │     │  un hilo)    │     │  Station…)   │     │ (HTML + JS)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  SeedLink    │ ──► │  RingBuffer  │ ──► │  Processor   │ ──► │  Ventana Pro │
│ rtserve.iris │     │ (thread-safe)│     │ Butterworth, │     │  Waveform +  │
│  → ObsPy     │     │              │     │ STA/LTA, FFT │     │  Spec + Hel  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Pila técnica

| Capa             | Elección                                            | Razón                                              |
|------------------|-----------------------------------------------------|----------------------------------------------------|
| **UI**           | PySide6 ≥ 6.6                                       | LGPL, look nativo multiplataforma, QtWebEngine trae Chromium |
| **Web**          | QWebEngineView                                      | Embeber ECharts sin importar un navegador de terceros        |
| **Globo 3D**     | [ECharts-GL](https://github.com/ecomfe/echarts-gl)  | Una sola librería cubre 2D + 3D, bundle más ligero que Three.js |
| **Charts 2D**    | [Apache ECharts](https://echarts.apache.org/) 5.4   | 7 charts comparten el mismo motor                            |
| **DSP**          | NumPy + SciPy                                       | Estándar de la industria — filtros Butterworth + FFT         |
| **Sismología**   | [ObsPy](https://www.obspy.org/) ≥ 1.4               | Cliente SeedLink + lectura/escritura MiniSEED                |
| **Waveform**     | [pyqtgraph](https://www.pyqtgraph.org/) 0.13        | 60 FPS acelerado por GPU                                     |
| **Audio**        | QtMultimedia QAudioSink                             | Multiplataforma, cero dependencias extra                     |
| **Timezone**     | `zoneinfo` (+ `tzdata` pip en Windows)              | Stdlib; auto-detección de `/etc/localtime` en POSIX          |
| **i18n**         | Dict JSON propio + helper `t()`                     | Python y JS comparten un solo diccionario, sin paso de build |
| **Empaquetado**  | PyInstaller (onedir) + `create-dmg` + `appimagetool` | Consistente cross-platform; onedir arranca rápido            |
| **CI / Release** | GitHub Actions                                      | Matriz de 3 plataformas + publicación automática al hacer tag |

### Estructura del proyecto

```
seismic-shakevision/
├── shakevision/              # ── paquete principal ──
│   ├── __main__.py           # entrada (python -m shakevision)
│   ├── config.py             # registro de servidores SeedLink + estaciones por defecto
│   ├── sources/              # DataSource abstracto + Mock / SeedLink
│   ├── processing/           # RingBuffer / Filters / Detector / Spectrum / Recorder / Intensity / Sonifier
│   ├── services/             # clientes USGS / IRIS / ShakeNet + Worker + Report + Timezone + ActivityLog + Location + ClearCache
│   ├── ui/                   # ventana principal PySide6 + flotantes + widgets + Settings + Profile + Onboarding
│   ├── i18n/                 # LocaleService + 4 diccionarios alineados (each 435 keys)
│   ├── web/{globe,dashboard,report}/   # HTML/JS/CSS embebido
│   └── assets/{fonts,icons}/ # fuentes (descargadas por script, fuera del repo)
│
├── tests/                    # pytest unitarios + integración (40+ módulos)
├── packaging/                # ⭐ PyInstaller spec + build.py multiplataforma
├── scripts/                  # install_libs.sh / install_fonts.sh / download_globe_assets.py
├── .github/workflows/        # ci.yml (cada push) + release.yml (disparado por tag)
├── CHANGELOG.md
├── pyproject.toml
└── README.md                 # éste (más README.en.md / README.es.md / README.fr.md)
```

---

## 🛠 Desarrollo y testing

```bash
# Ejecutar la suite de tests
pytest -v

# Lint
ruff check shakevision tests

# Sanity check de compilación
python -m compileall -q shakevision tests
```

CI corre en cada push / PR: Ubuntu / macOS / Windows × Python 3.10 /
3.11 / 3.12 × (ruff + pytest). Linux usa `xvfb-run`; macOS / Windows
usan `QT_QPA_PLATFORM=offscreen`.

---

## 🌐 Traducciones i18n

Los diccionarios viven en `shakevision/i18n/locales/*.json` (~435
claves cada uno, 4 idiomas alineados al 100 %).

**Añadir un idioma**:

1. Copia `en.json` a un nuevo archivo, p. ej. `ja.json` / `de.json`
2. Traduce cada value (no cambies las keys)
3. Regístralo en `shakevision/i18n/service.py` dentro de
   `SUPPORTED_LANGUAGES` + `LANGUAGE_LABELS`
4. Abre PR

---

## 🚢 Publicación

> Solo mantenedores. Sigue este flujo en cada release.

### Preparación inicial (ya hecho — saltar)

- ✅ `packaging/shakevision.spec` — spec de PyInstaller
- ✅ `packaging/build.py` — driver multiplataforma
- ✅ `.github/workflows/release.yml` — build + publish automático

### Pasos de release (con v0.1.1 como ejemplo)

```bash
# 1) Bump consistente de los 3 números de versión
#    a. shakevision/__init__.py    →  __version__ = "0.1.1"
#    b. pyproject.toml              →  version = "0.1.1"
#    c. packaging/shakevision.spec  →  version = "0.1.1"  (BUNDLE)

# 2) Actualizar CHANGELOG.md: prepender un bloque ## [0.1.1] — YYYY-MM-DD
#    El workflow lo extrae automáticamente como notas del release.

# 3) Commit + push
git add -A
git commit -m "release: v0.1.1"
git push origin main

# 4) Tag + push tag → dispara el release workflow
git tag -a v0.1.1 -m "ShakeVision v0.1.1 — binary installers"
git push origin v0.1.1
```

Tras subir el tag, GitHub Actions ejecuta:

```
release.yml (tag v0.1.1)
  ├── build-windows  (windows-latest, Py 3.11)      → ShakeVision-0.1.1-windows-x64.zip
  ├── build-macos    (macos-14 / Apple Silicon)     → ShakeVision-0.1.1-macos-arm64.dmg
  ├── build-linux    (ubuntu-22.04)                 → ShakeVision-0.1.1-linux-x64.AppImage
  └── publish        (descarga los 3 artifacts)
       ├── extrae el bloque [0.1.1] de CHANGELOG.md como release notes
       ├── ensambla SHA256SUMS.txt
       └── crea el Release en GitHub con 3 binarios + checksums
```

Unos 15–25 minutos después, **v0.1.1** aparece en
https://github.com/yiaogit/seismic-shakevision/releases.

### Pre-releases (rc / beta)

Sufijos `-rc1` / `-beta` / `-alpha` / `-dev` / `-pre` marcan
automáticamente `prerelease: true`:

```bash
git tag -a v0.2.0-rc1 -m "v0.2.0 release candidate 1"
git push origin v0.2.0-rc1
```

### Recuperarse de una release rota

```bash
# Borra el tag remoto (también borra el Release en la UI de GitHub)
git push --delete origin v0.1.1
git tag -d v0.1.1
# Arregla código, re-tag, push
git tag -a v0.1.1 -m "..."
git push origin v0.1.1
```

Detalles completos del empaquetado (compilación local, particularidades
del macOS dual-arch, tamaños, etc.) en
[`packaging/README.md`](packaging/README.md).

---

## 🗺 Hoja de ruta

- [x] **v0.1.0** — release completo desde código (i18n + zona horaria + Pro + Ajustes)
- [x] **v0.1.1** — instaladores binarios (Windows `.zip` + macOS arm64 `.dmg` + Linux `.AppImage`)
- [x] **v0.2.0** — replay histórico: descarga MiniSEED desde IRIS FDSN dataselect con velocidad ajustable
- [x] **v0.3.0** — UI Raspberry Shake LAN personalizado ("➕ Add LAN Shake…" + pestaña "My Shakes")
- [x] **v0.7.0** — rebrand a SeismicGuard, theming macOS-Sonoma, asistente, perfil + actividad, geolocalización IP, fix de overflow en PDF
- [ ] **v0.8.0** — UX de sismo favorito en el globo (basada en botón, reemplaza el right-click pospuesto)
- [ ] **v1.0.0** — firma de código (Windows EV cert + macOS Developer ID + notarización); elimina por completo los avisos SmartScreen / Gatekeeper

---

## 📜 Fuentes de datos

- 🍓 [Raspberry Shake](https://raspberryshake.org/) — red de sismología ciudadana, datos abiertos CC-BY
- 🇺🇸 [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/) — feed GeoJSON de sismos
- 🌍 [IRIS DMC](https://ds.iris.edu/) — metadatos de redes profesionales + stream SeedLink (`rtserve.iris.washington.edu`)

> ⚠ **No existe un servidor SeedLink público de Raspberry Shake.** Solo
> puedes conectarte a tu propio dispositivo en LAN (`rs.local:18000`)
> o a una suscripción RTDC de pago. Ver el registro `SEEDLINK_SERVERS`
> en `shakevision/config.py`.

---

## 🤝 Contribuir

Bienvenidos Issues y PRs. Los comentarios de código están en español
(convención histórica del proyecto); los strings al usuario se
externalizan via i18n. Antes de subir, por favor ejecuta:

```bash
ruff check shakevision tests
pytest -v
```

CI debe pasar antes de merge.

---

## 📄 Licencia

[MIT License](LICENSE) © 2025 Yiao

---

## 🙏 Agradecimientos

Gracias a la comunidad [Raspberry Shake](https://raspberryshake.org/)
y al proyecto [ObsPy](https://www.obspy.org/) por la cadena de
herramientas open-source de sismología; y reconocimiento a los
científicos ciudadanos del mundo por su contribución continua al
monitoreo sísmico.
