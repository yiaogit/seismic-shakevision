# 市面专业地震软件调研:功能与使用方式

> 目的:为 SeismicGuard 工作台的定位与改进提供参照。
> 按"操作/网络级 → 分析/研究级 → 监测/教学级"三档梳理,末尾给出共性功能
> 与本项目的定位映射。来源见文末。

---

## 1. 操作 / 台网级(实时台网运行 + 人工复核)

### SeisComP(gempa / GFZ,免费核心 + 商业模块)
许多国家台网的运行骨干。两个核心 GUI:

* **scrttv** — 实时波形浏览器:看多台站实时波形、连续频谱图,可**回溯浏览任意
  历史时段**,做快速震相关联,把未知事件加入系统;内置最简的关联器 + 手动定位,
  可把"选中并关联的震相"提交为初步定位。
* **scolv** — 事件处理工作台:**震相拾取器**(极性、不确定度、谱/谱图)、
  **定位**(关联台站、彩色残差、射线路径、残差-距离/方位图)、**震级计算**
  (配振幅波形复核)、震源机制解。
* 用法:自动检测/定位 → 分析员在 scolv 里复核震相、重定位、定震级 → 入库。

### Antelope / Datascope(BRTT / Kinemetrics,商业)
实时采集 + 处理一体。自动事件检测、到时拾取、定位、震级;`dbpick` 直接在连续
数据上人工分析。强在关系型数据库(Datascope)管理海量连续数据。

### Earthworm + Winston(免费)
实时数据采集/分发的"管道"层(很多软件的数据后端)。Winston Wave Server 提供
SeedLink 缓冲 + 磁盘历史数据;SWARM 等前端从它取数。

---

## 2. 分析 / 研究级(单/多事件深度分析)

### Snuffler(Pyrocko,免费,Python)
"snappy 的地震图浏览器 + 工作台"。读 MiniSEED/SAC 等;浏览海量波形档案、也接
实时流;**流畅的缩放/平移/滚动/滤波/旋转(ZNE↔ZRT)/缩放**;内置手动拾取器,
三类标记(普通/震相/事件);算走时;**可用 Python 写插件(snufflings)扩展**。
交互体验是同类标杆。

### ObsPyck / StreamPick / wavePicker(免费,ObsPy)
观测台标准事件分析流程的 GUI。连 FDSNWS/ArcLink/SeedLink/SDS,**自动抓波形 +
元数据(仪器响应、台站坐标)**;设 P/S 及自定义震相;标振幅极值算震级;**导出
QuakeML**。是"ObsPy 能力 + 拾取 UI"的代表。

### SeisAn(免费,Univ. Bergen,数十年标准)
完整观测台工作流:**光标/手动拾取震相、定位、编辑事件、谱参数、地震矩、
三分量定方位角、画震中**;还含 coda Q、合成、地震危险性等研究模块。EEV 命令式
事件浏览是其经典工作方式。

### SAC(Seismic Analysis Code,IRIS,免费)
研究界处理时间序列的"通用语"。命令/脚本驱动:算术、FFT、三种谱估计、IIR/FIR
滤波、叠加、抽稀、插值、相关、**震相拾取**、强大绘图。偏批处理/脚本而非实时。

---

## 3. 监测 / 教学 / 消费级(实时看波形,本项目所在档)

### SWARM(USGS VSC,免费,Java)
**和本项目最可比**。实时显示+分析波形;数据源:Earthworm/Winston、**SeedLink**、
**FDSN Web Services**、波形文件;时域+频域工具 + 地图;**全屏 kiosk 监测模式**;
**4 种波形视图:标准波形、频谱(spectra)、频谱图(spectrogram)、质点运动
(particle motion)** —— 这正是本项目已有的那套。Raspberry Shake 用户常用它
(经 Winston,端口 16032)。

### Raspberry Shake 生态
* **ShakeNet**(官方 App,全平台):看波形、频谱、地震。
* 经 **SWARM** 接 OSOP/Winston;经 **jAmaseis** 接实时数据。

### jAmaseis(IRIS,免费,Java,教学向)
连本地/远程教育地震仪或 IRIS DMC 的实时数据,实时显示波形。面向课堂。

---

## 4. 共性"专业功能"清单(把上面提炼成需求)

