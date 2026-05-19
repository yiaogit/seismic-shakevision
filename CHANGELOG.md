# Changelog

All notable changes to **SeismicGuard** (formerly **ShakeVision OpenData Monitor**) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.7.2] — 2026-05-18

🪟 **Hotfix: Windows .exe crash on launch.**

### Fixed
- **PyInstaller `--windowed` startup crash on Windows** (regression
  reported in v0.7.1):
  ```
  Traceback (most recent call last):
    File "__main__.py", line 27, in <module>
  RuntimeError: sys.stderr is None
  ```
  When PyInstaller builds a GUI app without a console window
  (`--windowed` / `--noconsole`), Python's `sys.stdout` and
  `sys.stderr` are both `None`. Two places relied on them and crashed
  before the splash could appear:
    * `__main__.py` — `faulthandler.enable()` (no args) tries to dump
      to `sys.stderr`.
    * `utils/logging.py:setup_logging()` — `StreamHandler(stream=
      sys.stdout)` raises on the first log line.
- Fix in `__main__.py`: if `sys.stderr is None`, route faulthandler
  output to `%TEMP%/seismicguard_faulthandler.log` instead. File
  handle kept alive on `sys` to survive GC.
- Fix in `utils/logging.py`: new `_make_stream_handler()` chooses
  `sys.stdout` → `sys.stderr` → `FileHandler(%TEMP%/seismicguard.log)`
  → `NullHandler` as a robust cascade. The log file path is consistent
  across runs so users can find it for bug reports.

### Changed
- Version bumped 0.7.1 → 0.7.2 in `pyproject.toml`,
  `shakevision/__init__.py`, and `packaging/shakevision.spec`.

---

## [0.7.1] — 2026-05-18

🎨 **New app icon** — cracked-earth SeismicGuard mark on deep navy.

### Added
- New app icon (`packaging/macos/icon.icns`, `packaging/windows/icon.ico`,
  `packaging/linux/icon.png`) with deep-navy rounded-square background,
  yellow cracked-earth glyph, and "SeismicGuard" wordmark below.
- `shakevision/assets/branding/app_icon.png` + `app_icon_512.png` bundled
  for in-app use (About dialog, splash fallback, etc.).
- ICO is multi-resolution (16/32/48/64/128/256); ICNS contains the
  standard macOS variant set; Linux PNG is 1024×1024 for AppImage and
  `.desktop` entries.

### Changed
- `packaging/shakevision.spec` BUNDLE bumped from `0.3.0` → `0.7.1`
  (CFBundleShortVersionString + CFBundleVersion also updated from the
  stale `0.1.1` placeholder).
- Version bumped 0.7.0 → 0.7.1 in `pyproject.toml` and
  `shakevision/__init__.py`.

---

## [0.7.0] — 2026-05-18

🎨 **Major redesign release** — rebrand, theming, internationalisation,
onboarding, profile, location services, PDF polish.

### Rebrand
- Renamed app from **ShakeVision** to **SeismicGuard** everywhere
  user-visible (window title, splash, About, status messages, reports).
  Python package stays `shakevision` for backwards-compat with installs.

### Theming
- New `ThemeManager` + `LayerModeManager` singletons (themes
  independent of pro/standard layer modes).
- macOS-Sonoma / ChromeOS Material-3 palette overhaul: system-blue
  accent `#0a84ff`, iOS-style hairlines, pill buttons, capsule tabs,
  custom tooltips, drop shadows.
- Light theme reworked from scratch: dashboard cards, workbench
  panels, intensity card, profile dialog all use dynamic CSS variables.
- `ui/animations.py` + `ui/elevation.py` + `ui/pg_theming.py` helpers
  for hover/press micro-animations, Material elevation shadows, and
  theme-aware pyqtgraph plots.
- AppHeader logo with real-time theme awareness (PNG swap on switch).
- Globe view always uses dark background regardless of Qt theme.

### Internationalisation
- Full i18n infrastructure (`LocaleService`, `t()` helper).
- 435 keys × 4 locales (English, Spanish, Chinese, French) at 100 %
  parity, covering UI, status messages, web views (globe + dashboard
  ECharts), report templates.

### Onboarding
- Splash screen with progress bar.
- `Localízame` welcome transition with halo animation, system
  timezone detection (no network).
- 6-step onboarding wizard (welcome / language / timezone / theme /
  layer mode / done) with live re-translation as the user picks
  language.
