# SeismicGuard 全功能链路测试与完善空间

日期：2026-10-18
版本：0.8.3.0
测试方式：真实 `MainWindow` + 真实按钮/表格/弹窗 + IRIS SeedLink/dataselect
（不用 controller 直连捷径；地图标记点击的 WebGL 命中限制见 §5）。

---

## 1. 覆盖总览

| 模块 | 链路数 | 结果 |
|---|---:|---|
| Globe（自转/图层/周期/相机/台站/地震） | 10 | ✅ 全部通过 |
| Data（Live/Analysis/图表/跨页） | 7 | ✅ 全部通过 |
| Events（Live/历史/筛选/最近台站/收藏） | 11 | ✅ 全部通过 |
| Mine（收藏事件/台站/删除） | 5 | ✅ 全部通过 |
| Workbench Live（滤波/冻结/拾取/FFT/频谱/24h/Hodogram/MMI） | 16 | ✅ 全部通过 |
| Replay（事件预填/下载/PSD/频谱/PNG/CSV/目录） | 8 | ✅ 通过（ZRT 条件见 §4） |
| Settings / Profile / 主题 / Kiosk | 6 | ✅ 直接验证通过；齿轮按钮的自动化有 macOS 激活限制 |
| 报告 / 跨页跳转 / 台站历史 / 关闭清理 | 6 | ✅ 通过 |

**关键回归**：连续 3 次 Connect → Stop、Stop 后等待事件循环、带活动流关闭窗口，均无崩溃。
**测试套件**：583 passed；ruff/compileall clean。

---

## 2. 功能清单与真实使用链路

### 2.1 全局 / 外壳

| 功能 | 打开方式 / 链路 |
|---|---|
| 四页导航 | 顶栏 tabs：Globe → Data → Events → Mine |
| Workbench | 顶栏 **Workbench** 按钮 |
| Standard / Professional | 顶栏 **Std view / Pro view** 分段按钮 |
| 主题 | 顶栏月亮/太阳按钮（dark ↔ light） |
| 语言 | 顶栏语言/设置；四语言即时切换 |
| Profile | 顶栏用户图标 |
| Settings | 顶栏齿轮 |
| MMI/PGV chip | Live 连接后顶栏出现；点击打开 Workbench |
| Kiosk | `F11` 进入，`F11`/`Esc` 退出 |
| 状态栏 | 延迟、连接状态、操作提示 |
| 首次运行 | Splash → Onboarding 6 步（本轮未重新截图） |

### 2.2 Globe

| 功能 | 链路 |
|---|---|
| 3D 地球 | Globe 页自动加载 |
| 图层 | SHOW 区 **Devices / Quakes / Both** |
| 时间窗 | **1h / 24h / 7d / 30d** |
| 自转暂停/恢复 | 右侧相机栏 **⏸/▶**（`cam-rotate`） |
| 放大/缩小/复位 | 右侧 **+ / − / ⟲** |
| 台站详情 | 点设备标记 → 台站弹窗 |
| 台站收藏 | 弹窗 → **Favorite**（再次打开变 Unfavorite） |
| 台站加入实时 | 弹窗 → **Monitor live** → Workbench 左侧 combo → **Connect** |
| 台站历史 | 弹窗 → **View history** → Workbench Historical + Replay 预选台站 |
| 地震详情 | 点地震标记 → Review/Favorite/Cancel |
| 地震收藏 | 地震弹窗 → **Favorite** |
| 地震回顾 | 地震弹窗 → **Review** → 选择最近台站 → Replay |
| 图例/计数 | 左下 Magnitude、右下地震计数 |

### 2.3 Data

| 功能 | 链路 |
|---|---|
| Live/分析切换 | Data → **Live / Analyze** |
| Live 周期 | Web 区 **1h / 6h / 24h / 7d / 30d** |
| Live 地区 | Region 下拉 |
| KPI/图表 | 顶部 KPI + Top-10 / 震级 / 深度 / 时间线 / 速率 / 震中 |
| Analysis 查询 | Analyze → Region + Window + Min M + 双滑块 → **Search** |
| 专业图表 | GR/b、能量、Mc(t)、Omori、深度/空间密度等 |
| 空态/超限 | 未查询/超过 20k 的提示 |
| 跨页 | **Review events →** → Events |
| 报告 | File 菜单 **Export HTML / Export PDF**（HTML 实测 24–25 KB） |

