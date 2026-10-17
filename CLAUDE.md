# SeismicGuard — Project Context for Claude

> This file is the entry point any Claude (or Claude Code) agent should
> read first when working on this repo. It encodes the project's
> identity, current state, architecture, conventions, and open work so
> the agent doesn't have to re-derive context from a cold start.

---

## 1. What this is

**SeismicGuard** (formerly **ShakeVision**, renamed in v0.7.0) is a
cross-platform desktop seismic monitoring workbench. It ingests live and
historical seismic data from public networks (USGS, IRIS/FDSN, Raspberry
Shake / ShakeNet) and visualizes earthquakes on a 3D globe + dashboard
charts + traditional waveform / helicorder / spectrogram panels.

The audience is two-tier:

* **Standard mode** — non-experts: 3D globe with live quakes, MMI
  intensity card, KPI dashboard, exportable HTML/PDF report.
* **Professional mode (Workbench)** — researchers / Shake hobbyists:
  real-time waveform from a chosen station (SeedLink) or replay from
  IRIS dataselect, STA/LTA event trigger, MiniSEED recording, FFT
  spectrogram, helicorder, particle-motion plot, sonification.

Languages: **English / Español / 中文 / Français**, switchable at
runtime via the gear icon in the header.
Themes: **light** / **dark** (the legacy "auto" mode was removed in
v0.7.6 — see CHANGELOG).

Repo URL: https://github.com/yiaogit/seismic-shakevision
License: MIT.

---

## 2. Current state (read this first)

> 📌 **当前会话方向 (user)**
> 1. 把本文件与 `docs/roadmap.md` 校准到 **0.8.3.0** 的真实状态（本次已做）。
> 2. **本机冒烟验证**：界面启动、数据面板「实时 | 分析」双页、历史回放、
>    报告导出——补上沙箱里无法验证的渲染类工作，再据发现优化。结果见 §9。

| Item | Value |
|---|---|
| Current version (4 files, see §5) | **0.8.3.0** — committed, tagged and released |
| Latest tag pushed to origin | `v0.8.3.0` (commit `dd45523`, 2026-06-28) |
| HEAD | `main` @ `295adbd` — one CI release-notes fix on top of the tag |
| Latest **release with installers** on GitHub Releases | `v0.8.3.0` — macOS arm64 `.dmg`, Windows `.zip`, Linux `.AppImage` + `SHA256SUMS.txt` |
| Branch | `main` |
| Python | 3.10 / 3.11 / 3.12 (CI matrix); 3.14 runs locally but is **off-matrix** |
| Qt binding | PySide6 |
| i18n keys | **739** per locale (en/es/fr/zh), aligned |

### Known issues / unfinished

1. **No auto-update mechanism.** Users must manually download new
   installers from the GitHub Releases page. (Tracked for v1.0.0.)
2. **GUI / obspy tests need full deps + a display.** Pure tests
   (i18n / measurements / recordings_list / response / seismic_stats /
   event_filter…) run headless; the full suite needs the venv from §5
   on a real machine (see §9).
3. **Dashboard Analysis layer — render validated locally (§9).** Historical
   query + pro charts + analysis report all render on a real machine. The
   remaining gap is the **empty state**: when no analysis query has succeeded
   (or `/count` exceeds 20 000) the page keeps showing live KPIs/charts.
4. **Light theme tab bar (macOS).** `QTabWidget.setDocumentMode(True)` keeps a
   native dark strip in light mode, making inactive tabs unreadable;
   `setDocumentMode(False)` fixes it (verified in §9).
5. **Live re-translation gaps.** Dashboard region combos + analysis status text
   do not retranslate; `"1 día"` bucket label is hardcoded Spanish; Event
   Center’s capped-row hint is overwritten on language change.
6. **Two intentionally-unused i18n keys** (`common.cancel`,
   `profile.tab_title`): the app never calls them, but
   `tests/test_i18n.py` and `tests/test_profile_view.py` assert them as
   a locale contract. The dead-key scan must therefore include `tests/`,
   not just `shakevision/` + web JS. All 4 locales stay aligned
   (739 keys, same placeholders).
7. **`ui/sidebar_nav.py` has no runtime consumer** — the shell uses a
   `QTabWidget` (main_window.py); only `tests/test_sidebar_nav.py`
   imports the sidebar. Either re-wire it or delete it in a cleanup.