- Auto-popup timezone dropdown for macOS QComboBox.

### Profile dialog (📊)
- AppHeader 👤 entry point opens a modal `ProfileDialog` with:
  - Identity card with GitHub avatar (OAuth Device Flow, no secret).
  - 6 usage stat cards (launches, time in app, earthquakes viewed,
    stations clicked, audio played, reports generated).
  - **Recent activity timeline** (last 50 events with relative time,
    stored locally in QSettings via `ActivityLog`).
- `UsageTracker` records aggregates; `ActivityLog` records events.

### Region & time (Settings → General)
- Timezone dropdown with all IANA zones + "Detect from system" button.
- **Auto-detect location** button: one-click IP-based geolocation via
  ip-api.com (no key, HTTP, 5 s timeout). Address can be detected
  automatically or typed manually. Privacy-first — never called in
  background.

### Globe (3D Earth)
- Three visual modes:
  - **Day**: NASA Blue Marble texture, realistic shading.
  - **Night**: Blue Marble darkened + Black Marble city lights as
    emission layer (industry-standard NASA Worldview approach;
    final iteration of 4 attempts).
  - **Holographic**: country borders + multi-language labels
    (≤ 100 countries, Taiwan blocklisted), reactive to language.
- Auto-recovery from WebGL context loss with ResizeObserver +
  `safeSetOption` wrapper.
- `download_globe_assets.py` script with mirror fallback for optional
  texture files.

### Reports & PDF export
- `report.html` template fully internationalised.
- **PDF export overflow fixed**: `@page A4 + 18 mm margins`, table
  columns now wrap (`table-layout: fixed; word-break: break-word`),
  KPI grid switches from 4 → 2 columns in print, header repeated on
  each page, white print background.
- QWebEngineView sized 794 × 1123 px (A4 96 dpi) to minimise
  Chromium scaling glitches.

### Settings
- Reset tab replaces the old Backup tab: one-click "Clear cache and
  restart" wipes all `QSettings` (10 apps) + `~/.cache/shakevision/`
  with a hard confirmation dialog → `QApplication.quit()`. Next
  launch re-runs the onboarding wizard.

### Removed / postponed
- Right-click favourite-earthquake from the globe (7 implementation
  iterations couldn't make echarts-gl's `scatter3D` raycaster
  cooperate reliably; the underlying `FavoritesStore` and Profile
  dialog plumbing remains for a future button-based UX).

### Fixed
- Profile dialog dark-mode rendering: cards were white over dark
  background because QSS read theme colours at construction time
  only — now re-applied on `ThemeManager.changed_signal`.
- Black rectangles inside Profile cards: explicit
  `background: transparent` on all child QLabels.
- All click feedback (station click, add-to-workstation) broken by a
  short-lived `rebuildChart()` call in `ResizeObserver` — reverted to
  `chart.resize()` only.
- Recoverable WebGL `getRoots` errors no longer surface in the
  user-facing error overlay (whitelist + `safeSetOption`).

### Added (services)
- `services/activity_log.py` — 14-kind enum + 50-entry ring buffer.
- `services/location_service.py` — async IP geolocation.
- `services/clear_cache.py` — orchestrated QSettings + disk-cache wipe.
- `services/github_auth.py` — GitHub Device Flow.

---

## [0.3.0] — 2025-05-18

🛰 **Custom LAN Raspberry Shake support.**

### Added
- **AddShakeDialog** (`ui/add_shake_dialog.py`) — modal para registrar
  un Raspberry Shake propio en la red local: campo IP/hostname,
  código de estación, puerto y etiqueta. Botón "Test connection"
  hace pre-check TCP de 5 s en hilo aparte y pinta resultado verde/
  rojo, sin bloquear la UI.
- **ShakePresetStore** (`services/shake_presets.py`) — singleton
  persistente que guarda los Shakes LAN del usuario en QSettings
  (`shakes/lan_presets`, JSON). API simple (`all/add/delete/rename/
  find_by_host`) + señal `presets_changed` para que cualquier vista
  se refresque sin polling.
- **Entrada "➕ Add LAN Shake…" en el desplegable** de estaciones
  del ControlPanel. Al seleccionarla se abre AddShakeDialog y, si
  acepta, el preset queda añadido + persistido + auto-seleccionado.
- **Nueva pestaña "My Shakes"** en el diálogo Settings con CRUD
  completo (Add / Rename / Delete + doble-click para editar). Lista
  vacía muestra un placeholder amigable.
