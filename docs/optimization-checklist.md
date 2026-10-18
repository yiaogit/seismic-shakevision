# SeismicGuard 综合检查与优化清单

日期：2026-10-18  
版本：0.8.3.0  
汇总范围：全 UI 巡检 + 波形刷新率专项 + 全功能链路测试。

状态图例：
- `[x]` 已验证 / 已修复
- `[~]` 已验证但受自动化/环境限制，需真实桌面复核
- `[ ]` 尚未实施，列入优化 backlog

---

## 一、结论摘要

| 维度 | 结论 |
|---|---|
| UI 逐页巡检 | 23 个页面/状态已截图检查；空态、顶栏、Mine、Settings、日期、Helicorder、活动日志等问题已修复 |
| 波形刷新率 | UI 定时器 **30.78 Hz**、单帧绘制 **0.24 ms**，瓶颈不是渲染，而是 IRIS **~13 s/包** 的数据节奏 |
| 波形平滑 | 已实现 **60 s 历史预填充 + 12 s playout**；IU.PAB 实测 **29.8 Hz**，676 帧中 655 帧时间推进（97%），200 ms 两帧波形差 20,358 像素 |
| 功能链路 | Globe/Data/Events/Mine 21/21；Workbench 控件 15/15；Replay 下载/PSD/导出通过；报告/Kiosk/连续 Connect-Stop 通过 |
| 真实缺陷 | 修复 **Stop 时 QThread segfault**、**Workbench 置顶时弹窗被挡**、**Kiosk 快捷键失效** |
| 测试 | **586 passed**；ruff/compileall clean |
| P0/P1 进展 | P0-1/P0-2/P0-3、P1-1…P1-9 完成；P2-1…P2-8/P2-10 完成（P2-8 为 L1，L2 待签名/回滚） |

---

## 二、UI 巡检清单

### 2.1 主窗 / 顶栏

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| 四个顶层页切换 | `[x]` | Globe / Data / Events / Mine 均可点击 |
| 版本 chip 尺寸 | `[x]` | 从整条 56 px 缩为 22 px |
| 状态/分隔标签黑块 | `[x]` | HeaderStation/Status/Sep 透明化 |
| 主题切换 | `[x]` | dark ↔ light，图表/报告同步 |
| 语言切换 | `[x]` | 四语言；本轮未逐条重走所有页面 |
| MMI 芯片 | `[x]` | Live 数据后出现；点击打开 Workbench |
| Kiosk | `[x]` | F11/Esc；已改 ApplicationShortcut |
| 浅色主题可读性 | `[x]` | Data/Events 抽查通过 |
| 顶栏 Workbench/Std/Pro 按钮 | `[x]` | 可打开/切换 |
| 设置齿轮按钮 | `[~]` | 直接构造 SettingsDialog 正常；自动化点击受 macOS 激活影响，需真实桌面复核 |
| Profile 按钮 | `[x]` | 统计/活动正常 |

### 2.2 Globe

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| 自转暂停/恢复 | `[x]` | `paused` class 正确切换 |
| Devices/Quakes/Both | `[x]` | 三个图层 active 正确 |
| 1h/24h/7d/30d | `[x]` | 7d active 后回 24h |
| 放大/缩小/复位 | `[x]` | 按钮点击无 JS 错误 |
| 台站弹窗 | `[x]` | 坐标/SeedLink/通道/槽位完整 |
| 台站 Favorite | `[x]` | FavoritesStore 增加；无 toast（见 backlog） |
| Monitor live → Workbench | `[x]` | 台站进入 combo；Connect/Stop 正常 |
| View history → Replay | `[x]` | Replay 模式 + 台站预选 |
| 地震弹窗 Favorite | `[x]` | 收藏成功 |
| 地震 Review → picker → Replay | `[x]` | mode=1，事件 banner 预填 |
| 标记真实鼠标命中 | `[~]` | WebGL 自动化限制；真实桌面可用，建议加搜索入口 |

