# Dashboard professionalization — design & build guide

> Source of truth for turning the **Data** dashboard from a lay overview into a
> professional **seismicity analysis** view, plus the matching PDF report.
> Read before touching `web/dashboard/`, `ui/dashboard_view.py`,
> `processing/seismic_stats.py` or `services/report.py`.

## 1. Decisions (locked, user)

* **Keep the lay overview**; add a **Professional / Analysis layer** (toggle),
  mirroring the Standard/Pro layer split — don't scare non-experts with a
  b-value plot by default.
* **Decouple the data source**: the dashboard must analyze an arbitrary
  **region + time window** (via the `fdsnws-event` historical query we already
  built), not only the rolling live feed (≤1 month). Live = monitor recent;
  Analysis = study a chosen catalog.
* **Pro charts (all four):** Gutenberg–Richter / b-value, cumulative count +
  energy release, Omori aftershock decay, enhanced depth / spatial section.
* **PDF = snapshot of the current analysis**: parameters (region / window / Mc /
  b) + GR + energy release + depth + top events + map.

## 2. Statistics (pure, `processing/seismic_stats.py`, tested in sandbox)

Methods chosen (standard seismology):

* **Magnitude of completeness Mc** — *maximum curvature (MAXC)*: the magnitude
  bin with the peak of the non-cumulative FMD, with the common **+0.2**
  correction. Simple, robust enough for a UI.
* **b-value / a-value** — *Aki–Utsu maximum likelihood*:
  `b = log10(e) / (mean(M≥Mc) − (Mc − ΔM/2))`, with **Shi & Bolt (1982)**
  uncertainty. `a` from `log10 N(≥Mc) + b·Mc`.
* **FMD** — cumulative `N(≥M)` and non-cumulative `n(M)` per `ΔM=0.1` bin (for
  the GR plot).
* **Seismic moment** `M0 = 10^(1.5·Mw + 9.1)` N·m (Hanks & Kanamori).
* **Energy** `log10 E = 1.5·M + 4.8` J (Gutenberg–Richter).
* **Cumulative series** — events sorted by time → cumulative count and
  cumulative `M0` (energy-release curve).
* **Omori** — aftershock rate `n(t) = K / (t + c)^p` fit (least-squares over
  binned rate; needs `scipy.optimize`). Modest: returns K, c, p or `None` if it
  can't fit.
* **Depth** — histogram + percentiles; lat/depth pairs for a cross-section.

All pure (numpy/scipy, no Qt) → unit-tested headless. obspy NOT required.

## 3. Build stages

1. **Stats core** (`seismic_stats.py`) + pytest. *(this stage, testable)*
2. **Pro analysis layer** in `web/dashboard/` (ECharts): GR/b, energy release,
   Omori, depth section, behind a Summary/Advanced/**Professional** toggle.
   i18n ×4. *(node --check only; validate on machine)*
3. **Decouple data source**: `build_payload` accepts an external dataset; a
   region-preset + window picker drives an `fdsnws` query → analysis layer.
4. **PDF**: `report.py` exports the current analysis snapshot.
5. **Verify** + CHANGELOG.

## 4. Gotchas

* ECharts/Qt/web can't run in the sandbox → JS via `node --check`, charts
  validated on the user's machine.
* b-value is only meaningful **above Mc** and with enough events (guard small
  N: return `None`/hide the chart, don't show a garbage b).
* Large historical queries are slow/big → reuse the threaded `fdsn_worker`;
  respect the 20 000 cap.
* Keep the lay overview untouched by default; the pro layer is opt-in.