### 2.4 Events

| 功能 | 链路 |
|---|---|
| Live / Historical | Events → **Live / Historical** |
| 周期/刷新 | Live 栏 Period + **Refresh** |
| 过滤 | Min magnitude / Depth / Time range / 搜索文本 |
| 表格 | 时间/震级/深度/距离类别/地点；排序 |
| 选择事件 | 单击行 → 右侧 Nearest stations 填充 |
| 最近台站 | 台站/Δ°/km/类别；双击 → Replay（该台站） |
| 事件收藏 | 选中事件 → ☆ Favorite（自动收藏绑定台站） |
| 历史查询 | Historical → 1y/5y 快捷 + Region + Min/Max M + Sort + Max results + **Search catalog** |
| 历史清空 | **Clear** |
| 跨页 | **Statistics view →** → Data |

### 2.5 Mine

| 功能 | 链路 |
|---|---|
| 收藏事件 | Mine → Favorite earthquakes |
| 复核收藏事件 | 双击行 → 选择最近台站 → Replay |
| 收藏台站 | Mine → Favorite stations |
| 使用收藏台站 | 双击行 → 台站弹窗 → Monitor live |
| 取消收藏 | 选中行 → Unfavorite |
| 过滤 | 时间范围 + 文本；Refresh |
| 录音 | 列表 → 双击回放 / 打开文件夹 / 删除 |
| 本地目录 | 列表 → 双击重开 / 打开文件夹 / 删除 |
| 空态 | 无收藏/无匹配提示；删除按钮仅选中时可用 |

### 2.6 Workbench Live

| 功能 | 链路 |
|---|---|
| 台站选择 | 左侧 STATION combo（含地图添加的台站） |
| 连接/停止 | **Connect / Stop** |
| 带通滤波 | Enable filter + Low/High/Order |
| 预设 | **Body / Surf / Reg / Off** |
| STA/LTA | Threshold slider（折叠区） |
| 冻结/解冻 | **Freeze** |
| 单位 | **m/s** |
| P/S 拾取 | **P / S**；✕ 清除；⟲ 复位 |
| 自动冻结 | **Auto** |
| 频谱图 | FFT window 0.5/1/2/4 s；**Log freq** |
| 频谱显示 | 右上 **Spectrogram** 开关 |
| 24h 日记 | 子页 **24h Diary** |
| Hodogram | 子页 **Hodogram** |
| 声化 | Sound 区 **Listen**（需音频设备） |
| MMI chip | 顶栏 chip；点击回到 Workbench |

### 2.7 Workbench Replay

| 功能 | 链路 |
|---|---|
| 进入历史 | Workbench → **Historical analysis** |
| 台站/波段 | Station + Band |
| 时间/时长/输出 | Start UTC、Duration、Output counts/VEL/DISP/ACC |
| 快捷时长 | 30s / 1min / 2min / 5min / 10min / 30min / 1h |
| 独立滤波 | FilterLow/High |
| 下载/清除 | **Load / Clear** |
| 事件上下文 | 从 Globe 地震 Review / Events 台站双击 / Mine 收藏事件 → 自动预填 |
| TauP | 自动计算 P/S；标注在波形上 |
| PSD/频谱 | PSD、Spectrogram 开关；FFT window；Log freq |
| ZRT | Rotate ZRT（需事件 + 台站坐标 + 水平分量） |
| 导出 | Export 菜单：PNG / CSV / QuakeML / Save catalog |
| 本地目录 | Mine → 双击目录条目重开 |
| 状态/数据量 | `Ready · mm:ss loaded` 或错误提示 |

### 2.8 Settings / Profile / 其他

| 功能 | 链路 |
|---|---|
| General | 齿轮 → General：语言、时区、地址、Auto-detect |
| My Shakes | 齿轮 → My Shakes：LAN Shake 增删改 |
| Reset | 齿轮 → Reset：清缓存/偏好/收藏/统计并重启 |
| Apply/Cancel | General/My Shakes；Reset 页已禁用 |
| Profile | 顶栏用户 → 统计 + 最近活动 + GitHub 登录 |
| 主题 | 顶栏主题按钮；图表/报告同步 |
| Kiosk | F11 进入；F11/Esc 退出（本轮已改为 ApplicationShortcut） |
| 报告 | File → Export HTML/PDF |
| 自动更新 | ❌ 尚未实现（roadmap 唯一待办） |