8. **Python 3.14 is off the CI matrix.** It installs and runs locally
   (565/565 tests green, §9), but 3.10–3.12 is the supported
   configuration — reproduce any 3.14-only bug on 3.12 before chasing it
   (`brew install python@3.12` if needed).
9. **Tooling drift:** `ruff` is unpinned (`>=0.4`), so 0.17.x now reports
   576 findings by default while 0.12.7 is clean. Pin it or add an
   explicit `[tool.ruff.lint] select`.
10. **Docs drift**: CLAUDE.md and `docs/roadmap.md` had lagged behind
   0.8.x. Update this file in the same commit as any version bump.

---

## 3. Architecture

```
ShakeVision/
├─ shakevision/                  ← Python package
│  ├─ __main__.py                ← App entry point; SSL/certifi bootstrap,
│  │                                ThemeManager.init, splash → MainWindow
│  ├─ __init__.py                ← __version__, APP_NAME ("SeismicGuard")
│  │
│  ├─ ui/                        ← All Qt widgets / windows (40+ files)
│  │  ├─ main_window.py          ← The shell: QTabWidget with 4 top tabs
│  │  │                             (Globe / Data / Events / My collection)
│  │  │                             + lazily-opened floating Pro window
│  │  ├─ pro_window.py           ← Standalone "Workbench" window (waveform,
│  │  │                             spectrogram, helicorder, particle, replay)
│  │  ├─ workbench_controller.py ← Owns the realtime pipeline (source, buffer,
│  │  │                             detector, timers, audio) and drives ProWindow;
│  │  │                             MainWindow only wires 6 control signals
│  │  ├─ app_header.py           ← Top bar: theme cycle, layer toggle, Pro, gear
│  │  ├─ sidebar_nav.py          ← Legacy vertical nav — runtime-unused, only
│  │  │                             tests/test_sidebar_nav.py imports it
│  │  ├─ globe_view.py           ← QWebEngineView wrapping ECharts-GL globe
│  │  ├─ dashboard_view.py       ← QWebEngineView; TWO independent pages
│  │  │                             (Live | Analysis) + pro-stat charts (0.8.3)
│  │  ├─ historical_search_bar.py ← fdsnws-event query form (range/mag/region)
│  │  ├─ event_filter_bar.py     ← Reusable quake filter bar (mag/depth/text)
│  │  ├─ date_picker.py          ← Shared UTC date/time pickers (clamped to now)
│  │  ├─ range_slider.py         ← Draggable brush-style range slider (0.8.3)
│  │  ├─ combo_utils.py          ← Locale-aware QComboBox sizing (popup width)
│  │  ├─ signal_safety.py        ← `subscribe()` — safe singleton-signal wiring
│  │  ├─ control_panel.py        ← Workbench control surface (station/filter/audio)
│  │  ├─ waveform_widget.py      ← Scrolling 3-channel pyqtgraph trace
│  │  ├─ helicorder_widget.py    ← Drum recorder (24h)
│  │  ├─ spectrogram_widget.py   ← Sliding-window FFT image
│  │  ├─ particle_motion_widget.py ← N-E plane particle trajectory + polarization azimuth (stabilized redraw, v0.8.0)
│  │  ├─ spectrum_panel.py       ← PSD power-spectrum panel (power dB vs freq, v0.8.0)
│  │  ├─ intensity_card.py       ← MMI translation card (lay user)
│  │  ├─ replay_panel.py         ← Historical review: static waveform browser (0.8.0 rewrite — zoom/pan + UTC axis + band select + deconv VEL/DISP/ACC + ZNE→ZRT rotate + TauP P/S + dB spectrogram + PSD + spec/PSD toggles + PNG/CSV/QuakeML export + reopen saved catalog review; ReplaySource no longer used by UI)
│  │  ├─ event_center_panel.py   ← TOP-LEVEL "Events" tab: quake table + nearby stations (Δ°/km/category) + ☆favorite (v0.8.0)
│  │  ├─ event_list_panel.py     ← Sortable quake-table component reused inside event center (v0.8.0)
│  │  ├─ my_data_panel.py        ← TOP-LEVEL "我的/My collection" tab: favorites (quakes/stations) + records (recordings/catalog), reopen review, open-folder (v0.8.0; replaces local_data_panel)
│  │  ├─ add_shake_dialog.py     ← Add LAN Shake station (v0.3.0)
│  │  ├─ audio_player.py         ← QAudioSink wrapper for sonification
│  │  ├─ profile_view.py         ← Profile page content (usage stats/activity)
│  │  ├─ settings_dialog.py      ← Multi-tab Ajustes (language/timezone/...)
│  │  ├─ profile_dialog.py       ← Local user profile + GitHub OAuth + favs
│  │  ├─ onboarding_wizard.py    ← First-run 6-step wizard (lang/tz/theme/...)
│  │  ├─ splash.py               ← Loading screen with progress bar
│  │  ├─ localizame_view.py      ← "Localízame" intro page with halo
│  │  ├─ github_login_dialog.py  ← GitHub device-flow login
│  │  ├─ loading_overlay.py      ← Reusable spinner/error overlay (i18n live)
│  │  ├─ pdf_exporter.py         ← QWebEngineView.printToPdf wrapper
│  │  ├─ animations.py           ← Breathe/fade/pulse factories
│  │  ├─ theme.py                ← Palettes (light/dark) + global QSS
│  │  ├─ theme_manager.py        ← Singleton (light/dark only; auto removed)
│  │  ├─ layer_mode_manager.py   ← Standard/Professional toggle
│  │  ├─ macos_native.py         ← Transparent titlebar / full-content view
│  │  ├─ icons.py                ← Logo/icon centralized loader
│  │  ├─ elevation.py            ← Drop-shadow helpers
│  │  └─ pg_theming.py           ← Apply theme to pyqtgraph PlotItems
│  │
│  ├─ services/                  ← Network + persistence + workers
│  │  ├─ usgs.py                 ← GeoJSON earthquake feed client
│  │  ├─ fdsn_event.py           ← USGS fdsnws-event historical catalog client
│  │  │                             (ANSS, ~1900→now; 20k-event cap →
│  │  │                             FDSNTooManyError)
│  │  ├─ fdsn_worker.py          ← QThread worker for large historical queries
│  │  ├─ region_presets.py       ← Curated country/region bounding boxes
│  │  ├─ geo_region.py           ← Offline Flinn–Engdahl region + country
│  │  │                             (babel / reverse_geocoder, soft deps)
│  │  ├─ iris.py                 ← FDSN station catalog (IU / US networks)
│  │  ├─ shakenet.py             ← Raspberry Shake FDSN station catalog
│  │  ├─ dataselect.py           ← IRIS FDSN dataselect (historical MiniSEED)
│  │  ├─ cache.py                ← FileCache (TTL-based; survives restarts)
│  │  ├─ worker.py               ← QObject async refresh worker (USGS + stations)
│  │  ├─ data_models.py          ← Earthquake / ShakeStation / PagerLevel dataclasses
│  │  ├─ report.py               ← HTML/CSS report generator
│  │  ├─ timezone_service.py     ← IANA-based tz singleton (auto-detect first)
│  │  ├─ location_service.py     ← IP geolocation (free tier, cached)
│  │  ├─ shake_presets.py        ← Persistence for LAN-added Shake stations
│  │  ├─ favorites_store.py      ← Persistent favorited quakes + stations (quakes now carry lat/lon/depth, v0.8.0)
│  │  ├─ catalog_store.py        ← Persistent QuakeML review catalog (~/SeismicGuard/catalog.xml); add/list/get/remove (v0.8.0)
│  │  ├─ response.py             ← StationXML instrument response: remove_response + station coords (v0.8.0)
│  │  ├─ activity_log.py         ← Profile "Recent activity" timeline data
│  │  ├─ usage_tracker.py        ← Local launch + session metrics (no network)
│  │  ├─ github_auth.py          ← OAuth device flow (no client secret needed)
│  │  ├─ settings_backup.py      ← Import/export QSettings as JSON
│  │  └─ clear_cache.py          ← Settings → "Clear cache" implementation
│  │
│  ├─ sources/                   ← Realtime data source abstractions
│  │  ├─ base.py                 ← Abstract base + samples_received signal
│  │  ├─ mock.py                 ← Synthetic source for tests + demo
│  │  ├─ seedlink.py             ← ObsPy EasySeedLinkClient wrapper (LAN Shake)
│  │  └─ replay.py               ← Replay arbitrary IRIS dataselect at N× speed
│  │
│  ├─ processing/                ← DSP + analytics (no Qt)
│  │  ├─ buffer.py               ← Thread-safe ring buffer
│  │  ├─ filters.py              ← Butterworth bandpass + detrend
│  │  ├─ detector.py             ← STA/LTA + trigger state machine
│  │  ├─ event_filter.py         ← Pure quake filtering (mag/depth/window/text)
│  │  ├─ magnitude_color.py      ← Green→red magnitude colour scale (pure)
│  │  ├─ seismic_stats.py        ← Mc (MAXC) · b/a-value (Aki–Utsu + Shi&Bolt) ·
│  │  │                             FMD · seismic moment/energy · cumulative
│  │  │                             series · Omori fit · depth stats (0.8.3)
│  │  ├─ spectrum.py             ← Sliding-window FFT (scipy.signal.spectrogram)
│  │  ├─ recorder.py             ← Save events to MiniSEED on trigger
│  │  ├─ sonifier.py             ← Samples → audio bytes
│  │  ├─ intensity.py            ← MMI translation (magnitude/distance → MMI)
│  │  └─ measurements.py         ← ZNE→ZRT rotate · polarization azimuth · Welch PSD · great-circle distance (pure, tested, v0.8.0)
│  │
│  ├─ web/                       ← HTML/JS/CSS bundled with the app
│  │  ├─ globe/                  ← ECharts-GL 3D globe (Blue Marble / Black
│  │  │                             Marble / holo) + optional lib/ + world.json
│  │  ├─ dashboard/              ← Live + Analysis chart pages (ECharts);
│  │  │                             lib/echarts.min.js downloaded by script
│  │  └─ report/                 ← template.html (live) + template_analysis.html
│  │                                (stats report, inline SVG) + styles.css
│  │
│  ├─ i18n/                      ← Locale system
│  │  ├─ __init__.py             ← Public API: t(), LocaleService
│  │  ├─ service.py              ← Singleton + language_changed signal + t()
│  │  └─ locales/{en,es,fr,zh}.json   (739 flat dotted keys each)
│  │
│  ├─ utils/                     ← Pure helpers (no Qt)
│  │  ├─ logging.py              ← Centralized logger
│  │  ├─ periods.py              ← Period→seconds + time-window quake filter
│  │  └─ timescale.py            ← Non-linear epoch↔fraction mapping (slider)
│  └─ assets/                    ← Fonts (Inter, JetBrains Mono), branding logos,
│                                  app icons (.ico/.icns/.png); textures live
│                                  in web/globe/lib/ (gitignored, scripted)
│
├─ tests/                        ← pytest suite (62 files; GUI tests need display)
├─ docs/                         ← Design/roadmap notes (see §8)
├─ packaging/                    ← PyInstaller spec + Windows version_info
│  ├─ shakevision.spec
│  └─ windows/version_info.txt
├─ scripts/                      ← Dev helpers: install_libs.sh (ECharts + globe
│  │                                textures), install_fonts.sh,
│  │                                download_globe_assets.py
├─ .github/workflows/
│  ├─ ci.yml                     ← lint + tests, 3 OS × 3 Python on every push/PR
│  └─ release.yml                ← PyInstaller builds + GitHub Release on tag v*
├─ pyproject.toml                ← Version + deps (certifi pinned post-v0.7.6)
├─ CHANGELOG.md                  ← Keep-a-Changelog format, source of truth
├─ CLAUDE.md                     ← THIS FILE
├─ README.md / README.{en,es,fr}.md
└─ LICENSE                       ← MIT
```