### 2.3 Data

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| Live 周期 1h/6h/24h/7d/30d | `[x]` | 6h/24h 实测 active |
| Live Region + KPI + 图表 | `[x]` | 10 个 canvas 实测 |
| Analysis 空态 | `[x]` | 未查询时显示引导 |
| Analysis 查询（IS/1y/M3） | `[x]` | 19 事件，图表正常 |
| 超 20k 上限提示 | `[x]` | 既有逻辑 |
| “Most recent 311.5 h” | `[x]` | 改为 13 d ago，>2 年显示日期 |
| RangeSlider 右端日期 | `[x]` | 右侧留 24 px，不再被滚动条裁切 |
| Review events → Events | `[x]` | tab 2 |
| Statistics view → Data | `[x]` | tab 1 |
| 报告 Export HTML | `[x]` | 24–25 KB 实测 |
| 报告 PDF | `[x]` | 既有 smoke 通过；本轮未重跑 |
| 分析页无数据报告保护 | `[x]` | 既有逻辑 |

### 2.4 Events

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| Live / Historical 切换 | `[x]` | mode 0/1 |
| Live 周期/Refresh | `[x]` | 既有 |
| 过滤 M≥5 + 文本 Japan | `[x]` | 2000 → 169 → 7 |
| 历史 1y/IS/M4.5 Search | `[x]` | 5 事件 |
| 最近台站表 | `[x]` | 8 行；双击→Replay |
| 事件收藏（Live/历史） | `[x]` | 自动绑定台站 |
| 历史无查询提示 | `[x]` | 不再显示 No recent earthquakes |
| 未查询计数 0/0 | `[ ]` | 建议显示 `—` 或“未查询” |
| 2000 行渲染上限提示 | `[x]` | 既有 |
| Events 密度/双 ScopeBar | `[ ]` | 可折叠/收进 tooltip（P2） |

### 2.5 Mine

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| 空态提示 | `[x]` | “Nothing saved yet…” |
| Unfavorite 空选禁用 | `[x]` | 选中后才启用 |
| 收藏事件行 | `[x]` | 2 行实测 |
| 双击收藏事件 → picker → Replay | `[x]` | 成功 |
| 收藏台站双击 → Monitor live | `[x]` | 台站进入 combo（2→3） |
| 取消收藏 | `[x]` | 2→1 |
| 时间/文本过滤 | `[x]` | 既有 |
| 录音列表 | `[~]` | 需 STA/LTA 触发后才有内容，本轮未生成 |
| 本地 Catalog 列表 | `[x]` | 保存后 1 条；可双击重开 |
| 无收藏空表 | `[x]` | 引导文案 |

### 2.6 Workbench Live

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| 空态坐标轴 | `[x]` | 改为 Waiting for data/spectrum，无空轴 |
| 台站/通道标签 | `[x]` | 实际波段（BHZ 等），非硬编码 EHZ |
| Filter 开关 | `[x]` | config 同步 |
| Body/Surf/Reg/Off | `[x]` | Body 低 1.0/高 10.0 |
| Freeze | `[x]` | `is_frozen` True |
| P/S 拾取 + Clear | `[x]` | picks 生成/清空 |
| FFT 2 s | `[x]` | 2.0 |
| Log freq | `[x]` | 开关状态 |
| Spectrogram 显示切换 | `[x]` | 隐藏/显示 |
| 24h Diary | `[x]` | 子页切换；有“实时填充”提示 |
| Hodogram | `[x]` | 子页切换 |
| MMI chip | `[x]` | 可见、可点击 |
| Listen/声化 | `[~]` | 需音频设备，本轮未验证声音 |
| Stop | `[x]` | 修复 segfault；3 次连续 Stop 正常 |
| Close with live stream | `[x]` | 清理正常 |

