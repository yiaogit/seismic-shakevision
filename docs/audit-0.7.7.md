# SeismicGuard 0.7.7 — 代码体检报告

> 范围:Bug 审查、翻译文字审查、代码结构优化分析
> 基线:`main` @ `8fc6761`,版本 `0.7.6.1`
> 方法:ruff lint + compileall + 静态审查(沙箱无法跑 PySide6 GUI 测试套件)

---

## 概览

| 维度 | 结论 | 严重度 |
|---|---|---|
| Lint / 编译 | 干净(仅 1 个脚本 F541) | 🟢 |
| 生命周期(dead C++ 守卫缺失) | 系统性缺失,22 处订阅点仅 1 处已修 | 🔴 高 |
| 主题(import 时冻结颜色) | 连接状态色切主题不更新 | 🟡 中 |
| 翻译一致性 | key/占位符完美对齐,无漏译 | 🟢 |
| 死 i18n key | ~18 个真死 key(与 CLAUDE.md 说法不符) | 🟡 低 |
| 代码结构 | `main_window.py` 为 god-object | 🟡 中(技术债) |

---

## 一、Bug 审查

### 🔴 B1 — dead C++ object 守卫系统性缺失(高)

CLAUDE.md §4 明确要求:订阅全局单例信号的槽,必须 `try/except RuntimeError`
防护,并通过 `self.destroyed` 断开,避免 pytest-qt teardown 时
"Internal C++ object already deleted" 级联(v0.7.6 后曾因此挂掉 12 个
test_report)。

现状:全仓 **约 30 处** widget 方法订阅 `LocaleService.language_changed_signal()`
/ `ThemeManager.changed_signal()` / `LayerModeManager` / `FavoritesStore` /
`ShakePresetStore` / `ActivityLog` 等长生命周期单例,**但只有
`loading_overlay.py`(v0.7.6.1 修过)做了 destroyed 断开 + RuntimeError 守卫**。
其余 22 个文件全部裸连接:

```
add_shake_dialog  app_header  control_panel  dashboard_view  github_login_dialog
globe_view  helicorder_widget  intensity_card  main_window(41 处 connect)
onboarding_wizard  particle_motion_widget  pg_theming  pro_window
profile_dialog  profile_view  replay_panel  settings_dialog
spectrogram_widget  theme_manager  waveform_widget …
```

风险更高的是 lambda 订阅(例如 `app_header.py:265`
`changed_signal().connect(lambda _t: self._refresh_themed_assets())`、
`main_window.py:254`),lambda 捕获 self、无法按引用断开,既延长 widget
生命周期,又会在 C++ 对象已删后被触发。

**建议**:沿用 `loading_overlay.py` 的范式做一个 mixin 或小工具
(`subscribe_singleton(signal, slot, owner)`),统一:绑定方法槽 + 在
`owner.destroyed` 时 disconnect + 槽内 `try/except RuntimeError`。逐文件迁移,
每迁一个跑该区域的 `pytest tests/test_<area>.py`。这是 0.7.7 最该做的一项。

### 🟡 B2 — 连接状态颜色在 import 时被冻结(中)

`ui/app_header.py:91` 的 `_STATE_COLORS` 字典在 **模块 import 时** 用
`COLOR_TEXT_MUTED / COLOR_ACCENT_WARM / COLOR_OK` 求值。但
`apply_theme()` 是在运行时重写这些模块级 `COLOR_*` 全局量的
(CLAUDE.md §4)。结果:`line 179 color = _STATE_COLORS[state]` 始终读到
启动时那套颜色,**切换主题后连接状态指示器/文字颜色不更新**。

**修复**:把 `_STATE_COLORS` 改成在使用点(`_set_status` 内)实时
`from shakevision.ui import theme as _t` 读取 `_t.COLOR_OK` 等,而非模块级常量。
小改动,低风险。同类 import-time 读色需在 `app_header.py` 顺带排查。

### 🟢 B3 — 7 处 `except Exception: pass`(低,多为有意)