---

## 4. Conventions worth knowing

### Theme
- `ThemeManager` is a singleton with two modes only (`dark`, `light`)
  after v0.7.6.1; QSettings `auto` migrates to `dark` automatically.
- `apply_theme(app, theme)` rewrites module-level `COLOR_*` globals AND
  applies QPalette + app-wide QSS. Widgets that read theme colors
  should do `from shakevision.ui import theme as _t` and access
  `_t.COLOR_BACKGROUND` at paint time (NOT at import time) so they
  pick up live changes.
- Widgets reactive to theme should `connect(ThemeManager.changed_signal(), …)`.
  Connect BEFORE constructing children to avoid missing the first emit
  (this was the v0.7.6.1 wizard sync bug — see CHANGELOG).

### i18n
- Always use `t("some.key")` from `shakevision.i18n`. Never hardcode
  user-visible strings.
- When adding a key, add it to ALL FOUR locales (`en/es/fr/zh.json`).
- For live retranslate, `LocaleService.language_changed_signal().connect(…)`
  in the widget's `__init__` and refresh setText calls in a `_retranslate`
  method.
- Pitfalls: signal handlers must guard against dead C++ widgets with
  `try/except RuntimeError`, AND disconnect via `self.destroyed` to
  avoid pytest-qt teardown cascades (see v0.7.6.1 LoadingOverlay fix).

