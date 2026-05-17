# ShakeVision OpenData Monitor

> 🌐 **桌面级开源地震监测可视化工作站** — 实时拉取全球公民地震网（Raspberry Shake）+ USGS / IRIS 专业台网数据，融合 3D 地球、数据看板、波形/频谱/触发分析于一体。
>
> 🌐 **Cross-platform desktop seismic monitoring workbench** — streams real-time data from the global Raspberry Shake citizen network and the USGS / IRIS professional backbone, unifying a 3D globe, data dashboard, waveform/spectrogram/trigger analysis in one app.

[![CI](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)](https://github.com/yiaogit/seismic-shakevision)
[![Languages: EN · ES · 中文 · FR](https://img.shields.io/badge/i18n-EN%20%7C%20ES%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20FR-brightgreen)](shakevision/i18n/locales/)

---

## 🌟 Highlights

| 模块 | 功能 |
|------|------|
| 🌍 **3D Globe** | ECharts-GL 实时渲染地球，叠加 600+ Raspberry Shake 公民台站 + 400+ USGS/IRIS 骨干台站，按周期过滤地震并按震级分色显示，点击光点可缩放并加入 Pro 工作台 |
| 📊 **Data Dashboard** | 7 张联动 ECharts：Top 国家、震级/深度直方图、24h 时间线（自适应密度气泡）、PAGER 雷达（含区域过滤器）、周期自适应桶图、深度×震级散点 |
| 🔬 **Pro Workbench**（独立浮窗） | 实时三通道波形 + 频谱图 + 24h 鼓式记录 + N-E 质点轨迹 + STA/LTA 触发录波 + MMI 烈度卡 |
| 🔊 **Sonification** | 把最近 60 秒的地动信号变速并播放成可听音频，速度可调（1×–60×） |
| 🌐 **i18n** | 全栈 4 语言（EN / ES / 简中 / FR）即时切换，包含 Web 视图和图表内部、tooltip、报告 HTML |
| 🕒 **Timezone-aware** | 系统时区自动检测 + 手动覆盖；所有时间戳一致显示用户时区 |
| 📄 **Reports** | 单文件 HTML 报告（含 SVG 时间线）+ PDF 导出（QWebEngine） |
| ⚡ **Live SeedLink** | 直连 IRIS rtserve.iris.washington.edu:18000，IU/US/II/IC 网络自动路由，分阶段连接状态显示，可随时取消 |

---

## 📦 安装

### 选项 A：从源码运行（开发者 / 极客）

适用于：macOS（Intel + Apple Silicon M1–M5）/ Windows 10+ / Linux 主流发行版

#### 0. 前置依赖

| 系统 | 必需 |
|------|------|
| 所有平台 | Python ≥ 3.10（建议 3.11 或 3.12）+ Git |
| **Linux** | `libegl1 libxkbcommon0 libxcb-cursor0 libxcb-icccm4 libgl1 libdbus-1-3`（Ubuntu/Debian 上 `apt install`） |
| **macOS** | Xcode Command Line Tools (`xcode-select --install`) |
| **Windows** | Visual C++ Redistributable（pip 安装 PySide6 时通常已附带） |

#### 1. 克隆

```bash
git clone https://github.com/yiaogit/seismic-shakevision.git
cd seismic-shakevision
```

#### 2. 创建虚拟环境 + 安装

<details>
<summary>🍎 <b>macOS</b> (M1–M5 含 Apple Silicon) / 🐧 <b>Linux</b></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# 可选：安装 macOS 原生增强（透明标题栏）
pip install -e ".[macos]"
```

</details>

<details>
<summary>🪟 <b>Windows 10 / 11</b></summary>

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

</details>

#### 3. 下载本地化资源（一次性）

```bash
# 离线 JS 库（ECharts + ECharts-GL，约 4 MB）
bash scripts/install_libs.sh

# 字体（Inter Variable + JetBrains Mono，约 6 MB）
bash scripts/install_fonts.sh
```

> Windows 用户用 Git Bash 或 WSL 运行同样的命令；或手动下载脚本里列出的 URL 到对应目录。

#### 4. 启动

```bash
python -m shakevision
```

首次启动会自动检测系统时区并应用英文界面。点击右上 ⚙ 可切换语言（EN/ES/简中/FR）+ 时区。

---

### 选项 B：预编译安装包（最终用户）

> **状态**：v0.1.0 暂只发布源码包，二进制 `.exe / .dmg / .AppImage` 见 [Roadmap](#-路线图)。

未来 v0.2.0 将在 [Releases](https://github.com/yiaogit/seismic-shakevision/releases) 页面提供：

| 平台 | 下载 | 安装方式 |
|------|------|----------|
| **Windows 10/11 x64** | `ShakeVision-0.2.0-win64.exe` | 双击运行，无需管理员权限 |
| **macOS Apple Silicon (M1–M5)** | `ShakeVision-0.2.0-mac-arm64.dmg` | 拖入 Applications；首次右键 → 打开（未签名） |
| **macOS Intel** | `ShakeVision-0.2.0-mac-x64.dmg` | 同上 |
| **Linux x64** | `ShakeVision-0.2.0-linux-x86_64.AppImage` | `chmod +x` 后双击 |

---

## 🚀 快速上手

```
启动 → 默认进入 🌍 Globe 视图
  ├── 点击任意 USGS 光点 → 弹窗"添加到 Pro?" → ✅ → 浮现在 Pro 控制面板下拉
  ├── 切换 📊 Data → 查看 7 张联动图表 + 周期/区域过滤
  └── 右上 🔬 Pro → 打开独立的专业窗口
                    ├── 选刚才加入的 USGS 台站
                    ├── 点 Connect → 走 SeedLink 实时流
                    └── 看实时波形 / 频谱 / 鼓式记录 / 质点轨迹

右上 ⚙ Settings → 切语言 + 时区，立即生效，无需重启
```

---

## 🗺 项目结构

```
seismic-shakevision/
├── pyproject.toml          # 项目元数据 + 依赖
├── README.md               # 本文件
├── CHANGELOG.md            # 版本变更日志
├── LICENSE                 # MIT
├── requirements.txt        # 锁定的依赖（pip-tools 风格）
├── tech_stack.md           # 技术栈决策记录
│
├── scripts/                # 一次性资源下载脚本
│   ├── install_fonts.sh    # Inter + JetBrains Mono → assets/fonts/
│   └── install_libs.sh     # ECharts/ECharts-GL → web/*/lib/
│
├── shakevision/            # ── 主包 ──
│   ├── __main__.py         # 入口（python -m shakevision）
│   ├── config.py           # 全局配置（台站预设/SeedLink 注册表/默认值）
│   │
│   ├── sources/            # ── 数据源 ──
│   │   ├── base.py         # DataSource 抽象 + SampleBatch
│   │   ├── mock.py         # MockSource（合成数据，开发用）
│   │   └── seedlink.py     # SeedLinkSource（真实 IRIS/Shake 流，含 5s TCP 预检 + 分阶段反馈 + 安全 stop）
│   │
│   ├── processing/         # ── 信号处理（纯 NumPy/SciPy/ObsPy）──
│   │   ├── buffer.py       # RingBuffer 环形缓冲（线程安全）
│   │   ├── filters.py      # Butterworth 带通 + 去趋势
│   │   ├── detector.py     # STA/LTA 触发状态机
│   │   ├── spectrum.py     # 滑窗 FFT 频谱
│   │   ├── recorder.py     # MiniSEED 录波器
│   │   ├── intensity.py    # PGV → MMI 烈度估算
│   │   └── sonifier.py     # 地动→音频转换（变速重采样）
│   │
│   ├── services/           # ── 外部 API 客户端 ──
│   │   ├── cache.py        # 文件缓存（TTL）
│   │   ├── usgs.py         # USGS GeoJSON Feed 客户端
│   │   ├── iris.py         # IRIS FDSN Station Service 客户端
│   │   ├── shakenet.py     # Raspberry Shake FDSN 客户端
│   │   ├── worker.py       # 单 worker 异步刷新地震+台站
│   │   ├── report.py       # HTML 报告生成器（i18n 多语言）
│   │   ├── timezone_service.py  # 时区单例（系统检测 + 用户覆盖）
│   │   └── data_models.py  # Earthquake / ShakeStation / PagerLevel
│   │
│   ├── ui/                 # ── PySide6 桌面 UI ──
│   │   ├── main_window.py  # 主窗口（Globe + Dashboard 双 tab + Pro 浮窗按钮）
│   │   ├── app_header.py   # 顶栏（Pro 按钮 + 设置齿轮 + 连接状态 LED）
│   │   ├── globe_view.py   # 3D 地球 QWebEngineView 桥
│   │   ├── dashboard_view.py # 7 图表看板 QWebEngineView 桥
│   │   ├── pro_window.py   # 🔬 Pro 浮窗（独立 QMainWindow）
│   │   ├── control_panel.py # 台站选择 + 滤波 + STA/LTA + 音频
│   │   ├── waveform_widget.py / spectrogram_widget.py
│   │   ├── helicorder_widget.py / particle_motion_widget.py
│   │   ├── intensity_card.py     # MMI 烈度卡片
│   │   ├── audio_player.py       # QAudioSink 包装 + 状态机
│   │   ├── settings_dialog.py    # 语言 + 时区 + 自定义地址
│   │   ├── loading_overlay.py    # 通用加载/错误覆盖层
│   │   ├── pdf_exporter.py       # printToPdf 包装
│   │   └── macos_native.py       # macOS 透明标题栏（pyobjc 可选）
│   │
│   ├── i18n/               # ── 国际化 ──
│   │   ├── service.py      # LocaleService 单例 + t() 函数
│   │   └── locales/        # 4 语言字典（each 260 keys，全对齐）
│   │       ├── en.json
│   │       ├── es.json
│   │       ├── zh.json
│   │       └── fr.json
│   │
│   ├── web/                # ── 嵌入式 HTML/JS 资产 ──
│   │   ├── globe/          # 3D 地球（ECharts-GL）
│   │   ├── dashboard/      # 7 图表看板（ECharts）
│   │   └── report/         # HTML 报告模板
│   │
│   └── assets/             # 字体 + 图标（脚本下载，不入仓）
│
├── tests/                  # pytest 单元 + 集成测试（30+ 文件）
├── .github/workflows/      # CI（Ubuntu × macOS × Windows / Py 3.10–3.12）
└── .gitignore              # 排除 venv / cache / 字体 / 下载的 JS 库
```

---

## 🛠 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| **UI 框架** | PySide6 ≥ 6.6 | LGPL 协议，跨平台原生外观，QtWebEngine 自带 Chromium |
| **Web 渲染** | QWebEngineView | 嵌入 ECharts/ECharts-GL，不引入第三方浏览器引擎 |
| **3D 地球** | [ECharts-GL](https://github.com/ecomfe/echarts-gl) | 单一图表库覆盖 2D+3D，bundle 比 Three.js 小 |
| **2D 图表** | [Apache ECharts](https://echarts.apache.org/) 5.4 | 7 种图表全用同一引擎 |
| **DSP** | NumPy + SciPy | 工业标准，Butterworth 滤波/FFT 谱图都用 SciPy |
| **地震学** | [ObsPy](https://www.obspy.org/) ≥ 1.4 | SeedLink 客户端 + MiniSEED 读写 |
| **波形绘制** | [pyqtgraph](https://www.pyqtgraph.org/) 0.13 | 60 FPS GPU 加速 |
| **音频** | QtMultimedia QAudioSink | 跨平台，零额外依赖 |
| **时区** | Python 3.9+ `zoneinfo` | 标准库；POSIX `/etc/localtime` symlink 自动检测 |
| **i18n** | 自研 JSON dict + `t()` | Python + JS 共用同一份字典，无构建步骤 |
| **测试** | pytest + pytest-qt + ruff | Ubuntu/macOS/Windows × Py 3.10-3.12 矩阵 CI |

---

## 🔧 配置

默认配置定义在 `shakevision/config.py`。用户运行时可通过 ⚙ Settings 改语言/时区；下次启动会从 QSettings 恢复。

**SeedLink 服务器映射**（按网络代码自动路由）：

```python
SEEDLINK_SERVERS = {
    "IU": ("rtserve.iris.washington.edu", 18000),    # 全球网
    "US": ("rtserve.iris.washington.edu", 18000),    # 美国国家网
    "II": ("rtserve.iris.washington.edu", 18000),    # IRIS/IDA
    "AM": ("rs.local",                    18000),    # 本地 Raspberry Shake
    # …(IC, GT, CU, G, GE, C 也走 rtserve.iris)
}
```

> ⚠ **Raspberry Shake 公开 SeedLink 不存在**。只能连本地 LAN 内自己的设备（`rs.local:18000`）或付费 RTDC 订阅。

---

## 🧪 开发与测试

```bash
# 运行测试套件
pytest -v

# Lint
ruff check shakevision tests

# 字节码编译检查
python -m compileall -q shakevision tests
```

CI 在每次 push / PR 时自动跑：
- Ubuntu / macOS / Windows
- Python 3.10 / 3.11 / 3.12
- ruff + pytest（Linux 用 xvfb-run，macOS/Windows 用 `QT_QPA_PLATFORM=offscreen`）

---

## 🌐 i18n 翻译说明

字典在 `shakevision/i18n/locales/*.json`（each 260 keys，4 语言对齐）。

**贡献新翻译**：
1. 复制 `en.json` 为新文件，例如 `ja.json`
2. 翻译每个值（不改 key）
3. 在 `shakevision/i18n/service.py` 的 `SUPPORTED_LANGUAGES` + `LANGUAGE_LABELS` 注册
4. PR

---

## 📜 数据来源

- [Raspberry Shake](https://raspberryshake.org/) — 公民地震学网络，开放数据 CC-BY
- [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/) — 地震 GeoJSON Feed
- [IRIS DMC](https://ds.iris.edu/) — 专业台网元数据 + SeedLink 实时流（`rtserve.iris.washington.edu`）

---

## 🗺 路线图

- [x] v0.1.0 — 全功能源码版本（i18n + 时区 + Pro 浮窗 + 设置面板）
- [ ] v0.1.1 — 打包二进制：Windows `.exe` + macOS `.dmg` (arm64 + x64) + Linux `.AppImage`
- [ ] v0.2.0 — 历史回放：从 IRIS FDSN dataselect 下载 MiniSEED 按可调速度回放
- [ ] v0.3.0 — 自定义 LAN Raspberry Shake 连接 UI（输入 IP）
- [ ] v0.4.0 — 主题切换（亮色 / 高对比度）

---

## 🤝 贡献

欢迎 Issue / PR。代码注释使用西班牙语（项目历史约定），用户面对的字符串通过 i18n 系统。提交前请跑 `ruff check` + `pytest`。

---

## 📄 License

[MIT License](LICENSE) © 2025 Yiao

---

## 🙏 致谢

感谢 [Raspberry Shake](https://raspberryshake.org/) 社区与 [ObsPy](https://www.obspy.org/) 项目提供的开源地震学工具链；致敬全球公民科学家在地震监测领域的持续贡献。
