# SeismicGuard 0.8.3.0 — 全 UI 巡检与功能逻辑审计

日期：2026-10-18
范围：主窗四个页面及各状态、设置/个人/台站弹窗、Workbench
Live/Replay/24h/Hodogram、浅色主题抽查。
截图目录：`/tmp/sg_shots/ui_review/`（临时，不随仓库提交）。

---

## 一、逐页截图与结论

| # | 页面/状态 | 截图 | 结论 |
|---|---|---|---|
| 1 | Globe · Quakes | `00_globe_quakes.png` | 正常；头图/图例/计数器/时间窗清楚 |
| 2 | Globe · Devices | `01_globe_devices.png` | 正常；2.8 万 Shake + 151 USGS 点位 |
| 3 | Data · Live | `02_data_live.png` | KPI/图表/地区选择正常 |
| 4 | Data · Analysis 空态 | `03_data_analysis_empty.png` | 空态文案清楚；日期滑块右侧已留白 |
| 5 | Data · Analysis 结果 | `04_data_analysis_result.png` | 19 事件/1 年；KPI 改为“13 d ago” |
| 6 | Events · Live | `05_events_live.png` | 目录/过滤/最近台站布局正常 |
| 7 | Events · 选中事件 | `06_events_selected.png` | 最近台站 Δ/km/类别显示正常 |
| 8 | Events · Historical | `07_events_historical.png` | 未查询提示已改为“先选择筛选并 Search” |
| 9 | Mine · 空 | `08_mine_empty.png` | 新增空态引导；Unfavorite 禁用 |
| 10 | Mine · 有收藏 | `09_mine_populated.png` | 收藏事件/台站行、筛选正常 |
| 11 | Settings · General | `10_settings_general.png` | 地址输入框不再截断；标签黑底已去除 |
| 12 | Settings · My Shakes | `11_settings_shakes.png` | 空列表提示正常 |
| 13 | Settings · Reset | `12_settings_reset.png` | 标签透明/内边距修复；Reset 页禁用 Apply/Cancel |
| 14 | Profile | `13_profile.png` | 活动日志不再出现 “M? near ?” / “station ?” |
| 15 | 台站弹窗 | `14_station_dialog.png` | 台站/SeedLink/选择符/按钮完整 |
| 16 | Workbench · Live 空 | `15_workbench_live_empty.png` | 改为 Waiting for data/spectrum，无空轴 |
| 17 | Workbench · Live 已连接 | `16_workbench_live_connected.png` | IU.PAB 三通道 + 频谱图正常 |
| 18 | Workbench · 24h Diary | `17_workbench_helicorder.png` | 标题跟随 BHZ；新增实时填充提示 |
| 19 | Workbench · Hodogram | `18_workbench_hodogram.png` | 极化方位/直线度正常 |
| 20 | Workbench · Replay 空 | `19_workbench_replay_empty.png` | 显示 IU.ANMO/BHZ + Load 提示；PSD 轴 0–20 Hz |
| 21 | Workbench · Replay 已加载 | `20_workbench_replay_loaded.png` | 波形/频谱/PSD + P/S 标记完整 |
| 22 | 浅色 Data | `21_light_data.png` | 图表/文字可读 |
| 23 | 浅色 Events | `22_light_events.png` | 表格/过滤可读 |

---

## 二、本轮修复的 UI 显示问题

| 问题 | 修复 |
|---|---|
| Workbench/Replay 空绘图区显示 0.1–0.9 s、00:00:00、±400 `(x0.001)` | Waveform/Spectrogram 增加 EmptyState，未加载时隐藏绘图区 |
| Replay 空态 `STATION: —`、EHZ 标签与 IU.ANMO/BH 不符 | 空态显示 `IU.ANMO`，通道按波段（BHZ/BHN/BHE） |
| PSD 空态坐标 ±400 / x0.001 | 固定 0–20 Hz / −120–0 dB，关闭 SI 前缀 |
| Helicorder 硬编码 EHZ，18 s 数据看起来全空 | 标题跟随实际波段（BHZ）；增加“24 h 记录实时填充”提示 |
| 顶栏版本 chip 占满 56 px、状态/分隔标签黑底 | chip 固定 22 px；HeaderStation/Status/Sep 透明背景 |
| Mine 空表无说明、Unfavorite 可点 | 空态/无匹配提示；无选中行时禁用删除 |
| Settings Reset 文字贴边、标签黑底、Apply 语义冲突 | 增加内边距/透明背景；Reset 页禁用 Apply/Cancel |
| Settings 地址占位被截断 | 输入框最小宽度 240 px |
| Analysis “Most recent 311.5 h ago” | ≥48 h 显示天数（13 d ago），≥2 年显示日期 |
| RangeSlider 最后一格日期被滚动条裁切 | 右侧留 24 px，tick 标签夹紧 |
| 历史事件未查询却显示 No recent earthquakes / 0/0 | 增加“选择筛选并 Search catalog”提示 |
| Profile 活动记录 “Inspected station ?” / “M? near ?” | 点击台站记录 network.code；事件记录 place/mag；旧数据回退为通用文案 |
| 地震/台站/连接活动未记录或参数为空 | 补齐 UsageTracker 调用与参数；连接成功记录 streamed |