---

## 3. 实测结果（本轮）

| # | 链路 | 结果 |
|---|---|---|
| 1 | Globe 自转暂停/恢复 | ✅ paused class 切换 |
| 2 | Globe Devices/Quakes/Both | ✅ active class 切换 |
| 3 | Globe 1h/24h/7d/30d | ✅ 7d active 后回 24h |
| 4 | 相机 +/-/reset | ✅ 无 JS 错误 |
| 5 | 台站弹窗 Favorite | ✅ FavoritesStore 增加 IU.PAB |
| 6 | 台站弹窗 Monitor live → Connect/Stop | ✅ 台站入 combo；连接成功；停止正常 |
| 7 | 台站弹窗 View history | ✅ Replay 模式 + IU.PAB 预选 |
| 8 | 地震弹窗 Favorite | ✅ 收藏成功 |
| 9 | 地震弹窗 Review → picker → Replay | ✅ mode=1，event 预填 |
| 10 | Data Live 6h/24h + 图表 | ✅ active + 10 canvas |
| 11 | Data Analysis IS/1y/M3 Search | ✅ 19 events，10 canvas |
| 12 | Data → Events scope | ✅ tab 2 |
| 13 | Events Live 2000 行 + 最近台站 | ✅ 8 台站 |
| 14 | Events 收藏 Live/Historical | ✅ 2 收藏 |
| 15 | Historical 1y/IS/M4.5 Search | ✅ 5 events |
| 16 | 历史事件台站双击 → Replay | ✅ mode=1，event banner |
| 17 | Mine 收藏行 → picker → Replay | ✅ 2 行，打开成功 |
| 18 | Replay 下载 | ✅ 10:00 或 9:11（按数据可用性） |
| 19 | Replay PSD/Spectrogram 开关 | ✅ |
| 20 | Replay FFT 2s / Log freq | ✅ |
| 21 | Replay CSV/PNG 导出 | ✅ 文件落盘 |
| 22 | Replay Save catalog（有 P/S） | ✅ 目录 1 条 |
| 23 | Workbench 滤波/预设 | ✅ 低 1.0 高 10.0 |
| 24 | Freeze + P/S + Clear | ✅ picks 生成/清空 |
| 25 | Live FFT 2s/Log/Spectrogram 开关 | ✅ |
| 26 | 24h/Hodogram | ✅ 子页切换 |
| 27 | MMI chip 出现 + 点击 | ✅ |
| 28 | Stop 后等待 5s | ✅ 不再 segfault |
| 29 | 连续 3 次 Connect/Stop | ✅ 无崩溃 |
| 30 | 带活动流关闭窗口 | ✅ 清理正常 |
| 31 | Events 过滤（M≥5 + 文本 Japan） | ✅ 2000→169→7 |
| 32 | Events → Data scope | ✅ tab 1 |
| 33 | Kiosk F11/Esc | ✅ 进入/退出 |
| 34 | 报告 HTML | ✅ 24–25 KB |
| 35 | Settings 直接打开 3 tabs | ✅（自动化齿轮路径受 macOS 激活影响） |
| 36 | Profile 统计/活动 | ✅ |

---

## 4. 本轮修复的真实缺陷

### 4.1 Stop 时 SIGSEGV（严重）

- 复现：连接 IU.PAB → Stop → 等待 500 ms，进程 `Segmentation fault: 11`。
- 堆栈：`QThread` 析构 + `QObjectWrapper::destroy`，主线程 posted events。
- 根因：`SeedLinkSource.stop()` 同时把 worker/thread 连接到 `deleteLater`，又让 Python 包装器在 `_on_thread_finished` 后 GC；QThread 所有权双重释放。与平滑预填充无关（禁用 prefill 仍复现）。
- 修复：移除 `thread.finished -> worker.deleteLater/thread.deleteLater`；由 source 在 `_on_thread_finished` 后安全释放两个 Python 持有的 QObject。
- 验证：Stop 后等待 5 s、连续 3 次 Connect/Stop、带活动流关闭窗口全部无崩溃。

### 4.2 Workbench 置顶时弹窗跑到后面