### 2.7 Workbench Replay

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| 空态 station/channel | `[x]` | IU.ANMO/BHZ，而非 —/EHZ |
| PSD 空态轴 | `[x]` | 0–20 Hz / −120–0 dB |
| 事件预填 | `[x]` | Globe/Events/Mine 均可 |
| Download | `[x]` | 10:00 或 9:11（按数据可用性） |
| PSD/Spectrogram 开关 | `[x]` | 隐藏/显示 |
| FFT 2 s / Log | `[x]` | 正常 |
| CSV 导出 | `[x]` | 文件落盘 |
| PNG 导出 | `[x]` | 34–109 KB，文件落盘 |
| Save catalog（有 P/S） | `[x]` | 目录 1 条 |
| QuakeML 导出 | `[x]` | 既有；需 P/S |
| ZRT 旋转 | `[~]` | 仅在有事件+台站坐标+水平分量时启用；POHA 垂直-only 禁用属正确行为 |
| Rotate 禁用原因提示 | `[ ]` | 建议 tooltip/状态说明（P1） |
| 部分数据 9:11/10:00 | `[ ]` | 建议状态标明请求 vs 实际（P1） |
| 无 P/S 时 Catalog/QuakeML | `[ ]` | 建议禁用并提示先放 P/S（P1） |

### 2.8 Settings / Profile / 辅助

| 检查项 | 状态 | 处理 / 备注 |
|---|---|---|
| General/My Shakes/Reset 三页签 | `[x]` | 直接构造验证 |
| Reset 标签透明/内边距 | `[x]` | 黑底/贴边修复 |
| 地址输入框 | `[x]` | 加宽，占位不再截断 |
| Reset 页 Apply/Cancel | `[x]` | 已隐藏（仅保留 Restore defaults + Reset） |
| Profile 统计/活动 | `[x]` | 活动记录不再出现 “?” |
| 活动日志 station/quake/stream | `[x]` | 参数补齐 + 旧记录回退 |
| Kiosk F11/Esc | `[x]` | ApplicationShortcut |
| 报告 HTML | `[x]` | 菜单触发 |
| Onboarding | `[~]` | 本轮未重走 6 步 |
| GitHub OAuth | `[~]` | 需浏览器，本轮未登录 |
| LAN Shake 添加 | `[~]` | 需 rs.local，本轮未连真实设备 |

---

## 三、波形刷新率专项清单

| 检查项 | 状态 | 数据 / 处理 |
|---|---|---|
| UI 定时器频率 | `[x]` | **30.78 Hz**，median 32.4 ms，p95 43.1 ms |
| 单帧绘制耗时 | `[x]` | **0.24 ms** median / 0.31 ms p95 |
| 数据时间戳变化 | `[x]` | 30 s 内仅 **2 次**（8.7 s / 6.9 s） |
| SeedLink 包大小 | `[x]` | IRIS ~**13 s/包**（BHZ 523 samples @40 Hz = 13.05 s） |
| 其他服务器 | `[x]` | IPGP/KNMI/INGV 不可达；BGR 拒绝 IU.PAB；无更小包可用 |
| 根因判断 | `[x]` | **不是 FPS/绘制**，是数据到达节奏 |
| 历史预填充 | `[x]` | 首包后 dataselect 取 60 s，插入缓冲区前面 |
| Playout 游标 | `[x]` | 真实时钟推进，12 s 延迟读取窗口 |
| N/E 预填充映射 | `[x]` | dataselect 的 BH1/BH2 → N/E；三通道完整 |
| 检测/MMI 实时性 | `[x]` | 仍用最新窗口，不随视觉延迟 |
| 刷新结果 | `[x]` | **29.8 Hz**；655/676 帧时间推进（97%） |
| 视觉验证 | `[x]` | 200 ms 两帧波形区域 **20,358** 像素变化 |
| 视口延迟 | `[x]` | 约 12–15 s；状态栏提示 `Smooth display buffer +12 s` |
| 本地 Shake/无历史 | `[x]` | 自动回退到原跳包行为，无假数据 |
| 断流 >30 s | `[x]` | 光标一次性重同步，避免无限累积 |
| 平滑/实时开关 | `[x]` | 已加 **Smooth display**；关闭即时回 Realtime，开启恢复 +12s |
| 视觉延迟标注 | `[x]` | Latency 标签改为显示波形延迟 |