### Dashboard (Live | Analysis)
- `DashboardPanel` (`ui/dashboard_view.py`) hosts **two truly independent
  pages** since 0.8.3: **Live** (rolling USGS feed, region selector;
  Top-10 stays global) and **Analysis** (USGS `fdsnws-event` historical
  catalog: region preset + window + min magnitude).
- The analysis window is chosen with `ui/range_slider.py` — a brush-style
  dual-handle slider on a **non-linear** time axis (`utils/timescale.py`,
  more resolution near “now”). Date pickers elsewhere come from
  `ui/date_picker.py` (always clamped to “now” in UTC).
- **All statistics live in `processing/seismic_stats.py`** (pure, tested:
  Mc/MAXC, Aki–Utsu b-value + Shi & Bolt σ, FMD, M0/energy, cumulative
  series, Omori fit, depth stats). `dashboard_view.build_pro_stats()`
  marshals them into the payload; `web/dashboard/dashboard.js` only draws.
- Historical queries are pre-checked with `fdsnws/count` against the
  service's 20 000-event cap; the real query runs in
  `services/fdsn_worker.py` (QThread), never on the UI thread.
- Read `docs/dashboard-pro.md` before touching the dashboard or the
  report analysis layout.

### Signal wiring
- For singleton signals (theme / locale / any long-lived object) use
  `subscribe(widget, signal, slot)` from `ui/signal_safety.py` instead
  of a bare `.connect()`: it disconnects on `destroyed` and guards the
  slot against dead C++ objects (the pytest-qt teardown crash).