- 复现：Workbench 已打开 → Globe 地震 Review（或台站 Monitor live / Settings）→ 选择台站对话框不出现，后续 settings/profile 被阻塞。
- 根因：`QMessageBox/QInputDialog` 以 MainWindow 为 parent；Workbench 是独立顶层窗口且在最前。
- 修复：新增 `_dialog_parent()`，Workbench 可见时把台站/地震/Review 选择器/Settings/Profile/GitHub 登录的 parent 设为 Workbench。
- 验证：Pro 可见时 Review → picker → Replay mode=1；Settings/Profile 在 Pro 可见时正常。

### 4.3 Kiosk F11/Esc 在焦点不在主窗时失效

- 根因：`QShortcut` 默认 `WindowShortcut`，Workbench/WebEngine 获得焦点时不触发；Esc 也无法退出。
- 修复：改为 `Qt.ApplicationShortcut` 并保留 shortcut 引用。
- 验证：F11 进入（kiosk=True，header 隐藏），Esc 退出（header 恢复）。

---

## 5. 自动化限制（不是产品故障）

1. **WebGL 地图标记命中**：ECharts-GL scatter3D 的 `convertToPixel` 不返回屏幕坐标，DOM `click` 无法命中标记；本轮通过同一个 `GlobeBridge.station_clicked/earthquake_clicked` 入口打开弹窗，弹窗内按钮全部真实点击。真实鼠标点击在手动桌面测试可用；建议后续加“台站搜索/最近台站列表”作为键盘可访问入口。
2. **macOS 原生模态窗口**：自动化中 Settings 齿轮点击有时进入无可见 dialog/主窗隐藏的状态；直接构造 SettingsDialog 可正常显示三页签。需要在真实桌面再点一次齿轮确认（本轮未能把该自动化路径判为产品失败）。
3. **音频设备/麦克风**：Listen 链未做实际声音输出验证；录音列表需要 STA/LTA 触发后才有内容。
4. **LAN Shake**：AddShakeDialog 本轮未连真实 rs.local 设备。
5. **GitHub OAuth / Onboarding**：需要浏览器/首次运行状态，本轮未重走。

---

## 6. 仍可完善的空间（按优先级）

| 优先级 | 空间 | 建议 |
|---|---|---|
| **P0** | 平滑播放带来的 12 s 视觉延迟 | 若用户更重视低延迟，增加 “Smooth / Realtime” 开关；当前默认平滑，检测/MMI 仍实时 |
| **P1** | Workbench 初始 `Mi Shake LAN (rs.local)` 假台站 | 改为“未选择台站”占位，Connect 禁用，引导从地图/事件添加 |
| **P1** | 地图标记点击目标小、无搜索 | 加台站搜索/最近台站面板；增大标记点击半径；键盘可达 |
| **P1** | Replay “Save catalog / QuakeML” 在无 P/S 时仍可点 | 无 picks 时禁用并在 tooltip 说明“先放 P/S”；有 picks 后启用 |
| **P1** | Rotate ZRT 禁用时原因不明确 | tooltip/状态说明“需要事件 + 台站坐标 + 水平分量”；POHA 这类垂直-only 台站应明确提示 |
| **P1** | 历史/回放数据不足（9:11 / 10:00） | 状态明确“请求 10:00，实际 9:11”，或允许重试/换台站 |
| **P2** | 台站 Favorite 点击后无 toast | 收藏/取消后状态栏反馈；My collection 徽标 |
| **P2** | 报告只有菜单入口 | Data 页加显式 “Export report” 按钮；PDF 走同一入口 |
| **P2** | Settings 齿轮的自动化不稳定 | 真实桌面回归；可加 `dlg.raise_()`/`activateWindow()` 与窗口可见性检查 |
| **P2** | 无自动更新 | manifest + 通知 + 应用内下载校验；签名/回滚后再做 L2 |
| **P2** | Onboarding/GitHub/LAN Shake 未重走 | 单独用临时 HOME + 首次运行脚本覆盖 |

---

## 7. 验证与提交

- `pytest -q`：**583 passed**。
- `ruff check .`：clean。
- `compileall`：OK。
- 本轮代码修复：`SeedLinkSource` teardown、`_dialog_parent`、kiosk ApplicationShortcut。
- 建议连同 `docs/smooth-live-waveform.md`、`docs/ui-review-round3.md` 一起阅读。