- 60+ claves i18n nuevas (EN / ES / ZH / FR) para todo el flujo de
  Shake LAN, incluyendo mensajes de error TCP/DNS específicos.
- Tests: `test_shake_presets.py` (CRUD + round-trip QSettings + 9
  casos), `test_add_shake_dialog.py` (validación campo a campo).

### Changed
- ControlPanel ahora se suscribe a `ShakePresetStore.changed_signal()`
  para reflejar cambios externos (otra ventana, Settings) en vivo.

---

## [0.2.0] — 2025-05-18

⏯ **Historical replay from IRIS dataselect.**

### Added
- **DataselectClient** (`services/dataselect.py`) — cliente síncrono
  del servicio FDSN dataselect/1 de IRIS para descargar MiniSEED de
  cualquier intervalo histórico. Cacheado en disco (TTL 30 días por
  ser datos inmutables), soporta `force_refresh`, distingue 204/404
  como `NoDataAvailable` (caso esperado, no error). Sin Qt → 100%
  testeable.
- **ReplaySource** (`sources/replay.py`) — implementa `DataSource`
  reproduciendo un `obspy.Stream` con velocidades 0.5× / 1× / 2× /
  5× / 10× / 30× / 60×. Reloj puro (`_ReplayClock`) separable y
  testeable. API: `start / stop / pause / resume / seek / set_speed`.
  Emite `progress(cursor_s, duration_s)` para barras de progreso y
  `finished` al terminar.
- **Pro tab "⏯ Replay"** (`ui/replay_panel.py`) — formulario con
  N.S.L.C. + datetime UTC + duración + selector de velocidad +
  botones Download / Play / Pause / Stop + barra de progreso
  arrastrable. Buffer/processor/spectrum independientes del Live
  tab → ambos pueden estar activos simultáneamente. Descarga en
  hilo separado con loading overlay; errores friendly (sin datos,
  IRIS caído, timeout).
- 18 claves i18n nuevas (EN / ES / ZH / FR) para todo el flujo de
  replay.
- Tests: `test_dataselect.py` (mock urllib: URL FDSN bien formada,
  caching, 204/404 → NoDataAvailable, fallback a caché obsoleta),
  `test_replay.py` (núcleo `_ReplayClock` + ReplaySource con
  obspy.Stream sintético).

### Changed
- `shakevision.sources.__init__` exporta `ReplaySource` además de
  los anteriores.

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
- **Windows · auto-detección de zona horaria**: nueva dependencia
  `tzlocal` que traduce el nombre del registro de Windows ("China
  Standard Time", "Pacific Standard Time"…) al estándar IANA
  ("Asia/Shanghai", "America/Los_Angeles"). Antes la app caía a UTC
  en arranques limpios de Windows; ahora detecta correctamente la
  zona del SO.
- **Windows · SmartScreen "Unrecognized app"**: añadido
  `VS_VERSIONINFO` (CompanyName, ProductName, FileDescription,
  versión…) al `.exe`. No elimina el warning (eso requiere firma EV,
  en la roadmap v1.0), pero reduce la fricción y mejora la
  legitimidad percibida del binario.
- **Globe · auto-recuperación de WebGL en Windows**: tras
  minimizar/restaurar la ventana o reiniciar el proceso GPU de
  Chromium, ECharts dejaba de pintarse con `Cannot read properties
  of null (reading 'getRoots')`. Ahora el JS detecta el
  `webglcontextlost`, reconstruye el chart y reaplica el estado.
  Triple defensa: evento WebGL + wrapper `safeSetOption` + heartbeat
  cada 10 s.
- **timezone_service**: tercer nivel de fallback a `datetime.timezone.utc`
  para que `format_local` / `to_iso_local` nunca lancen excepción
  aunque la base IANA esté rota o desinstalada.
- **FileCache.age_seconds()**: clamp a `≥ 0` para tolerar el desfase
  de nanosegundos entre `time.time()` y `st_mtime` de NTFS en Windows.

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

- **0.3.0** — 2025-05-18 — Custom LAN Raspberry Shake support
- **0.2.0** — 2025-05-18 — Historical replay from IRIS dataselect
- **0.1.1** — 2025-05-18 — Binary installers (Win / mac / Linux)
- **0.1.0** — 2025-05-15 — First public release

See [GitHub Releases](https://github.com/yiaogit/seismic-shakevision/releases) for downloadable artifacts.
