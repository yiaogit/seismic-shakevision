# SeismicGuard — 重构方案(全项目扫描 + 拆分设计)

> 目标:把 `main_window.py`(1663 行 god-object)瘦身为"外壳",抽出
> Workbench 实时流水线;同时做几处低风险优化。行为**完全不变**。
> 基线:`main` @ 0.7.6.1(+ 已完成的 0.7.7 修复)。

---

## 1. 扫描结论

### 各层体量
| 层 | 总行数 | 最大文件 |
|---|---|---|
| `ui/` | 13053 | **main_window.py 1663**(离群),dashboard_view 814,app_header 780 |
| `services/` | 4918 | github_auth 551,favorites_store 452 |
| `sources/` | 1253 | seedlink 563 |
| `processing/` | 1386 | buffer 263,intensity 260 |

`ui/` 占全项目一半,`main_window.py` 是唯一的离群点。其余文件虽有 700+
但职责单一,本方案不动。

### 关键架构事实(决定了拆分可行)
1. **`ProWindow` 已经是纯视图**:它持有各面板 widget(control_panel、
   waveform/spectrogram/helicorder/particle/replay_panel、intensity_card),
   但**不持有** source/buffer/timer——文件头注释明确写了
   "NO posee ni source ni buffer ni timer; vive en MainWindow"。
2. **流水线状态全在 `MainWindow`**:`_source / _buffer / _processor /
   _spectrum_computer / _detector / _recorder / _audio_player /
   _refresh_timer / _helicorder_timer / _spectrum_frame_skip /
   _intensity_smoother / _current_station`。
3. **ProWindow 重新发射控制信号**:`station_changed / filter_changed /
   trigger_changed / connect_clicked / disconnect_clicked / listen_clicked`,
   MainWindow 连到 **ProWindow 的**信号(不是直连 control_panel),
   所以 wiring 已经和具体面板解耦。
4. **16 个编排方法**(L522–945,约 430 行)就是把上面的状态串起来驱动
   ProWindow 的面板。它们对"外壳"的依赖很少,只有:
   - `self._status_bar.showMessage(...)`(×20)
   - `self._latency_label.setText(...)`(×3)
   - `self.app_header.set_station(...)`、`self._connection_label`
   - `self.intensity_card.update_from_snapshot/reset`
   - `self._config.*` 只读
   - `self.pro_window.is_*_subtab_visible()` 视图查询
5. **影响面极小**:全项目只有 `__main__.py` 一处 `import MainWindow`;
   `tests/` 里**没有**任何测试直接构造 `MainWindow`——这既说明改动 blast
   radius 小,也说明这条流水线目前**根本没被单元测试覆盖**(正是抽出来的
   最大动机:抽成独立 `QObject` 后可脱离 GUI 单测)。

---

## 2. 核心重构:抽出 `WorkbenchController`

> ✅ **状态:已在 v0.7.7 执行完成。** 16 个方法 + 流水线状态已全部搬入
> `shakevision/ui/workbench_controller.py`;`main_window.py` 1663 → 1105 行。
> compile + ruff 全过,但**完整 GUI 行为需在本机 `pytest -q` 验证**。
> 下面保留原始设计供参考/复查。

### 设计
新建 `shakevision/ui/workbench_controller.py`:

```python
class WorkbenchController(QObject):
    """拥有实时波形流水线;驱动一个 ProWindow 视图。

    不引用任何外壳 widget——通过信号把外壳级 UI 更新发出去,
    由 MainWindow 接线。这样 controller 可脱离 GUI 单测。
    """

    # → 外壳级 UI 更新(MainWindow 接线到 status_bar / header / label)
    status_message    = Signal(str, int)      # texto, msec
    latency_changed   = Signal(float)
    station_changed   = Signal(str)           # etiqueta para el header
    connection_state  = Signal(object)        # ConnectionState

    def __init__(self, config, view: "ProWindow", parent=None): ...
```

**移入 controller 的状态**(从 MainWindow 搬走):
`_source、_buffer、_processor、_spectrum_computer、_detector、_recorder、
_audio_player、_refresh_timer、_helicorder_timer、_spectrum_frame_skip、
_intensity_smoother、_current_station`。

**移入 controller 的 16 个方法**:
`_on_station_changed、_on_filter_changed、_on_trigger_changed、
_on_connect_clicked、_on_disconnect_clicked、_start_source_for、
_stop_source、_on_data_ready、_on_source_status、_on_refresh_tick、
_on_listen_clicked、_on_playback_started/finished/failed、
_on_event_triggered、_on_event_released`。