- `t()` and `LocaleService` are re-exported from `shakevision.i18n`.

### Pure quake helpers
- `processing/event_filter.py` — magnitude / depth / time-window /
  multilingual text filtering, shared by Event Center and My collection.
- `processing/magnitude_color.py` — green→red magnitude scale used by
  tables, legend and globe markers.
- Keep these Qt-free so they stay unit-testable headless.

### Error overlays
- `LoadingOverlay` is the standard "loading / error + retry" widget.
  Use `show_loading(message, subtitle)`, `show_error(message, subtitle,
  show_retry=True)`, `hide_overlay()`.
- All loading/error strings go through `t()` keys (`overlay.loading`,
  `overlay.btn_retry`, `error.<service>.contact`).

### macOS / Windows packaging
- PyInstaller spec is at `packaging/shakevision.spec`. macOS bundle is
  named `ShakeVision.app` (not SeismicGuard) for back-compat with old
  installs.
- macOS .dmg needs `certifi` collected via `collect_data_files` AND
  added to `hiddenimports` — without this, HTTPS fails inside the
  bundle (v0.7.6 hotfix).
- Windows .exe is built `noconsole` — anything that writes to
  `sys.stderr` directly will crash; route through `logger` instead
  (v0.7.2 hotfix).

### QSettings keys
- Theme:       `SeismicGuard / Theme / theme/mode`
- Onboarding:  `SeismicGuard / Onboarding / wizard/completed`
- Locale:      `SeismicGuard / I18n / locale`
- Timezone:    `SeismicGuard / Timezone / tz/iana`
- Shake presets, favorites, profile etc. — see their `services/` files

---

## 5. Build / test / release commands