---

## 三、软件功能清单（面向用户）

### 1. 主窗与全局
- 四个顶层页：Globe / Data / Events / Mine。
- 顶栏：Workbench、Standard/Professional 视图、主题（light/dark）、语言（en/es/fr/zh）、Profile、Settings、MMI/PGV 芯片。
- 全局：UTC 时间显示、Kiosk（F11/Esc）、浅/深主题、四语言即时切换、首次运行向导、Splash、Localízame 介绍页。

### 2. Globe
- ECharts-GL 3D 地球（昼/夜/全息视觉）。
- 图层：Devices / Quakes / Both。
- 时间窗：1 h / 24 h / 7 d / 30 d。
- 缩放、旋转、重置、暂停旋转。
- 台站点选 → 弹窗（坐标/海拔/SeedLink/通道/收藏/Monitor live/View history）。
- 地震点选 → 事件回顾确认 → Replay。
- 图例、事件计数、设备计数。
- 收藏状态星标。

### 3. Data
- Live：KPI（事件数、最大震级、最近事件、影响区域）、Top-10 国家、震级分布、深度分布、时间线、地区筛选、周期（1h/6h/24h/7d/30d）。
- Analysis：地区 + 时间窗 + 最小震级 + 双滑块时间范围；`fdsnws-event` 查询/计数；空态/超限提示。
- Advanced Analysis：Depth×Magnitude、Period distribution、Magnitude over time、Depth distribution、Gutenberg–Richter/b 值、能量、Mc(t)、Omori、空间密度等。
- 报告：HTML/PDF（live 与 analysis）。
- 空态与查询状态、数据上限保护。

### 4. Events
- Live / Historical 两种模式。
- 周期：day/week/month；手动 Refresh；更新时间。
- 历史查询：时间滑块 + 24h/7d/30d/1y/5y 预设、最小/最大震级、地区、排序、最大结果数、Clear、Search catalog。
- 过滤：最小震级、深度、时间范围、地点/国家/地区搜索、计数器。
- 表格：时间/震级/深度/距离类别/地点；排序；2000 行渲染上限提示。
- 最近台站：台站、Δ°、km、类型；双击复核。
- 收藏事件/台站；双击事件用最近台站复核。
- 历史错误/空结果状态。

### 5. Mine
- 收藏事件表（时间/震级/地点）；双击 Replay。
- 收藏台站表（台站/站点）；双击使用。
- 录音列表（时间/台站/文件）；双击回放；打开文件夹/删除。
- 本地 QuakeML 复核目录（时间/台站/P icks/描述）；双击重开；删除/打开文件夹。
- 时间范围 + 文本过滤；刷新；计数。
- 无收藏/无匹配空态；删除按钮仅在选中时可用。

### 6. Workbench · Live
- 台站选择/添加（来自地图或 LAN Shake）、Connect/Stop。
- SeedLink 实时数据（3 通道，时间对齐）。
- 带通滤波（低/高/阶数，Body/Surf/Reg/Off 预设）、STA/LTA 阈值。
- 波形：冻结、counts/m/s、P/S 拾取、清除、自动缩放、十字光标、区域选择、冻结读数。
- 频谱图：线性/对数频率、FFT 窗长 0.5/1/2/4 s、色标/对比度。
- 24h Helicorder（波段动态标题）。
- Hodogram：N-E 轨迹 + 极化方位 + 直线度。
- 录音、声化播放、触发状态。
- 顶栏 MMI/PGV 芯片（两模式共用；点击开工作台）。