**通信改造**(机械替换,逐处):
- `self._status_bar.showMessage(t,ms)` → `self.status_message.emit(t,ms)`
- `self._latency_label.setText(x)`     → `self.latency_changed.emit(...)`
- `self.app_header.set_station(s)`      → `self.station_changed.emit(s)`
- `self.intensity_card.X`               → `self.view.intensity_card.X`
  (intensity_card 属于 ProWindow 视图,直接走 view)
- 面板推送 `self.pro_window.waveform_panel...` → `self.view.waveform_panel...`
- `self._config.*` → controller 自己持有的 `self._config`

### MainWindow 改造后
```python
self._workbench = WorkbenchController(config, view=self.pro_window)
# 把 ProWindow 的控制信号接到 controller
self.pro_window.station_changed.connect(self._workbench.on_station_changed)
# … 其余 5 个信号同理 …
# 把 controller 的外壳级信号接回外壳 widget
self._workbench.status_message.connect(self._status_bar.showMessage)
self._workbench.latency_changed.connect(self._on_latency)
self._workbench.station_changed.connect(self.app_header.set_station)
```
MainWindow 从 1663 行降到约 1100~1200 行,回归"外壳"角色。

### 风险与缓解
- **风险**:这 16 个方法共享状态密集;ProWindow 关闭时会销毁/重建面板
  (CLAUDE.md 警告),controller 持有 view 引用需在重建时同步。
- **缓解**:① 纯搬移、**零行为改动**;② 每步 `compileall + ruff`;
  ③ **必须在本机** `pytest -q` 全绿;④ 新增 controller 的单测(mock view),
  把这条原本零覆盖的流水线纳入测试;⑤ 拆成下面的小步,每步独立可回滚。

### 分步执行(每步可单独提交 + 本机测试)
1. 新建 `workbench_controller.py` 空壳 + 4 个信号 + `__init__` 接收
   `config, view`。先不搬方法,MainWindow 仍照旧 —— 编译通过。
2. 搬"音频回放"小簇(`_on_listen_clicked` + 3 个 `_on_playback_*` +
   `_audio_player`)到 controller,MainWindow 转发。最小、最独立,先验证范式。
3. 搬"数据流 + 刷新"(`_on_data_ready/_on_source_status/_on_refresh_tick`
   + `_buffer/_processor/_spectrum_computer/_spectrum_frame_skip`)。
4. 搬"source 生命周期"(`_start_source_for/_stop_source/_on_connect/
   _on_disconnect` + `_source/_refresh_timer/_helicorder_timer`)。
5. 搬"控制变更 + 事件触发"(`_on_station/filter/trigger_changed`、
   `_on_event_triggered/released` + `_detector/_recorder`)。
6. 删除 MainWindow 里搬空的状态、清理 import,收尾。
7. 新增 `tests/test_workbench_controller.py`(mock view + fake source)。

---

## 3. 其它低风险优化(可独立做)

| 编号 | 内容 | 风险 |
|---|---|---|
| **O1** | 报告导出:`_on_export_report`(HTML)与 `_on_export_report_pdf`
  共享"无数据守卫 + lazy ReportGenerator + 台站标签 + quake 过滤",抽
  `_prepare_report_context()` 私有方法去重 | 低,纯函数提取 |
| **O2** | `_period_seconds / _period_label / _filter_for_period` 这组纯函数
  与 Qt 无关,可移到 `services/` 或 `utils/` 成模块级函数,便于单测 | 低 |
| **O3** | main_window 里仍有内联 `logging.getLogger(__name__)`(2 处),
  统一用 0.7.7 新增的模块级 `logger` | 极低 |
| **O4** | `_max_positional` 等若多处复用,signal_safety 已可作为通用工具 | — |

---

## 4. 建议执行顺序与定位

- **0.7.7(当前 patch)**:只做 O1/O3 这类零风险微优化(可选)。
- **0.8.0(专门版本)**:做第 2 节的 `WorkbenchController` 抽取 + O2 +
  controller 单测。**必须本机 pytest 全绿**逐步推进,不与其它功能混提交。

> 说明:沙箱环境缺 libEGL 且无法 sudo,跑不了 PySide6 GUI 测试套件。
> 因此第 2 节的拆分虽设计完备,真正执行/验证应在能跑 `pytest -q` 的
> 本机进行;Cowork 这边可以先把不依赖 GUI 运行期的部分(空壳、纯函数、
> 单测脚手架)写好并 `compileall + ruff` 验证。