```bash
# 0) One-time env + web assets (lib/, textures, fonts are gitignored)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
bash scripts/install_libs.sh              # ECharts-GL/echarts + globe textures
bash scripts/install_fonts.sh             # Inter / JetBrains Mono
python scripts/download_globe_assets.py   # Blue Marble day/night + world.json

# Run from source (dev)
.venv/bin/python -m shakevision
# Headless import smoke-test (no window):
QT_QPA_PLATFORM=offscreen .venv/bin/python -m shakevision --help  # if supported

# Tests
.venv/bin/pytest -q                                  # full suite (display + obspy)
.venv/bin/pytest tests/test_onboarding_wizard.py -v  # one file
.venv/bin/ruff check .                               # lint

# Compile-only sanity (no runtime)
.venv/bin/python -m compileall -q shakevision/

# Build local installer (requires PyInstaller, slow ~10-20 min)
.venv/bin/pyinstaller packaging/shakevision.spec

# Cut a release
# 1. Bump version in: pyproject.toml + shakevision/__init__.py
#                   + packaging/shakevision.spec (3 places: version, CFBundleShortVersionString, CFBundleVersion)
#                   + packaging/windows/version_info.txt (filevers, prodvers, FileVersion, ProductVersion)
# 2. Add CHANGELOG.md [X.Y.Z] section
# 3. git commit + git tag -a vX.Y.Z -m "..."
# 4. git push origin main && git push origin vX.Y.Z
# 5. The release.yml workflow (triggered by tag push) builds 3
#    platforms via PyInstaller (~25-40 min) and uploads to
#    https://github.com/yiaogit/seismic-shakevision/releases/tag/vX.Y.Z
```

CI workflow is `.github/workflows/ci.yml` (push + PR on main).
Release workflow is `.github/workflows/release.yml` (tag `v*` push).

---

## 6. Recent version history (most → least recent)

| Version | Date | One-line summary |
|---|---|---|
| **0.8.3.0** | 2026-06-28 | Data panel split into **two independent pages** (Live \| Analysis) + draggable `RangeSlider`; historical `fdsnws-event` catalog with `/count` pre-check; pure `seismic_stats` + pro charts (GR/b, energy, Mc(t), Omori, depth sections/spatial density); analysis report (inline SVG, Spanish/4 locales); Event Center historical mode + region presets + offline Flinn–Engdahl/babel search; magnitude colour scale; reworked live report; many table/filter/combo fixes. |
| **0.8.0.0** | 2026-06-17 | Major: Replay rewritten as pro waveform browser (deconv/rotate/TauP/PSD/export); top-level Event Center + nearby stations; "My collection" tab (favorites + recordings + QuakeML catalog, reopen review + open-folder export); button-based favorites; particle-motion stabilization + polarization azimuth; macOS fullscreen-close fix. Folds in unreleased 0.7.7 audit work. |
| 0.7.6.1 | 2026-05-21 | Overlay+services i18n cleanup, wizard initial-theme sync fix, removed `auto` theme mode |
| 0.7.6 | 2026-05-20 | macOS .dmg SSL CERTIFICATE_VERIFY_FAILED hotfix (certifi-backed default HTTPS context) |
| 0.7.5 | 2026-05-19 | One-click GitHub sign-in + Workbench rename polish + Windows fixes (combo arrow, Reset labels) |
| 0.7.4 | … | 7 Windows / Onboarding / Settings / Profile fixes (+ 5 patches) |
| 0.7.3 | … | Windows globe textures / world.json missing (CI install_libs.sh) |
| 0.7.2 | … | Windows .exe noconsole startup crash (sys.stderr is None) |
| 0.7.1 | … | New SeismicGuard logo + icons |
| 0.7.0 | … | Rebrand ShakeVision → SeismicGuard, theming infra, full i18n, onboarding wizard, profile, location |
| 0.6.x | … | macOS/ChromeOS theme overhaul (12 phases), Blue Marble day / Black Marble night, country labels, favorites |
| 0.5.x | … | Splash + Localízame, OAuth, profile dialog, settings import/export |
| 0.4.x | … | Rebrand prep, theme manager + day/night, globe layer modes |
| 0.3.0 | … | Add LAN Shake dialog + "My Shakes" persistence |
| 0.2.0 | … | IRIS dataselect client + Replay panel + ReplaySource |
| 0.1.1 | … | Binary installers (PyInstaller), release pipeline |
| 0.1.0 | … | Initial scaffold |

