<div align="center">

# 🌐 SeismicGuard

**简体中文** · [English](README.en.md) · [Español](README.es.md) · [Français](README.fr.md)

> 原名 **ShakeVision OpenData Monitor**。v0.7.0 完成 SeismicGuard 品牌重塑、
> macOS Sonoma 风格主题、全栈 4 语言 i18n、Onboarding 引导、Profile 活动时间线、
> IP 地理定位等大量改进。历史的 v0.1.x 二进制仍以 `ShakeVision-*` 名字保留在
> Releases 页面。

**桌面级开源地震监测可视化工作站**
*Cross-platform desktop seismic monitoring workbench*

实时拉取全球公民地震网（Raspberry Shake）+ USGS / IRIS 专业台网数据，
融合 3D 地球 · 数据看板 · 波形/频谱/触发分析于一体的单体桌面应用。

[![CI](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml)
[![Release](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platform-windows%20%7C%20macos%20arm64%20%7C%20linux-lightgrey)](https://github.com/yiaogit/seismic-shakevision/releases/latest)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20ES%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20FR-brightgreen)](shakevision/i18n/locales/)

[**下载安装包**](#-下载安装) · [**从源码运行**](#-从源码运行) · [**功能速览**](#-功能速览) · [**架构**](#-架构) · [**发布流程**](#-发布流程)

</div>

---

## ✨ 功能速览

| 模块                       | 内容                                                                                                                            |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| 🌍 **3D Globe**           | ECharts-GL 实时渲染地球，叠加 600+ Raspberry Shake 公民台站 + 400+ USGS / IRIS 骨干台站，地震按震级分色，可点击缩放并加入 Pro 工作台 |
| 📊 **Data Dashboard**     | 7 张联动 ECharts：Top 国家、震级/深度直方图、24h 时间线（自适应密度气泡）、PAGER 雷达（区域过滤器）、周期自适应桶图、深度×震级散点  |
| 🔬 **Pro Workbench**      | 独立浮窗：实时三通道波形 + 频谱图 + 24h 鼓式记录 + N-E 质点轨迹 + STA/LTA 触发录波 + MMI 烈度卡                                  |
| 🔊 **Sonification**       | 把最近 60 秒的地动信号变速并播放成可听音频（1× – 60×）                                                                            |
| 🌐 **i18n**               | 全栈 4 语言（EN / ES / 简中 / FR）即时切换，包括 Web 视图、图表内部、tooltip、HTML 报告                                          |
| 🕒 **Timezone-aware**     | 系统时区自动检测 + 手动覆盖；所有时间戳一致显示用户时区                                                                          |
| 📄 **Reports**            | 一键导出单文件 HTML 报告（含 SVG 时间线）+ PDF 导出（QWebEngine printToPdf）                                                     |
| ⚡ **Live SeedLink**      | 直连 IRIS `rtserve.iris.washington.edu:18000`，IU/US/II/IC 网络自动路由，分阶段连接状态显示，可随时取消                          |

---

## 📦 下载安装

> **推荐普通用户走这条路。** 二进制由 GitHub Actions 在每个 tag 上自动构建，
> SHA-256 校验和也由 Actions 自动写入 Release。

最新版本在 → **[Latest Release](https://github.com/yiaogit/seismic-shakevision/releases/latest)**

| 平台                              | 下载文件                                       | 安装方式                                              |
|-----------------------------------|------------------------------------------------|-------------------------------------------------------|
| 🪟 **Windows 10 / 11 x64**        | `ShakeVision-X.Y.Z-windows-x64.zip`            | 解压 → 双击 `ShakeVision.exe`（**首次**会触发 SmartScreen，见下） |
| 🍎 **macOS Apple Silicon (M1–M5)**| `ShakeVision-X.Y.Z-macos-arm64.dmg`            | 打开 DMG → 拖入 `/Applications` → 首次右键 → 打开                |
| 🐧 **Linux x64**                  | `ShakeVision-X.Y.Z-linux-x64.AppImage`         | `chmod +x ShakeVision-*.AppImage` → 双击                          |

#### 🛡 Windows SmartScreen / macOS Gatekeeper 首次启动须知

ShakeVision 当前**未做代码签名**（EV 证书约 $300/年；列入 v1.0 路线图）。
因此首次启动时操作系统会拦截：

<details>
<summary><b>🪟 Windows — "Windows protected your PC"</b></summary>

下载完 ZIP 解压后双击 `ShakeVision.exe`，会看到蓝色弹窗：

```
Windows protected your PC
Microsoft Defender SmartScreen prevented an unrecognized app from starting.
```

操作：

1. 点弹窗里的 **"More info"**（左下角小字）
2. 弹窗展开后出现 **"Run anyway"** 按钮 —— 点它
3. 之后再启动就不会再问

> 这一步只需做一次。SmartScreen 在你的本地建立信任后，下次直接打开。
> 如果你不愿点 "Run anyway"，可以从源码运行（见 [从源码运行](#-从源码运行)）。

</details>

<details>
<summary><b>🍎 macOS — "ShakeVision can't be opened because Apple cannot check it for malicious software"</b></summary>

把 `.app` 拖到 `/Applications` 后第一次启动时，会被 Gatekeeper 拦下。操作：

1. **不要** 双击启动；改为 **右键（或按住 Control + 点击）** `ShakeVision.app`
2. 选择菜单里的 **"Open"**
3. 弹窗里再点 **"Open"** 确认
4. 之后正常双击即可

</details>

> 🍎 **Intel Mac 用户**：不再发布 Intel 二进制（M1+ 已主导市场超过 4 年）。
> 请按 [从源码运行](#-从源码运行) 部分本地构建。

校验和检查（可选）：

```bash
# 在 Release 页面下载 SHA256SUMS.txt 后
sha256sum -c SHA256SUMS.txt        # Linux
shasum -a 256 -c SHA256SUMS.txt    # macOS
certutil -hashfile <file> SHA256   # Windows PowerShell
```

---

## 💻 从源码运行

适合开发者、Intel Mac 用户，以及想做二次开发或 PR 的同学。

### 前置依赖

| 系统      | 必需                                                                                              |
|-----------|---------------------------------------------------------------------------------------------------|
| 所有平台  | Python ≥ 3.10（推荐 3.11 / 3.12）+ Git                                                            |
| **Linux** | `libegl1 libxkbcommon0 libxcb-cursor0 libxcb-icccm4 libgl1 libdbus-1-3`（Ubuntu/Debian `apt install`） |
| **macOS** | Xcode Command Line Tools（`xcode-select --install`）                                              |
| **Windows** | Visual C++ Redistributable（pip 装 PySide6 时通常已自带）                                       |

### 一键启动

```bash
# 1) 克隆 + 进入
git clone https://github.com/yiaogit/seismic-shakevision.git
cd seismic-shakevision

# 2) 虚拟环境 + 安装（含开发依赖）
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"

# 3) 一次性资源下载（≈10 MB：ECharts + 字体 + 地球纹理）
bash scripts/install_libs.sh
bash scripts/install_fonts.sh

# 4) 启动
python -m shakevision
```

> 🪟 Windows 上 step 3 用 Git Bash / WSL 运行 bash 脚本即可；或手动下载脚本里列的 URL 到对应目录。
> 🍎 macOS 用户可选 `pip install -e ".[macos]"` 装 pyobjc 享受透明标题栏。

---

## 🚀 快速上手

```
启动 → 默认进入 🌍 Globe 视图
  ├── 点击任意 USGS 光点 → 弹窗"添加到 Pro?" → ✅ → 浮现在 Pro 控制面板下拉
  ├── 切换 📊 Data → 查看 7 张联动图表 + 周期 / 区域过滤
  └── 右上 🔬 Pro → 打开独立的专业窗口
                    ├── 选刚才加入的 USGS 台站
                    ├── 点 Connect → 走 SeedLink 实时流
                    └── 看实时波形 / 频谱 / 鼓式记录 / 质点轨迹

右上 ⚙ Settings → 切语言 + 时区，立即生效，无需重启
```

---

## 🏗 架构

### 数据流

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ USGS GeoJSON │ ──► │   Worker     │ ──► │  data_models │ ──► │   Globe      │
│ IRIS FDSN    │     │ (单线程异步) │     │ (Earthquake, │     │ Dashboard    │
│ ShakeNet     │     │              │     │  Station…)   │     │ (HTML + JS)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  SeedLink    │ ──► │  RingBuffer  │ ──► │  Processor   │ ──► │  Pro 浮窗    │
│ rtserve.iris │     │ (线程安全)   │     │ Butterworth, │     │  Waveform +  │
│  → ObsPy     │     │              │     │ STA/LTA, FFT │     │  Spec + Hel  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### 技术栈

| 层               | 选型                                                | 理由                                              |
|------------------|-----------------------------------------------------|---------------------------------------------------|
| **UI 框架**      | PySide6 ≥ 6.6                                       | LGPL，跨平台原生外观，QtWebEngine 自带 Chromium    |
| **Web 渲染**     | QWebEngineView                                      | 嵌入 ECharts，不引第三方浏览器引擎                 |
| **3D 地球**      | [ECharts-GL](https://github.com/ecomfe/echarts-gl)  | 单一图表库覆盖 2D + 3D，bundle 比 Three.js 小      |
| **2D 图表**      | [Apache ECharts](https://echarts.apache.org/) 5.4   | 7 种图表全用同一引擎                              |
| **DSP**          | NumPy + SciPy                                       | 工业标准 Butterworth 滤波 / FFT 谱图              |
| **地震学**       | [ObsPy](https://www.obspy.org/) ≥ 1.4               | SeedLink 客户端 + MiniSEED 读写                   |
| **波形绘制**     | [pyqtgraph](https://www.pyqtgraph.org/) 0.13        | 60 FPS GPU 加速                                   |
| **音频**         | QtMultimedia QAudioSink                             | 跨平台，零额外依赖                                |
| **时区**         | `zoneinfo`（Win 上 + `tzdata` pip 包）              | 标准库；POSIX `/etc/localtime` symlink 自动检测   |
| **i18n**         | 自研 JSON dict + `t()` 函数                          | Python 与 JS 共享同一份字典，无构建步骤          |
| **打包**         | PyInstaller (onedir) + `create-dmg` + `appimagetool` | 跨平台一致；onedir 启动快，杀软友好               |
| **CI / Release** | GitHub Actions                                      | 3 平台矩阵 + tag 触发自动发布                     |

### 项目结构

```
seismic-shakevision/
├── shakevision/              # ── 主包 ──
│   ├── __main__.py           # 入口（python -m shakevision）
│   ├── config.py             # SeedLink 服务器注册表 + 默认台站
│   ├── sources/              # DataSource 抽象 + Mock / SeedLink
│   ├── processing/           # RingBuffer / Filters / Detector / Spectrum / Recorder / Intensity / Sonifier
│   ├── services/             # USGS / IRIS / ShakeNet 客户端 + Worker + Report + Timezone
│   ├── ui/                   # PySide6 主窗口 + 浮窗 + 各 widget + Settings + LoadingOverlay
│   ├── i18n/                 # LocaleService + 4 份对齐字典（each 260 keys）
│   ├── web/{globe,dashboard,report}/   # 嵌入式 HTML/JS/CSS
│   └── assets/{fonts,icons}/ # 字体（脚本下载，不入仓）
│
├── tests/                    # pytest 单元 + 集成（30+ 模块）
├── packaging/                # ⭐ PyInstaller spec + 跨平台 build.py + 平台资源
│   ├── shakevision.spec
│   ├── build.py
│   └── README.md             # 打包深度说明
├── scripts/                  # install_libs.sh / install_fonts.sh
├── .github/workflows/        # ci.yml（每次 push） + release.yml（tag 触发）
├── CHANGELOG.md
├── pyproject.toml
└── README.md
```

---

## 🛠 开发与测试

```bash
# 运行测试套件
pytest -v

# Lint
ruff check shakevision tests

# 字节码编译检查
python -m compileall -q shakevision tests
```

CI 在每次 push / PR 跑：Ubuntu / macOS / Windows × Python 3.10 / 3.11 / 3.12 ×
（ruff + pytest）。Linux 用 `xvfb-run`，macOS / Windows 用 `QT_QPA_PLATFORM=offscreen`。

---

## 🌐 i18n 翻译贡献

字典在 `shakevision/i18n/locales/*.json`（each ≈260 keys，4 语言对齐）。

**加新语言**：

1. 复制 `en.json` → 新文件，如 `ja.json` / `de.json`
2. 翻译每个 value（不要改 key）
3. 在 `shakevision/i18n/service.py` 的 `SUPPORTED_LANGUAGES` + `LANGUAGE_LABELS` 注册
4. PR

---

## 🚢 发布流程

> 维护者用。每次发新版照这个流程走。

### 一次性准备（已就位，跳过）

- ✅ `packaging/shakevision.spec` — PyInstaller spec
- ✅ `packaging/build.py` — 跨平台驱动
- ✅ `.github/workflows/release.yml` — tag 触发自动构建 + 发布

### 发版步骤（以 v0.1.1 为例）

```bash
# 1) bump 三处版本号一致
#    a. shakevision/__init__.py    →  __version__ = "0.1.1"
#    b. pyproject.toml              →  version = "0.1.1"
#    c. packaging/shakevision.spec  →  version = "0.1.1"  (BUNDLE)

# 2) 写 CHANGELOG.md：在最上面加 ## [0.1.1] — YYYY-MM-DD 区块
#    workflow 会自动从中抽取作为 Release 描述。

# 3) 提交 + 推
git add -A
git commit -m "release: v0.1.1"
git push origin main

# 4) 打 tag + 推 tag → 触发 release workflow
git tag -a v0.1.1 -m "ShakeVision v0.1.1 — binary installers"
git push origin v0.1.1
```

推完 tag 后，GitHub Actions 自动执行：

```
release.yml (tag v0.1.1)
  ├── build-windows  (windows-latest, Py 3.11)      → ShakeVision-0.1.1-windows-x64.zip
  ├── build-macos    (macos-14 / Apple Silicon)     → ShakeVision-0.1.1-macos-arm64.dmg
  ├── build-linux    (ubuntu-22.04)                 → ShakeVision-0.1.1-linux-x64.AppImage
  └── publish        (拉取 3 个 artifacts)
       ├── 从 CHANGELOG.md 抽取 [0.1.1] 区块作为 release notes
       ├── 拼接 SHA256SUMS.txt
       └── 在 GitHub Releases 创建 release，3 个二进制 + checksums 全部挂上
```

约 15–25 分钟后在 https://github.com/yiaogit/seismic-shakevision/releases 出现 **v0.1.1**。

### 预发布（rc / beta）

tag 加 `-rc1` / `-beta` / `-alpha` / `-dev` / `-pre` 后缀，publish job 自动标记 `prerelease: true`：

```bash
git tag -a v0.2.0-rc1 -m "v0.2.0 release candidate 1"
git push origin v0.2.0-rc1
```

### 出问题需要重发

```bash
# 删远端 tag（同时撤销 Release，需在 GitHub UI 也删一下 Release）
git push --delete origin v0.1.1
git tag -d v0.1.1
# 修代码、重新打 tag、推
git tag -a v0.1.1 -m "..."
git push origin v0.1.1
```

详细打包说明（本地构建、双架构 macOS 注意事项、tamaños 等）见 [`packaging/README.md`](packaging/README.md)。

---

## 🗺 路线图

- [x] **v0.1.0** — 全功能源码版（i18n + 时区 + Pro 浮窗 + 设置面板）
- [x] **v0.1.1** — 二进制安装包（Windows `.zip` + macOS arm64 `.dmg` + Linux `.AppImage`）
- [x] **v0.2.0** — 历史回放：从 IRIS FDSN dataselect 下载 MiniSEED，可调速度回放
- [x] **v0.3.0** — 自定义 LAN Raspberry Shake 连接 UI（下拉 "➕ Add LAN Shake…" + Settings "My Shakes" 标签页）
- [ ] **v0.4.0** — 主题切换（亮色 / 高对比度）
- [ ] **v1.0.0** — 代码签名（Windows EV cert + macOS Developer ID + 公证）；彻底移除 SmartScreen / Gatekeeper 警告

---

## 📜 数据来源

- 🍓 [Raspberry Shake](https://raspberryshake.org/) — 公民地震学网络，开放数据 CC-BY
- 🇺🇸 [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/) — 地震 GeoJSON Feed
- 🌍 [IRIS DMC](https://ds.iris.edu/) — 专业台网元数据 + SeedLink 实时流（`rtserve.iris.washington.edu`）

> ⚠ **Raspberry Shake 公开 SeedLink 服务器不存在**。只能连本地 LAN 内自己的设备（`rs.local:18000`）
> 或付费 RTDC 订阅。详见 `shakevision/config.py` 中的 `SEEDLINK_SERVERS` 注册表。

---

## 🤝 贡献

欢迎 Issue / PR。代码注释使用西班牙语（项目历史约定），用户面对的字符串通过 i18n 系统外化。
提交前请跑：

```bash
ruff check shakevision tests
pytest -v
```

CI 通过后才会合并。

---

## 📄 License

[MIT License](LICENSE) © 2025 Yiao

---

## 🙏 致谢

感谢 [Raspberry Shake](https://raspberryshake.org/) 社区与 [ObsPy](https://www.obspy.org/) 项目提供的开源地震学工具链；
致敬全球公民科学家在地震监测领域的持续贡献。
