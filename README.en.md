<div align="center">

# 🌐 SeismicGuard

[简体中文](README.md) · **English** · [Español](README.es.md) · [Français](README.fr.md)

> Formerly **ShakeVision OpenData Monitor**. v0.7.0 ships the SeismicGuard
> rebrand, a macOS-Sonoma-style theming overhaul, full 4-language i18n,
> an onboarding wizard, a Profile activity timeline, IP-based location
> detection, and many quality-of-life improvements. The original v0.1.x
> binaries remain available on the Releases page under the legacy
> `ShakeVision-*` name.

**Open-source desktop seismic monitoring workstation**
*Cross-platform desktop seismic monitoring workbench*

Pulls real-time data from the global citizen seismic network
(Raspberry Shake) plus professional networks (USGS / IRIS), and fuses
a 3D globe · data dashboard · waveform / spectrogram / trigger
analysis into a single desktop app.

[![CI](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml)
[![Release](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platform-windows%20%7C%20macos%20arm64%20%7C%20linux-lightgrey)](https://github.com/yiaogit/seismic-shakevision/releases/latest)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20ES%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20FR-brightgreen)](shakevision/i18n/locales/)

[**Download installers**](#-download) · [**Run from source**](#-run-from-source) · [**Features**](#-features) · [**Architecture**](#-architecture) · [**Release flow**](#-release-flow)

</div>

---

## ✨ Features

| Module                     | What it does                                                                                                                       |
|----------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| 🌍 **3D Globe**            | ECharts-GL real-time Earth rendering, 600+ Raspberry Shake citizen stations + 400+ USGS / IRIS backbone stations, magnitude-coloured quakes, click-to-zoom + add to Pro workbench |
| 📊 **Data Dashboard**      | 7 linked ECharts: top countries, magnitude / depth histograms, 24h timeline (density bubbles), PAGER radar (region filter), period-adaptive buckets, depth × magnitude scatter |
| 🔬 **Pro Workbench**       | Floating window: 3-channel waveform + spectrogram + 24h helicorder + N-E particle motion + STA/LTA triggered recording + MMI intensity card |
| 🔊 **Sonification**        | Play the last 60 seconds of ground motion as audible audio at 1× – 60× speed                                                       |
| 🌐 **i18n**                | Full 4-language stack (EN / ES / 简中 / FR) with instant switching, including web views, chart internals, tooltips, HTML reports   |
| 🕒 **Timezone-aware**      | System timezone auto-detect + manual override; all timestamps render consistently in the user's zone                               |
| 📄 **Reports**             | One-click export to single-file HTML report (with SVG timeline) + PDF export via QWebEngine `printToPdf`                           |
| ⚡ **Live SeedLink**       | Direct connect to IRIS `rtserve.iris.washington.edu:18000`, IU/US/II/IC network auto-routing, staged connection status, cancellable at any time |
| 👤 **Profile**             | GitHub OAuth (Device Flow), usage stats, **recent activity timeline** (last 50 events with relative timestamps, stored locally)    |
| 📍 **Location**            | IP-based geolocation (one-click, never background) suggests nearest stations and updates timezone                                  |

---

## 📦 Download

> **Recommended for end users.** Binaries are built by GitHub Actions on
> every tag; SHA-256 checksums are uploaded automatically too.

Latest release → **[Latest Release](https://github.com/yiaogit/seismic-shakevision/releases/latest)**

| Platform                              | Asset                                          | How to install                                              |
|---------------------------------------|------------------------------------------------|-------------------------------------------------------------|
| 🪟 **Windows 10 / 11 x64**            | `ShakeVision-X.Y.Z-windows-x64.zip`            | Unzip → double-click `ShakeVision.exe` (SmartScreen on first run, see below) |
| 🍎 **macOS Apple Silicon (M1–M5)**    | `ShakeVision-X.Y.Z-macos-arm64.dmg`            | Open DMG → drag to `/Applications` → first time right-click → Open          |
| 🐧 **Linux x64**                      | `ShakeVision-X.Y.Z-linux-x64.AppImage`         | `chmod +x ShakeVision-*.AppImage` → double-click                            |

#### 🛡 First-launch notes (Windows SmartScreen / macOS Gatekeeper)

SeismicGuard is **not code-signed** yet (EV cert ≈ $300/year — planned for
v1.0). The OS will warn on first launch:

<details>
<summary><b>🪟 Windows — "Windows protected your PC"</b></summary>

After unzipping and double-clicking `ShakeVision.exe`, a blue dialog
appears:

```
Windows protected your PC
Microsoft Defender SmartScreen prevented an unrecognized app from starting.
```

What to do:

1. Click **"More info"** (small link, bottom-left of the dialog)
2. A **"Run anyway"** button appears — click it
3. Subsequent launches don't ask again

> One-time only. Once SmartScreen trusts your local copy, it stays out
> of the way. If you'd rather not click "Run anyway", run from source
> (see [Run from source](#-run-from-source)).

</details>

<details>
<summary><b>🍎 macOS — "ShakeVision can't be opened because Apple cannot check it for malicious software"</b></summary>

After dragging the `.app` into `/Applications`, the first launch is
blocked by Gatekeeper:

1. **Don't** double-click; instead **right-click (or Ctrl-click)**
   `ShakeVision.app`
2. Choose **"Open"** from the menu
3. Confirm **"Open"** again in the dialog
4. From then on, double-click works normally

</details>

> 🍎 **Intel Mac users**: Intel binaries are no longer published (Apple
> Silicon has been mainstream for 4+ years). Build locally — see
> [Run from source](#-run-from-source).

Optional checksum verification:

```bash
# After downloading SHA256SUMS.txt from the release page
sha256sum -c SHA256SUMS.txt        # Linux
shasum -a 256 -c SHA256SUMS.txt    # macOS
certutil -hashfile <file> SHA256   # Windows PowerShell
```

---

## 💻 Run from source

For developers, Intel Mac users, and anyone wanting to contribute.

### Prerequisites

| OS         | Required                                                                                                |
|------------|---------------------------------------------------------------------------------------------------------|
| All        | Python ≥ 3.10 (3.11 / 3.12 recommended) + Git                                                           |
| **Linux**  | `libegl1 libxkbcommon0 libxcb-cursor0 libxcb-icccm4 libgl1 libdbus-1-3` (Ubuntu/Debian `apt install`)   |
| **macOS**  | Xcode Command Line Tools (`xcode-select --install`)                                                     |
| **Windows**| Visual C++ Redistributable (usually bundled with pip-installed PySide6)                                 |

### One-shot setup

```bash
# 1) Clone + enter
git clone https://github.com/yiaogit/seismic-shakevision.git
cd seismic-shakevision

# 2) Virtual env + install (incl. dev extras)
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"

# 3) One-time asset download (~10 MB: ECharts + fonts + Earth textures)
bash scripts/install_libs.sh
bash scripts/install_fonts.sh

# 4) Launch
python -m shakevision
```

> 🪟 On Windows, run step 3 in Git Bash / WSL, or manually download the
> URLs listed in the script into the corresponding folders.
> 🍎 macOS users: `pip install -e ".[macos]"` adds pyobjc for the
> translucent title bar.

---

## 🚀 Quick start

```
Launch → defaults to the 🌍 Globe view
  ├── Click any USGS dot → "Add to Pro?" prompt → ✅ → appears in Pro panel
  ├── Switch to 📊 Data → 7 linked charts + period / region filters
  └── Top-right 🔬 Pro → opens the standalone professional window
                          ├── Pick the USGS station you just added
                          ├── Click Connect → live SeedLink stream
                          └── Watch real-time waveform / spectrogram / helicorder / particle motion

Top-right ⚙ Settings → switch language + timezone, applied instantly, no restart
Top-right 👤 Profile → identity card + usage stats + recent activity timeline
```

---

## 🏗 Architecture

### Data flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ USGS GeoJSON │ ──► │   Worker     │ ──► │  data_models │ ──► │   Globe      │
│ IRIS FDSN    │     │ (async      )│     │ (Earthquake, │     │ Dashboard    │
│ ShakeNet     │     │   single-thr)│     │  Station…)   │     │ (HTML + JS)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  SeedLink    │ ──► │  RingBuffer  │ ──► │  Processor   │ ──► │  Pro window  │
│ rtserve.iris │     │ (thread-safe)│     │ Butterworth, │     │  Waveform +  │
│  → ObsPy     │     │              │     │ STA/LTA, FFT │     │  Spec + Hel  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Tech stack

| Layer            | Choice                                              | Rationale                                          |
|------------------|-----------------------------------------------------|----------------------------------------------------|
| **UI framework** | PySide6 ≥ 6.6                                       | LGPL, native cross-platform look, QtWebEngine ships Chromium |
| **Web render**   | QWebEngineView                                      | Embed ECharts without pulling a third-party browser engine |
| **3D Earth**     | [ECharts-GL](https://github.com/ecomfe/echarts-gl)  | One chart lib covers 2D + 3D, smaller bundle than Three.js  |
| **2D charts**    | [Apache ECharts](https://echarts.apache.org/) 5.4   | All 7 charts share the same engine                          |
| **DSP**          | NumPy + SciPy                                       | Industry-standard Butterworth filtering + FFT spectrogram   |
| **Seismology**   | [ObsPy](https://www.obspy.org/) ≥ 1.4               | SeedLink client + MiniSEED read/write                       |
| **Waveform**     | [pyqtgraph](https://www.pyqtgraph.org/) 0.13        | 60 FPS GPU-accelerated                                      |
| **Audio**        | QtMultimedia QAudioSink                             | Cross-platform, zero extra dependencies                     |
| **Timezone**     | `zoneinfo` (+ `tzdata` pip on Windows)              | Stdlib; POSIX `/etc/localtime` symlink auto-detect          |
| **i18n**         | In-house JSON dict + `t()` helper                   | Python and JS share one dictionary, no build step           |
| **Packaging**    | PyInstaller (onedir) + `create-dmg` + `appimagetool` | Consistent across platforms; onedir starts fast, antivirus-friendly |
| **CI / Release** | GitHub Actions                                      | 3-platform matrix + tag-triggered auto-publish              |

### Project layout

```
seismic-shakevision/
├── shakevision/              # ── main package ──
│   ├── __main__.py           # entry (python -m shakevision)
│   ├── config.py             # SeedLink server registry + default stations
│   ├── sources/              # DataSource abstract + Mock / SeedLink
│   ├── processing/           # RingBuffer / Filters / Detector / Spectrum / Recorder / Intensity / Sonifier
│   ├── services/             # USGS / IRIS / ShakeNet clients + Worker + Report + Timezone + ActivityLog + Location + ClearCache
│   ├── ui/                   # PySide6 main window + floating panels + widgets + Settings + Profile + Onboarding
│   ├── i18n/                 # LocaleService + 4 aligned dictionaries (435 keys each)
│   ├── web/{globe,dashboard,report}/   # embedded HTML/JS/CSS
│   └── assets/{fonts,icons}/ # fonts (downloaded by script, not in repo)
│
├── tests/                    # pytest unit + integration (40+ modules)
├── packaging/                # ⭐ PyInstaller spec + cross-platform build.py
├── scripts/                  # install_libs.sh / install_fonts.sh / download_globe_assets.py
├── .github/workflows/        # ci.yml (every push) + release.yml (tag triggered)
├── CHANGELOG.md
├── pyproject.toml
└── README.md                 # this file (plus README.en.md / README.es.md / README.fr.md)
```

---

## 🛠 Development & testing

```bash
# Run the test suite
pytest -v

# Lint
ruff check shakevision tests

# Bytecode compile sanity check
python -m compileall -q shakevision tests
```

CI runs on every push / PR: Ubuntu / macOS / Windows × Python 3.10 / 3.11 / 3.12
× (ruff + pytest). Linux uses `xvfb-run`; macOS / Windows use
`QT_QPA_PLATFORM=offscreen`.

---

## 🌐 i18n contributions

Dictionaries live in `shakevision/i18n/locales/*.json` (≈ 435 keys each,
all 4 languages aligned at 100 %).

**Adding a new language**:

1. Copy `en.json` to a new file, e.g. `ja.json` / `de.json`
2. Translate every value (do not change keys)
3. Register in `shakevision/i18n/service.py` under
   `SUPPORTED_LANGUAGES` + `LANGUAGE_LABELS`
4. Open a PR

---

## 🚢 Release flow

> Maintainer-only. Follow this every release.

### One-time setup (already in place — skip)

- ✅ `packaging/shakevision.spec` — PyInstaller spec
- ✅ `packaging/build.py` — cross-platform driver
- ✅ `.github/workflows/release.yml` — tag-triggered auto build + publish

### Release steps (using v0.1.1 as an example)

```bash
# 1) Bump the three version numbers consistently
#    a. shakevision/__init__.py    →  __version__ = "0.1.1"
#    b. pyproject.toml              →  version = "0.1.1"
#    c. packaging/shakevision.spec  →  version = "0.1.1"  (BUNDLE)

# 2) Update CHANGELOG.md: prepend a ## [0.1.1] — YYYY-MM-DD section
#    The workflow extracts it automatically as the release notes.

# 3) Commit + push
git add -A
git commit -m "release: v0.1.1"
git push origin main

# 4) Tag + push tag → triggers the release workflow
git tag -a v0.1.1 -m "ShakeVision v0.1.1 — binary installers"
git push origin v0.1.1
```

After pushing the tag, GitHub Actions runs:

```
release.yml (tag v0.1.1)
  ├── build-windows  (windows-latest, Py 3.11)      → ShakeVision-0.1.1-windows-x64.zip
  ├── build-macos    (macos-14 / Apple Silicon)     → ShakeVision-0.1.1-macos-arm64.dmg
  ├── build-linux    (ubuntu-22.04)                 → ShakeVision-0.1.1-linux-x64.AppImage
  └── publish        (pulls all 3 artifacts)
       ├── extracts the [0.1.1] section from CHANGELOG.md as release notes
       ├── assembles SHA256SUMS.txt
       └── creates a GitHub Release with all 3 binaries + checksums
```

About 15–25 minutes later, **v0.1.1** appears at
https://github.com/yiaogit/seismic-shakevision/releases.

### Pre-releases (rc / beta)

Tag suffixes `-rc1` / `-beta` / `-alpha` / `-dev` / `-pre` mark the
publish job's `prerelease: true`:

```bash
git tag -a v0.2.0-rc1 -m "v0.2.0 release candidate 1"
git push origin v0.2.0-rc1
```

### Recovering from a bad release

```bash
# Delete the remote tag (also delete the Release in the GitHub UI)
git push --delete origin v0.1.1
git tag -d v0.1.1
# Fix code, retag, push
git tag -a v0.1.1 -m "..."
git push origin v0.1.1
```

Full packaging details (local builds, dual-architecture macOS caveats,
sizes, etc.) live in [`packaging/README.md`](packaging/README.md).

---

## 🗺 Roadmap

- [x] **v0.1.0** — full source release (i18n + timezone + Pro window + Settings)
- [x] **v0.1.1** — binary installers (Windows `.zip` + macOS arm64 `.dmg` + Linux `.AppImage`)
- [x] **v0.2.0** — historical replay: download MiniSEED from IRIS FDSN dataselect with adjustable speed
- [x] **v0.3.0** — custom LAN Raspberry Shake UI ("➕ Add LAN Shake…" dropdown + "My Shakes" tab in Settings)
- [x] **v0.7.0** — rebrand to SeismicGuard, macOS-Sonoma theming, onboarding wizard, profile + activity timeline, IP geolocation, PDF overflow fix
- [ ] **v0.8.0** — globe favourite-quake UX (button-based, replacing the postponed right-click attempt)
- [ ] **v1.0.0** — code signing (Windows EV cert + macOS Developer ID + notarisation); eliminate SmartScreen / Gatekeeper warnings entirely

---

## 📜 Data sources

- 🍓 [Raspberry Shake](https://raspberryshake.org/) — citizen seismology network, open data CC-BY
- 🇺🇸 [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/) — earthquake GeoJSON feed
- 🌍 [IRIS DMC](https://ds.iris.edu/) — professional network metadata + live SeedLink stream (`rtserve.iris.washington.edu`)

> ⚠ **No public Raspberry Shake SeedLink server exists.** You can only
> connect to your own LAN device (`rs.local:18000`) or a paid RTDC
> subscription. See `SEEDLINK_SERVERS` in `shakevision/config.py`.

---

## 🤝 Contributing

Issues and PRs welcome. Code comments are in Spanish (project history);
user-facing strings are externalised through the i18n system. Before
submitting, please run:

```bash
ruff check shakevision tests
pytest -v
```

CI must pass before merge.

---

## 📄 License

[MIT License](LICENSE) © 2025 Yiao

---

## 🙏 Acknowledgements

Thanks to the [Raspberry Shake](https://raspberryshake.org/) community
and the [ObsPy](https://www.obspy.org/) project for the open-source
seismology toolchain; and to citizen scientists worldwide for their
ongoing contributions to earthquake monitoring.