See `CHANGELOG.md` for the source-of-truth detail.

---

## 7. When adding new work, follow this rhythm

1. **Read the task carefully.** If it's a bug, repro before patching.
2. **Touch i18n keys early.** If your change adds user-visible strings,
   add the keys to all 4 locales in the same commit.
3. **Maintain theme-awareness.** Read `COLOR_*` at runtime via the
   `theme as _t` import idiom, not at import time.
4. **Wire `theme_changed` / `language_changed` BEFORE child
   construction**, not after, to avoid missing initial emits.
5. **Guard slots with `try/except RuntimeError`** when subscribing
   widget methods to global singletons — pytest-qt teardown is brutal.
6. **Compile-check + run targeted tests** before committing:
   `python -m compileall -q shakevision/ && pytest tests/test_<area>.py -q`.
7. **Write a CHANGELOG entry** under `## [Unreleased]` (or the current
   in-flight version) with `### Added/Changed/Fixed/Removed`.
8. **Dashboard / report work**: read `docs/dashboard-pro.md` first; keep
   the Live and Analysis pages independent (no shared charts) and put
   new math in `processing/seismic_stats.py` (pure + tested), not JS.
9. **Releasing**: see §5. Don't forget to bump all FOUR version files,
   not just `pyproject.toml`.

---

## 8. Quick "where do I find…" cheatsheet

| Need | Look in |
|---|---|
| Add a new chart to the dashboard | `shakevision/web/dashboard/` + `dashboard_view.py` |
| Change globe colors / texture / labels | `shakevision/web/globe/` |
| Hook a new earthquake feed | new client in `services/`, register in `worker.py` |
| Add a settings tab | `ui/settings_dialog.py` (`_build_*_tab` methods) |
| Localize a new string | `t("my.key")` + 4 JSON files in `i18n/locales/` |
| Change the splash / onboarding | `ui/splash.py` / `ui/onboarding_wizard.py` |
| Adjust the theme palette | `ui/theme.py` (`LIGHT_PALETTE` / `DARK_PALETTE`) |
| Add Windows / macOS metadata | `packaging/windows/version_info.txt` / `packaging/shakevision.spec` |
| Historical catalog / region presets | `services/fdsn_event.py`, `ui/historical_search_bar.py`, `services/region_presets.py` — design in `docs/events-i18n-timezone.md` |
| Seismic statistics (Mc, b-value, energy, Omori) | `processing/seismic_stats.py` (pure) + `docs/dashboard-pro.md` |
| Analysis time window / range slider | `ui/range_slider.py` + `utils/timescale.py` |
| Quake filtering (mag/depth/text) | `processing/event_filter.py` + `ui/event_filter_bar.py` |
| Inspect what got released | `curl -s https://api.github.com/repos/yiaogit/seismic-shakevision/releases` |
| **Design docs index** | `docs/`: `dashboard-pro.md` · `workbench-restructure.md` · `events-i18n-timezone.md` · `replay-redesign.md` · `roadmap.md` · `ux-review.md` · `audit-0.7.7.md` · `seismic-software-survey.md` |
| **Workbench station/event flow & 2-mode restructure** | **`docs/workbench-restructure.md`** — source of truth for how stations/events route into Live vs Replay; read BEFORE changing `pro_window` / `control_panel` / `replay_panel` station wiring |

---

## 9. Local smoke-test checklist (0.8.3.0)

Run on a real machine with a display + full deps (§5). Baseline used:
macOS 26.6 / arm64, `.venv` on **Python 3.14.3** (off-matrix), PySide6 6.12.0,
numpy 2.5.4, scipy 1.18.1, obspy 1.5.1, pytest 9.1.1; all web assets
downloaded. Harness built the real `MainWindow`, walked every tab, ran a
historical query and rendered both reports.