**结论**：30 Hz 已达成，而且是“真实平滑”，不是靠提高 FPS 或插值假数据；代价是最多约 12–15 s 的视觉延迟。

---

## 四、全链路测试与真实缺陷清单

### 4.1 已通过的主链路

| 链路 | 状态 |
|---|---|
| Globe 自转/图层/周期/相机 | `[x]` 10/10 |
| 台站弹窗 Favorite / Monitor live→Connect→Stop / View history | `[x]` |
| 地震弹窗 Favorite / Review→picker→Replay | `[x]` |
| Data Live/Analysis/图表/跨页 | `[x]` 7/7 |
| Events Live/历史/筛选/收藏/台站双击→Replay | `[x]` 11/11 |
| Mine 收藏→picker→Replay→Load；台站→Monitor live；取消收藏 | `[x]` 5/5 |
| Workbench Live 滤波/冻结/P-S/FFT/频谱/24h/Hodogram/MMI | `[x]` 15/15 |
| Replay 下载/PSD/频谱/CSV/PNG/目录 | `[x]` 8/8 |
| 报告 HTML / 台站历史 / Kiosk / Scope 跨页 | `[x]` |
| 连续 3 次 Connect/Stop、带活动流关闭 | `[x]` |

### 4.2 本轮修复的真实缺陷

| ID | 问题 | 根因 | 修复 | 验证 |
|---|---|---|---|---|
| BUG-1 | Stop 后 SIGSEGV | worker/QThread 同时 `deleteLater` + Python 包装器析构，QThread 双重释放 | 移除两个 `finished→deleteLater`，`_on_thread_finished` 后安全释放 | Stop 等待 5 s、3 次循环、带流关闭均无崩溃 |
| BUG-2 | Workbench 置顶时弹窗被挡 | 台站/地震/Settings/Profile 对话框 parent 是 MainWindow，落在 Workbench 后面 | 新增 `_dialog_parent()`，Workbench 可见时以其为父窗口 | Review→picker→Replay mode=1；Settings/Profile 在 Pro 可见时正常 |
| BUG-3 | Kiosk F11/Esc 失效 | `QShortcut` 默认 WindowShortcut，焦点在 Workbench/WebEngine 时不触发 | 改 `Qt.ApplicationShortcut` 并保留引用 | F11 进入、Esc 退出 |

### 4.3 自动化限制（不是产品故障）

| 项目 | 状态 | 说明 |
|---|---|---|
| WebGL 地图标记真实命中 | `[~]` | scatter3D 无像素命中 API；测试用同一 WebChannel 入口打开弹窗，按钮真实点击 |
| macOS Settings 齿轮 | `[~]` | 自动化中有时进入无可见 dialog/主窗隐藏状态；直接构造 SettingsDialog 正常；需真实桌面点一次 |
| 音频 Listen | `[~]` | 需音频设备；未验证实际声音 |
| LAN Shake | `[~]` | 需真实 rs.local |
| GitHub OAuth | `[~]` | 需浏览器登录 |
| Onboarding | `[~]` | 需首次运行临时 HOME，本轮未重走 |

---

## 五、链路逻辑与 UX 优化 backlog

### P0（建议下一轮优先）

| ID | 问题 | 建议 | 预期收益 |
|---|---|---|---|
| P0-1 `[x]` | Workbench 初始 `Mi Shake LAN (rs.local)` 假台站，Connect 可点但通常失败 | 已改为“选择台站…”占位；Connect 禁用；选真实台站后启用 | 消除“为什么连不上”的误导 |
| P0-2 `[x]` | 平滑模式固定 12 s 视觉延迟 | 已加 **Smooth display** 开关；默认平滑，取消即 Realtime | 让用户按场景选择低延迟或平滑 |
| P0-3 `[x]` | SeedLink 首包 ~13 s、连接状态只显示“Conectando…” | 已加**不确定进度条 + 实时耗时**；保留首通道/三分量状态 | 降低“卡住”的感知 |

### P1（体验/正确性）

