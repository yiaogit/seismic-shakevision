# Changelog

All notable changes to **ShakeVision OpenData Monitor** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.1] — 2025-05-18

📦 **Binary installers release.**

### Added
- **Pre-built binaries for Windows, macOS (Apple Silicon) and Linux.**
  - Windows: `.zip` (portable, descomprime y ejecuta `ShakeVision.exe`)
  - macOS arm64: `.dmg` con `.app` notarizable (arrastra a /Applications).
    Intel Mac no se distribuye en binario — los usuarios M1+ ya son
    mayoría desde 2020; los de Intel pueden ejecutar desde fuente.
  - Linux: `.AppImage` autoejecutable (`chmod +x` y doble-click)
- Pipeline de empaquetado reproducible (`packaging/build.py` + `shakevision.spec`)
  basado en PyInstaller **onedir** (rápido al arrancar, AV-friendly).
- Workflow `release.yml` que se dispara con cualquier tag `vX.Y.Z`,
  construye los tres binarios en paralelo y publica la GitHub Release
  con notas extraídas automáticamente de este CHANGELOG y tabla de
  SHA-256 checksums.

### Fixed
- **Windows**: `tzdata` añadido como dependencia condicional
  (`sys_platform == 'win32'`) — sin él `zoneinfo` rechazaba incluso
  `ZoneInfo("UTC")` por falta de base IANA en el SO.
- **timezone_service**: tercer nivel de fallback a `datetime.timezone.utc`
  para que `format_local` / `to_iso_local` nunca lancen excepción
  aunque la base IANA esté rota o desinstalada.

### CI / tests
- Alineados 14 tests obsoletos con el comportamiento actual del código
  (i18n por defecto en EN, swap del motor 3D a ECharts-GL, redesign
  del dashboard, sosfiltfilt edge ringing, etc.).
- Ruff sin errores en toda la base.

---

## [0.1.0] — 2025-05-15

🎉 **First public release.**

### Added

#### 🌍 3D Globe (default view)
- ECharts-GL real-time 3D Earth with night-side texture and atmosphere
- ~1500 Raspberry Shake stations (deep green) + ~400 USGS / IRIS stations (mint-green halo)
- Live earthquake markers from USGS GeoJSON feed, color-coded by magnitude (5 buckets: Micro / Light / Moderate / Strong / Major)
- Period selector: 1 h / 24 h / 7 d / 30 d
- Camera controls: zoom in/out, auto-rotate pause, reset view, click-to-zoom country-scale
- Click a USGS station → confirmation dialog → adds to Pro workbench (FIFO max 8 dynamic stations)
- Click a Raspberry Shake station → info-only popup (public SeedLink not available for AM network)

#### 📊 Data Dashboard
- 7 linked ECharts: Top 10 countries (M ≥ 3.0 filter), magnitude/depth histograms, timeline (adaptive density bubbles for >24 h windows), PAGER radar with **region dropdown filter**, period-adaptive distribution buckets, depth × magnitude scatter
- Global period selector (1 h / 6 h / 24 h / 7 d / 30 d) drives ALL charts
- Timezone-aware timestamps via `Intl.DateTimeFormat`
- Station summary KPI (Shake/USGS counts)
- Loading + error overlays with retry

#### 🔬 Pro Workbench (floating window)
- Opened via 🔬 Pro button in AppHeader (or `Ctrl+P` / `Cmd+P`)
- Independent `QMainWindow` — geometry persisted via QSettings
- Sub-tabs: 📡 Live (waveform + spectrogram) / 📜 24h Diary (helicorder) / 🌀 Hodogram (N-E particle motion)
- Control panel: station selector with dynamic add, Butterworth bandpass filter, STA/LTA trigger, sonification slider
- MMI intensity card translating PGV → live intensity badge (12 MMI levels, color-coded)
- Event recorder: STA/LTA trigger → MiniSEED auto-save with pre/post-event window

#### 📡 SeedLink connectivity
- Smart network-to-server routing: IU/US/II/IC → `rtserve.iris.washington.edu:18000`; AM → `rs.local:18000`
- 5-second TCP pre-check with explicit timeout (DNS / firewall / unreachable diagnosis)
- 8-stage progress reporting: DNS → TCP → handshake → SELECTs → first packet → streaming
- Network-aware channels (BHZ/BHN/BHE for IRIS broadband; EHZ/EHN/EHE for Shake)
- **Cancel-at-any-time**: socket shutdown + thread terminate fallback, never crashes the UI

#### 🌐 Internationalization
- Full 4-language support: English (default) / Español / 简体中文 / Français
- **260 translation keys** covering: menus, dialogs, status messages, chart axes/legends/tooltips, MMI levels with descriptions, HTML reports
- Per-locale JSON files, hot-swappable without restart
- Static HTML labels marked with `data-i18n` + JS auto-replacement
- Pythonic `t(key, **vars)` API with `{var}` format string interpolation
- Persistent via QSettings

#### 🕒 Timezone-aware
- Auto-detect system timezone (POSIX `/etc/localtime` symlink → `TZ` env var → `datetime.astimezone()`)
- Manual override via Settings dialog (~600 IANA timezones)
- ALL timestamps display in user's chosen TZ across dashboard, globe, reports, status bar
- No network/IP lookups — privacy-first

#### 📄 Reports
- One-click HTML report export with embedded SVG sparkline and CSS
- PDF export via `QWebEngineView.printToPdf` (no extra dependencies)
- Full i18n: section titles, KPI cards, table headers, event list — all translated

#### 🔊 Sonification
- "Listen to last 60 s" of seismic data, accelerated 1×–60×
- QAudioSink playback with proper state machine (handles macOS Idle/Active timing quirks)
- Stop button safely interrupts mid-playback

#### ⚙ Settings
- Language picker (4 languages with auto-glonyms)
- Timezone editable combo box + "Detect from system" button
- Custom location free-text field (optional, appears on reports)

### Infrastructure
- GitHub Actions CI: Ubuntu / macOS / Windows × Python 3.10 / 3.11 / 3.12 matrix
- Ruff linting + pytest test suite (30+ test modules)
- One-shot resource downloaders: `scripts/install_libs.sh` (ECharts/ECharts-GL ~4 MB) + `scripts/install_fonts.sh` (Inter + JetBrains Mono ~6 MB)

### Known limitations
- Only source distribution in v0.1.0; binary installers (`.exe` / `.dmg` / `.AppImage`) coming in v0.1.1
- Raspberry Shake public SeedLink server does NOT exist — only LAN connection to own device works for AM network
- Globe click "snap to point" centering not yet supported (ECharts-GL `beta` mapping needs per-version calibration); zoom-only works
- Historical replay deferred to v0.2.0

---

## Releases

- **0.1.1** — 2025-05-18 — Binary installers (Win / mac / Linux)
- **0.1.0** — 2025-05-15 — First public release

See [GitHub Releases](https://github.com/yiaogit/seismic-shakevision/releases) for downloadable artifacts.