| # | Check | How | Result |
|---|---|---|---|
| 1 | Package compiles | `.venv/bin/python -m compileall -q shakevision/` | ✅ pass |
| 2 | Full test suite | `.venv/bin/pytest -q` | ✅ **565 passed** in 26.1 s |
| 3 | Lint | `.venv/bin/ruff check .` | ⚠️ ruff **0.17.1 → 576**; ruff **0.12.7 → clean** (CI installs unpinned `ruff>=0.4`) |
| 4 | App launches, splash → MainWindow | `.venv/bin/python -m shakevision` | ✅ (harness built MainWindow directly; splash path not exercised) |
| 5 | 4 top tabs render (Globe/Data/Events/Mine) | visual | ✅ |
| 6 | Globe loads from local `lib/` + quake markers | visual + JS | ✅ WebGL true, Earth + borders + labels + 181 quakes. Software rendering (`--disable-gpu`) → “browser does not support WebGL” |
| 7 | Data ▸ Live charts + region selector | visual + JS | ✅ 9 ECharts instances, KPIs 181 / M5.7 / 21 regions, region combo works |
| 8 | Data ▸ Analysis: JP · 1 y · M≥3 | real query | ✅ 1,369 events, 16 charts, KPIs relabel to “/ 1 y”, b/Mc/energy/depth charts render. ⚠️ over-cap query (20,971) only warns — page keeps the previous **live** charts/KPIs (no analysis empty state) |
| 9 | Event Center: live/historical, filters, nearby stations | visual + Qt introspection | ✅ 10,164 loaded, table capped at 2,000 rows, live/historical switch works. ⚠️ cap notice is overwritten by a language switch; the filter count still says “Showing 10,164 / 10,164” |
| 10 | Pro Workbench opens; panels instantiate | visual | ✅ opens, waveform/spectrogram/heliogram/hodogram built. Live station connection not exercised (needs SeedLink/LAN Shake) |
| 11 | Replay review from an event | end-to-end | ⚠️ not exercised (needs an IRIS dataselect download); panel instantiates |
| 12 | Report export (live + analysis) | generator + WebEngine | ✅ analysis HTML 204 KB / PDF 776 KB with GR + energy SVG + findings; live HTML 29 KB / PDF 259 KB |
| 13 | Language + theme switch live | visual + JS | ✅ Qt UI, web charts, report all follow the switch. ⚠️ light theme: native macOS **document-mode tab bar stays dark** → inactive tabs nearly unreadable (`setDocumentMode(False)` fixes it, verified) |

### Findings from this run (fix candidates, not yet fixed)

1. **Light theme tab bar (macOS).** `QTabWidget.setDocumentMode(True)` uses a
   native strip that ignores the light palette; inactive tab text is
   unreadable. Setting `setDocumentMode(False)` makes it follow QSS (verified).
2. **Analysis page empty state.** Switching to Analysis without a successful
   query (or when `/count` exceeds 20 000) leaves the live KPI row
   (“EARTHQUAKES / 24 H”) and live-derived charts on screen, which reads as
   historical data. Needs an explicit “run a query” empty state.
3. **Live re-translation gaps.** `_retranslate_analysis_bar()` updates labels
   but not the region combos’ item texts or the existing `an_status` text;
   switching to zh leaves “Global (any region)” and the last status in English.
   The `EventListPanel` cap hint is also overwritten by `_update_hint()` on
   retranslate.
4. **Hardcoded Spanish label** `"1 día"` in `build_timeline` bucket labels
   (`dashboard_view.py`), shown in every locale as “(bucket: 1 día)”.
5. **Cache writes are fatal.** `FileCache.set()` propagates `OSError`, so a
   read-only `~/.cache` aborts the whole data load with “Could not load data”.
   Caching should be best-effort (and ideally use a platform cache dir).
6. **Font warning.** QSS asks for `"Inter Variable"` but the bundled `Inter.ttc`
   exposes family `Inter`, so Qt logs a missing-family warning on every start.
7. **Ruff drift.** Unpinned ruff makes CI/lint non-reproducible (see row 3) —
   pin the version or add an explicit `[tool.ruff.lint] select`.

### Sandboxed-agent caveat (not a product issue)

Running this app from inside a sandboxed agent (e.g. this DSH workspace) makes
Chromium’s nested sandbox die with `SIGTRAP` — the globe/dashboard stay blank.
For local smoke tests only, launch with:

```bash
QTWEBENGINE_DISABLE_SANDBOX=1 \
QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox" \
HOME=/tmp/sg_home XDG_CACHE_HOME=/tmp/sg_home/.cache \
.venv/bin/python -m shakevision
```

Normal users / installers are unaffected (no such env vars needed).