| ID | 问题 | 建议 |
|---|---|---|
| P1-1 `[x]` | 地图标记点击目标小、无搜索 | 已加 Globe **Find station** 搜索（输入 IU.PAB/站点名 + Enter），仍走同一台站弹窗；标记点击半径仍可继续优化 |
| P1-2 `[x]` | 历史事件未查询显示 `Filtered 0/0` | 显示 `—` 或“未查询” |
| P1-3 `[x]` | Replay 空态 PSD 提示“Select a segment…” | 空态改为“加载数据后选择一段” |
| P1-4 `[x]` | Replay 无 P/S 时 Catalog/QuakeML 仍可点 | 无 picks 禁用，tooltip 提示先放 P/S |
| P1-5 `[x]` | Rotate ZRT 禁用原因不明 | tooltip/状态说明“需事件+台站坐标+水平分量”；垂直-only 台站明确提示 |
| P1-6 `[x]` | 回放 9:11/10:00 部分数据 | 状态标明“请求 10:00，实际 9:11”，允许重试/换台站 |
| P1-7 `[x]` | 动态台站达到 8 个上限无反馈 | 弹窗显示剩余槽位；满时禁用 Monitor live 并提示先删除 |
| P1-8 `[x]` | 活动日志旧记录占位符 | `_load_entries` 一次性删除 station/place/mag 的 `?` 占位记录 |
| P1-9 `[x]` | Settings 齿轮真实桌面回归 | 改为非阻塞 `open()` + ApplicationModal + raise/activate；自动化点按钮已见 SettingsDialog |

### P2（打磨/长期）

| ID | 问题 | 建议 |
|---|---|---|
| P2-1 `[x]` | 台站 Favorite 无 toast | 收藏/取消后状态栏提示；My collection 数量徽标 |
| P2-2 `[x]` | 报告只有 File 菜单 | Data 页增加显式 Export report 按钮 |
| P2-3 `[x]` | Reset 页 Apply/Cancel 已禁用但仍占位 | 直接隐藏，仅保留 Restore defaults + Reset |
| P2-4 `[x]` | Data/Events 双 ScopeBar 占高度 | 新增 ▾/▸ 折叠说明，标题/链接保留 |
| P2-5 `[x]` | 分析页相对时间对长窗口不直观 | >365 天直接显示 `YYYY-MM-DD` |
| P2-6 `[x]` | Helicorder 刚连接几乎全空 | 新增 `x min / 24 h collected` 采集进度 |
| P2-7 `[x]` | “View history”语义模糊 | 改为“Open station in Replay”/“在回放中打开台站” |
| P2-8 `[~]` | 无自动更新 | L1 已完成：GitHub manifest + 启动通知 + 平台 asset + SHA-256 下载校验；安装/签名/回滚 L2 待做 |
| P2-9 `[~]` | Audio/LAN/GitHub/Onboarding 自动化缺口 | 已加构造 smoke：AddShake/GitHubLogin/Settings/Update/Onboarding；真实 OAuth/rs.local/音频仍需环境 |
| P2-10 `[x]` | 主窗设置齿轮自动化不稳定 | 已用 `open()` 非阻塞 modal；自动化点按钮可见 SettingsDialog 且 header 保持可见 |

---

## 六、验证与提交

| 项目 | 结果 |
|---|---|
| `pytest -q` | **595 passed**（3.04 s） |
| `ruff check .` | clean |
| `compileall` | OK |
| 连续 Connect/Stop | 3 次无崩溃 |
| 带活动流关闭 | 正常清理 |
| 报告 HTML | 24–25 KB |
| i18n | 4 语言各 803 键 |
| 提交 | 本批次（P0/P1 优化）、`29c3434`（链路修复 + 审计）、`656acba`（平滑波形）、`58fdb0f`（UI 巡检） |
| 工作区 | clean；未 push |

延伸文档：
- [UI 巡检](ui-review-round3.md)
- [平滑波形设计与实测](smooth-live-waveform.md)
- [全功能链路审计](functional-paths-audit.md)
