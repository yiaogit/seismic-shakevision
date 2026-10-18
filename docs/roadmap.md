# SeismicGuard 工作台优化路线（0.8.3.0 之后）

> **基线已更新**：原 v0.7.7 路线里的分析内核、频域/极化、事件目录、打磨项
> 大部分已随 0.8.0 / 0.8.3 交付（回放重写、事件中心、我的收藏、数据面板
> 双页、统计内核）。本文件现在只列**仍未完成**的项。
> 历史来源：`seismic-software-survey.md` 缺口表 + `workbench-assessment.md`
> + `ux-review.md`。产品上下文见 `CLAUDE.md`，本机验证清单见其 §9。

## 一、已交付（归档，勿重做）

- ✅ ZNE→ZRT 旋转、滤波预设、整段去仪器响应（Counts/VEL/DISP/ACC）。
- ✅ PSD（Welch）+ 主频；极化方位角 + 直线度；Hodograma 刷新稳定化。
- ✅ 事件目录浏览器（顶栏「事件」中心，v0.8.0）＋ 双击进回放复核。
- ✅ **本地触发录制纳入「我的」**（v0.8.0）；**复核拾取累积为持久本地
  QuakeML 目录**（`services/catalog_store.py`，可重开恢复 P/S 标记）。
- ✅ 波形标签跟随波段；示波器十字光标/读数/选区同步；kiosk 模式。
- ✅ 频谱图 dB 色标 + 拖动对比度。
- ✅ 数据面板「实时 | 分析」双页 + 拖动式区间滑块（0.8.3，不在原路线内）。
- ✅ 统计内核 `processing/seismic_stats.py` + 专业图表 + 分析报告（0.8.3）。
- ✅ 频谱图对数频率轴（1/2/5×10ⁿ 刻度，矩阵对数重分箱）。
- ✅ FFT 窗长可调（0.5 / 1 / 2 / 4 s，Live 与 Replay 都生效）。
- ✅ 强度卡压成顶栏 MMI/PGV 芯片（Standard + Professional 共用）。
- ✅ 数据页 / 事件中心职责说明栏 + 互跳（`ScopeBar`，ux-review P2）。

## 二、待办（按优先级）

1. **发布轨道：无自动更新机制** — 用户需手动下载安装包（v1.0.0 再议）。
   （v0.7.6.1 产物缺失的问题已随 0.8.3.0 三平台产物齐全而消失。）

## 三、搁置（已论证价值低）

- 多台站对比 / 定位（IRIS 分布稀疏）。
- 实时波段选择（BH 够用）。
- 插件系统（架构太重、过早）。

## 四、本机验证（已完成）

在 macOS 26 / arm64、Python 3.14（off-matrix）、PySide6 6.12 上验证并修复：

- 数据面板双页：分析页空状态、真实历史查询（1,369 事件）、专业图表、
  报告导出（HTML/PDF）。
- SeedLink 实时：IU.ANMO / IU.OTAV，三通道按时间对齐（100 Hz），
  波形 Y 自缩放、频谱图、鼓式记录、质点运动，干净断开（无 QThread 警告）。
- 回放：历史事件（日本 M7.6）与收藏事件（墨西哥 M5.2）均完成
  dataselect 下载、TauP P/S、去响应（VEL）、ZRT、PSD、频谱图与
  CSV/QuakeML/PNG 导出。
- 三条端到端流程：地图→就近台站→工作台；事件中心历史→就近台站→回放；
  收藏→「我的」→工作台。
- 频谱图对数轴 / FFT 窗长：Live 1→2 s 重建计算器；Replay 1 s→4 s
  频点数 21→81、时间列 2397→597，对数模式 256 行，P/S 标记保持。
- MMI 芯片：IU.ANMO 实时数据出现、切 Standard 仍可见、点击回工作台、
  断开自动隐藏。
- UX P2：数据页“逐条复核 →”切到事件页，事件页“统计视图 →”切回数据页。
- 全 UI 巡检：逐页截图主窗四页/弹窗/工作台各子页，修复空态轴、顶栏
  版本 chip、Mine 空态、Settings Reset、活动日志占位符、
  Helicorder 波段、分析日期等显示问题。
- Live 波形平滑：预填充 60 s 历史 + 12 s playout 缓冲，IU.PAB 实测
  29.8 Hz、97% 帧有时间推进；检测/MMI 仍用最新数据。见
  `docs/smooth-live-waveform.md`。
- 全功能链路审计：Globe 自转/图层/台站弹窗→工作台、Data/Events 历史、
  Mine 收藏→Replay、Workbench 控件、Kiosk、报告；修复 Stop 的 QThread
  双重释放 segfault、Workbench 置顶时弹窗被挡、Kiosk 快捷键。
  见 `docs/functional-paths-audit.md`。
- 地图 → 最近真实台站 IU.PAB（San Pablo，距马德里 111.5 km）：
  地图 Devices → 台站弹窗 → Monitor live → 工作台 Connect。
  网络握手 257 ms / TCP 105 ms / 首包 2.55 s；应用 “Connected” 约 13.1 s
  （含 10 s 通道对齐宽限 + IRIS 13 s 分包），实时延迟 10.8–16.7 s。

修复清单见 `CHANGELOG.md` 的 `[Unreleased]`；逐步清单与结果在
`CLAUDE.md` §9。仍未做：仅剩自动更新机制（另行排期）。