集中在 `main_window.py`(metrics/usage 相关,注释标了"métricas nunca
rompen UI")。属可接受的防御性吞异常,但建议至少 `logger.debug(...)`
留痕,避免真异常被静默吞掉。非阻塞。

---

## 二、翻译文字审查

整体质量**很好**,核心指标全绿:

- **Key 结构完美对齐**:en/es/fr/zh 各 450 个扁平化 key,两两 diff = 0,
  无缺漏、无多余。
- **占位符零不一致**:`{var}` / `{x:.3g}` / `%s` 在四语言中完全一致(0 处不匹配)。
- **无真实漏译**:ASCII 启发式报的"可疑"全是误报 —— 单位/格式串
  (`PGV … MMI …`)、专有名词(`Raspberry Shake`、`USGS / IRIS`、`PAGER`)、
  以及本身即法语的同形词(`Station`、`Pause`、`Magnitude`、`Violent`)。
- **无引用不存在的 key**:`t("字面量")` 静态扫描 + 动态前缀
  (`intensity.level.{n}`、`intensity.desc.{n}`、`activity.{kind}`)核对后,
  唯一命中 `status.connecting` 仅是 `i18n/__init__.py` 的 docstring 示例,非真调用。

### 🟡 T1 — ~18 个死 key(低)

确认全仓(Python + web JS)零引用的 key(注:所有 key 经
`globe_view.push_i18n()` 整表推给 webview,故 web.* 已交叉核对 web JS):

```
common.ok / common.yes / common.no / common.cancel / common.close
settings.status.applied / settings.status.language_changed / settings.status.timezone_changed
intensity.label.mmi / intensity.label.pgv
controls.sound.listen_playing
profile.tab_title
web.globe.controls.layer.both / .devices / .quakes
web.globe.controls.period / .rotate_play
web.globe.error.deps_missing
web.dashboard.error.cdn
```

四语言各一份,合计 70+ 死条目。CLAUDE.md §2 称 "死 key 已在 v0.7.6.1 清完",
**与此不符** —— 要么清理不彻底,要么这些是为计划中功能预留。建议:确认无在途
功能用到后,从 4 个 locale 一并删除,并同步更正 CLAUDE.md。

---

## 三、代码结构优化分析

### 🟡 S1 — `main_window.py` 是 god-object(中,技术债)

单个 `MainWindow` 类:**1656 行 / 49 个方法**,`__init__` 约 350 行
(L100–454),`connect()` 调用 41 处。职责混杂四块:

1. **Standard 壳**:侧栏导航、tab 切换、菜单、关于、Qt 事件。
2. **Workbench 编排**(最大可拆块,≈L517–945,~15 方法):station/filter/trigger
   控制、source 生命周期(start/stop)、数据流(data_ready/refresh_tick)、
   音频回放(listen/started/finished/failed)、事件触发(triggered/released)。
3. **Dashboard / Globe payload** 推送与各类回调。
4. **报告导出**(HTML + PDF,≈L1290–1420)。

**建议(增量、测试护航)**:
- 把第 2 块抽到一个 `WorkbenchController(QObject)`,由 MainWindow 持有并转发
  信号 —— 这是收益最大、边界最清晰的一刀。
- 把第 4 块报告导出抽到 `ui/report_actions.py` 或复用 `services/report.py`
  的薄封装。
- ⚠️ 高风险区:CLAUDE.md 警告 Pro 窗口会销毁/重建状态(buffers/helicorder),
  重构 source 生命周期时务必保持该语义。沙箱跑不了 GUI 测试,**任何结构改动
  都要在本机 `pytest` 全绿后再提交**,且建议拆成多个小 PR。

### 🟢 S2 — 其它

- `dashboard_view.py`(817)、`settings_dialog.py`(765)、`app_header.py`(764)、
  `onboarding_wizard.py`(763)偏大但职责单一,暂不急。
- `_on_export_report` 与 `_on_export_report_pdf` 有可提取的公共前置逻辑(选路径/
  组织数据),可小幅 dedup。

---

## 建议的 0.7.7 落地顺序

1. **B2 主题色冻结**:几行,立竿见影,先做。
2. **T1 死 key 清理**:删 4 个 locale + 更新 CLAUDE.md,纯文本低风险。
3. **B1 生命周期守卫**:做统一 `subscribe_singleton` 工具 + 逐文件迁移
   —— 本版最有价值,但工作量最大,建议本机 pytest 逐区域护航。
4. **B3 日志留痕**:顺带把 `except: pass` 加 `logger.debug`。
5. **S1 结构重构**:风险最高,建议**单独拆 PR / 甚至留到 0.8.0**,不要和上面
   的修复混在一个提交里。

> 发布流水线修复(`release.yml` 的 workflow_dispatch 不触发 publish)与
> 自动更新机制(推迟到 1.0.0 后)见此前讨论,未含在本报告。