### 7. Workbench · Replay
- 台站/波段（BH/…）/开始 UTC/时长/输出（counts/VEL/DISP/ACC）。
- 时长预设 30s–1h；独立带通滤波；Load/Clear。
- IRIS dataselect 下载；TauP P/S；ZNE→ZRT；整段去响应。
- 静态波形缩放/平移/区域选择；PSD；频谱图（FFT/对数）；Spectrogram/PSD 开关。
- 导出 PNG/CSV/QuakeML；保存/重开本地目录。
- 事件横幅、最近台站、自动窗口提示。

### 8. 设置 / Profile / 其他
- Settings：语言、时区、地址（手动/IP 自动检测）、LAN Shake 增删改、Reset（清缓存/偏好/收藏/统计并重启）。
- Profile：Guest/GitHub 登录、使用统计（启动/时长/事件/台站/音频/报告）、最近活动（本地）。
- Onboarding 六步向导、Splash、Localízame。
- 收藏持久化、QuakeML 目录持久化、录音持久化、缓存、设置导入/导出服务（代码层）。
- 无自动更新（唯一 roadmap 待办）。

---

## 四、功能逻辑问题与改进建议

| 优先级 | 问题 | 建议 |
|---|---|---|
| **P0** | Workbench 初始显示 `Mi Shake LAN (rs.local)` / `AM.LOCAL`，Connect 可点；用户会误以为已选真实台站，点击通常失败 | 改为显式“未选择台站”占位项，Connect 禁用；或首次进入时提示“从地图/事件添加台站”。保留 demo 仅开发模式 |
| **P0** | SeedLink 点 Connect 后约 13 s 才变 Connected、首帧约 13.5 s；10 s 通道宽限 + IRIS 13 s 分包，界面只显示“Conectando…” | 进度文案区分“TCP/握手完成 / 等待水平通道 / 首包到达”；可先发 Z 通道让波形立即出现，横向通道到达后补齐；或把 grace 降到 5 s 并允许 hold |
| **P1** | 地图 2.8 万点中台站标记很小，桌面端也难以精确点中；自动化点击多次未命中 | 增加地图台站搜索/最近台站列表；增大 USGS 点 click 半径；hover 显示台站名；提供“按代码打开”入口 |
| **P1** | 历史事件未查询时计数器仍显示 `Filtered 0 / 0` | 未查询时显示 `—` 或“未查询”，查询后再显示计数 |
| **P1** | Replay 空态 PSD 提示“Select a segment…” 但尚无数据 | 空态改为“加载数据后选择一段”；加载后再显示原提示 |
| **P1** | 地图台站达到动态上限（8）时，`add_station` 失败但弹窗/状态没有明确上限说明 | 弹窗中显示剩余槽位；满时禁用 Monitor live 并提示先删除旧台站 |
| **P1** | Profile 旧活动记录（无参数）会显示占位符 | 已对 `?` 做通用回退；建议后续做一次迁移/清理，避免历史噪声 |
| **P2** | “View history” 实际是打开 Replay 台站选择，不是事件历史 | 改名为“Open station in Replay”/“在回放中打开台站” |
| **P2** | Data/Events 两条 ScopeBar 占用垂直空间，和页签标题信息重复 | 保留说明但可折叠/首次提示；或把说明收进标题 tooltip |
| **P2** | 分析页 “Most recent” 用相对时间，跨年窗口仍不够直观 | 已改为天/日期；可进一步对 >1 年直接显示 `YYYY-MM-DD` |
| **P2** | Helicorder 24 h 页在刚连接时几乎全空 | 已加“实时填充”提示；可加“已采集 x 分钟/24 h”进度 |
| **P2** | Settings Reset 页仍有 Apply/Cancel 空间占用（已禁用） | 进一步隐藏，只保留 Restore defaults + Reset 按钮 |
| **P2** | 无自动更新 | 见此前方案：先做 manifest + 通知 + 应用内下载校验；L2 等签名/回滚就绪 |

---

## 五、验证

- `pytest -q`：**580 passed**（2.95 s）。
- `ruff check .`：clean。
- `compileall`：OK。
- i18n：4 语言各 **761** 键。
- 截图 23 张，覆盖主窗四页、弹窗、Workbench 全部子页、浅色抽查。
