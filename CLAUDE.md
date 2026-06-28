# SeismicGuard — Project Context for Claude

> This file is the entry point any Claude (or Claude Code) agent should
> read first when working on this repo. It encodes the project's
> identity, current state, architecture, conventions, and open work so
> the agent doesn't have to re-derive context from a cold start.

---

## 1. What this is

**SeismicGuard** (formerly **ShakeVision**, renamed in v0.4) is a
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

> ⏭️ **PLANNED NEXT WORK — remind the user at the start of the next session.**
> The user explicitly parked these two for "next conversation":
> 1. **数据板块的验证优化 (Data panel: validate + optimize).** Validate on a real
>    machine all the recent dashboard work that the sandbox can't run — two-mode
>    live/analysis, the analysis date-range selector + `fdsnws/count` pre-check,
>    the pro charts (GR/b · energy · Mc(t) · Omori · cross-section), region
>    display `ISO · name`, event-rate chart — then optimize from findings. Also
>    finish the paused structural pieces: **two truly-independent sub-pages**
>    (实时 | 分析, no shared charts) and the **live-page region selector**
>    (Top-10 stays global) + declutter (drop period-distribution, move depth
>    scatter to analysis). See `docs/dashboard-pro.md`.
> 2. **时间选择器改造 → 现代化拖动选择器 (Time selector → modern draggable range
>    slider).** Replace the calendar/date-edit time pickers with a draggable
>    range slider (brush-style timeline) for choosing the analysis window —
>    more modern/intuitive than from/to calendars.

| Item | Value |
|---|---|
| Current version (4 files, see §5) | **0.8.0.0** (prepared, not yet committed/tagged) |
| Latest tag pushed to origin | `v0.7.6.1` (commit `114ac15`) — `v0.8.0.0` not tagged yet |
| Latest **release with installers** on GitHub Releases | `v0.7.6` (0.7.6.1 / 0.7.7 never shipped artifacts; 0.7.7 work folded into 0.8.0.0) |
| Branch | `main` |
| Python | 3.10 / 3.11 / 3.12 supported (CI matrix) |
| Qt binding | PySide6 |
| i18n keys | **559** per locale (en/es/fr/zh), aligned |

### Known issues / unfinished

1. **`v0.8.0.0` not yet committed/tagged/released.** All 4 version files
   are bumped to 0.8.0.0 and CHANGELOG has the `[0.8.0.0]` section, but the
   release has not been committed or tagged. Follow §5 to commit + tag +
   push. (The old `v0.7.6.1`-missing-artifacts problem is now moot — that
   version was superseded; if the publish job ever skips again, the fix is
   still delete+re-push the tag.)
2. *(resolved 0.8.0)* The orphan `shakevision/ui/local_data_panel.py`
   (superseded by `my_data_panel.py`) has been **deleted**. No references
   remain anywhere (verified by grep).
3. **No auto-update mechanism.** Users must manually download new
   installers from the GitHub Releases page. (Tracked for v1.0.0.)
4. **GUI/obspy tests can't run in the assistant's sandbox** (no libEGL,
   no obspy) — pure tests (i18n/measurements/recordings_list/response)
   pass there; full GUI suite must be validated on a real machine / CI.
5. **i18n locales hold 2 intentionally-unused keys** (`common.cancel`,
   `profile.tab_title`): the app doesn't call them but the test suite
   asserts them as locale contract — the dead-key scan must include
   `tests/`, not just `shakevision/` + web JS. All 4 locales remain
   aligned (same 559 keys, same placeholders).

---

## 3. Architecture

```
ShakeVision/
├─ shakevision/                  ← Python package
│  ├─ __main__.py                ← App entry point; SSL/certifi bootstrap,
│  │                                ThemeManager.init, splash → MainWindow
│  ├─ __init__.py                ← __version__, APP_NAME ("SeismicGuard")
│  │
│  ├─ ui/                        ← All Qt widgets / windows (30+ files)
│  │  ├─ main_window.py          ← The shell; sidebar + QStackedWidget
│  │  ├─ pro_window.py           ← Standalone "Workbench" window
│  │  ├─ app_header.py           ← Top bar: theme cycle, layer toggle, gear
│  │  ├─ sidebar_nav.py          ← Left vertical nav (Globe/Data/Profile)
│  │  ├─ globe_view.py           ← QWebEngineView wrapping ECharts-GL globe
│  │  ├─ dashboard_view.py       ← QWebEngineView wrapping 7-chart dashboard
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
│  │  ├─ spectrum.py             ← Sliding-window FFT (scipy.signal.spectrogram)
│  │  ├─ recorder.py             ← Save events to MiniSEED on trigger
│  │  ├─ sonifier.py             ← Samples → audio bytes
│  │  ├─ intensity.py            ← MMI translation (magnitude/distance → MMI)
│  │  └─ measurements.py         ← ZNE→ZRT rotate · polarization azimuth · Welch PSD · great-circle distance (pure, tested, v0.8.0)
│  │
│  ├─ web/                       ← HTML/JS/CSS bundled with the app
│  │  ├─ globe/                  ← ECharts-GL 3D globe (Blue Marble, Black Marble, holo)
│  │  ├─ dashboard/              ← 7 ECharts charts (KPI/Top-10/timeline/PAGER…)
│  │  └─ report/                 ← Report HTML template + CSS
│  │
│  ├─ i18n/                      ← Locale system
│  │  ├─ locale_service.py       ← Runtime t() + LocaleService singleton + language_changed
│  │  └─ locales/{en,es,fr,zh}.json
│  │
│  ├─ utils/logging.py           ← Centralized logger
│  └─ assets/                    ← Fonts (Inter, JetBrains Mono), branding logos,
│                                  app icons (.ico/.icns/.png), Blue Marble textures
│
├─ tests/                        ← pytest suite (45 files, ~430 tests)
├─ packaging/                    ← PyInstaller spec + Windows version_info
│  ├─ shakevision.spec
│  └─ windows/version_info.txt
├─ scripts/                      ← Dev helpers (CI install_libs.sh, download textures…)
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
# Run from source (dev)
pip install -e .[dev]
python -m shakevision

# Tests
pytest -q                                  # full suite (PySide6 required)
pytest tests/test_onboarding_wizard.py -v  # one file
ruff check .                               # lint

# Compile-only sanity (no runtime)
python -m compileall -q shakevision/

# Build local installer (requires PyInstaller, slow ~10-20 min)
pyinstaller packaging/shakevision.spec

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
8. **Releasing**: see §5. Don't forget to bump all FOUR version files,
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
| Inspect what got released | `curl -s https://api.github.com/repos/yiaogit/seismic-shakevision/releases` |
| **Workbench station/event flow & 2-mode restructure** | **`docs/workbench-restructure.md`** — source of truth for how stations/events route into Live vs Replay; read BEFORE changing `pro_window` / `control_panel` / `replay_panel` station wiring |