| 功能 | 谁有 | 本项目现状 |
|---|---|---|
| 多源接入(SeedLink/FDSN/Winston/文件) | 普遍 | 部分(SeedLink + IRIS dataselect 回放) |
| **自由缩放/平移/滚动浏览任意时段** | Snuffler/scrttv/SWARM/SAC | ❌(只实时滚动窗) |
| **震相拾取 P/S(+不确定度/极性)** | scolv/Snuffler/ObsPyck/SeisAn/SAC | ❌ |
| **测量游标(时间/振幅、S-P)** | 全部分析级 | ❌ |
| **去仪器响应 → 物理单位** | scolv/ObsPyck/SeisAn/SAC | ❌(原始 counts) |
| **振幅 → 震级** | scolv/ObsPyck/SeisAn/Antelope | ❌(只显示 USGS 目录震级) |
| 滤波(交互/多带/旋转 ZNE↔ZRT) | 普遍 | 部分(全局带通,无旋转) |
| 频谱 / 频谱图 / PSD | SWARM/scolv/SAC | 部分(幅度谱图,无 PSD) |
| 质点运动 / 极化 | SWARM | ✅(可视化,无反方位角读数) |
| Helicorder | SWARM/普遍 | ✅ |
| 多台站定位 | scolv/Antelope/SeisAn | ❌(且 GSN 稀疏,价值有限) |
| 走时曲线 / 理论到时 | Snuffler/scolv | ❌ |
| 事件目录 + QuakeML 导出 | scolv/ObsPyck/SeisAn | ❌(只存 MiniSEED) |
| 地图 | SWARM/scolv | ✅(3D 地球) |
| kiosk/监测模式 | SWARM | 部分 |
| 插件 / 脚本扩展 | Snuffler/SAC/ObsPy | ❌ |

**三种典型使用方式**:
1. **交互 GUI**(SWARM、scrttv/scolv、Snuffler、ObsPyck、dbpick、SeisAn EEV)——
   鼠标拾取/测量/复核,本项目应向这一类靠。
2. **命令 / 脚本**(SAC、ObsPy、Earthworm 配置)——批处理/研究复现。
3. **自动 + 人工复核**(SeisComP、Antelope)——台网生产线。

---

## 5. 本项目(SeismicGuard)定位映射

* **现在所处档位 = SWARM / ShakeNet / jAmaseis(实时监测 + 可视化)。**
  而且 SWARM 的"4 种波形视图(波形/谱/谱图/质点运动)"本项目已全部具备,
  helicorder、3D 地图、声化甚至更丰富、UI 打磨度更高。
* **要往"分析级"(Snuffler / ObsPyck / SeisAn)迈进,缺的正是它们的共性内核**:
  自由浏览 + 交互拾取/测量 + 去仪器响应/物理单位 + 震级 + QuakeML 导出。
* **可直接借鉴的范式**:
  - 交互手感 → 学 **Snuffler**(缩放/平移/滤波/旋转/拾取一体,插件化)。
  - 观测台工作流 → 学 **ObsPyck**(自动抓响应元数据、P/S 拾取、振幅→震级、
    QuakeML 导出)——而且它也基于 ObsPy(本项目已依赖),路径最短。
  - 监测呈现 → 已对标 **SWARM**,继续保持优势(主题/i18n/声化/地球)。

**一句话**:本项目在"监测/呈现"这一档已做到同类领先;真正的专业化跃迁,是把
**Snuffler 的交互拾取/测量** + **ObsPyck 的响应去除/震级/QuakeML** 这两套
"分析内核"补进工作台(均可在已有的 pyqtgraph + ObsPy 上实现)。

---

## 来源

- SWARM(USGS):https://www.usgs.gov/software/swarm ; https://github.com/usgs/swarm
- SeisComP scrttv:https://www.seiscomp.de/doc/apps/scrttv.html ; scolv:https://www.seiscomp.de/doc/apps/scolv.html
- Snuffler / Pyrocko:https://pyrocko.org/docs/current/apps/snuffler/manual.html
- SeisAn:https://seisan.info/ ; https://pub.geus.dk/en/publications/seisan-earthquake-analysis-software-background-capabilities-recen/
- SAC(IRIS):https://ds.iris.edu/files/sac-manual/manual/intro.html
- ObsPyck:https://github.com/megies/obspyck ; StreamPick:https://github.com/miili/StreamPick
- Antelope / Datascope:https://pal.auckland.ac.nz/antelope-datascope-access-process/
- Raspberry Shake / Winston / jAmaseis:https://manual.raspberryshake.org/traces.html
