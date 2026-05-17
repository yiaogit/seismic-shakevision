/* ============================================================
   ShakeVision · Datos · Lógica de las 4 gráficas ECharts.
   ------------------------------------------------------------
   Recibe agregaciones pre-calculadas en Python a través de:

     window.shakevisionDashboard.setAggregations(payload)

   donde ``payload`` es un objeto con campos:

     {
       count_24h, max_magnitude, latest_iso, country_count,
       country_top10:    [{ name, count }, ...],
       magnitude_buckets: [{ label, count, color }, ...],
       depth_buckets:     [{ label, count }, ...],
       timeline_24h:      [{ ts, mag, place }, ...],
     }

   No realiza agregaciones por sí mismo: la lógica vive en Python para
   facilitar tests.
   ============================================================ */

(() => {
  // ─── i18n ───
  // Se actualiza con cada payload (campo ``i18n``). Por defecto vacío
  // → t() devuelve la clave misma, lo que es visible para debugging.
  let i18nTable = {};
  function t(key) {
    const v = i18nTable[key];
    if (v == null) return key;
    // Reemplazo sencillo de {var} si vienen extras
    if (arguments.length > 1) {
      const vars = arguments[1] || {};
      return v.replace(/\{(\w+)(?::[^}]*)?\}/g, (m, k) =>
        (k in vars ? vars[k] : m));
    }
    return v;
  }

  // Aplica los textos i18n a todos los nodos con data-i18n / data-i18n-title.
  // Se ejecuta cada vez que cambia la tabla de traducciones.
  function applyStaticI18n() {
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const key = el.getAttribute("data-i18n");
      if (i18nTable[key] != null) {
        el.textContent = i18nTable[key];
      }
    });
    document.querySelectorAll("[data-i18n-title]").forEach(el => {
      const key = el.getAttribute("data-i18n-title");
      if (i18nTable[key] != null) {
        el.title = i18nTable[key];
      }
    });
  }

  // ─── Zona horaria del usuario ───
  // Se actualiza con cada payload que llega del lado Python (campo
  // ``timezone``). Por defecto usamos la del navegador para evitar
  // un primer flash en UTC mientras se carga el primer payload.
  let userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  function formatLocalDateTime(ts_ms, opts) {
    // ts_ms: epoch milliseconds. Usa userTimezone + opciones del caller.
    try {
      const fmt = new Intl.DateTimeFormat(undefined, {
        timeZone: userTimezone,
        ...opts,
      });
      return fmt.format(new Date(ts_ms));
    } catch (e) {
      return new Date(ts_ms).toString();
    }
  }

  // Tema oscuro común para todas las gráficas
  const TEXT_PRIMARY   = "#fafafa";
  const TEXT_SECONDARY = "#a1a1aa";
  const TEXT_MUTED     = "#71717a";
  const ACCENT         = "#3b82f6";
  const ACCENT_2       = "#60a5fa";
  const PANEL_BG       = "#111111";
  const GRID_LINE      = "rgba(255,255,255,0.06)";

  const FONT_SANS = `"Inter Variable","Inter","-apple-system","SF Pro Text","Segoe UI Variable","Segoe UI","PingFang SC",sans-serif`;
  const FONT_MONO = `"JetBrains Mono","SF Mono","Monaco","Consolas","Menlo",monospace`;

  // Utilidad: opciones base que comparten todas las gráficas.
  function baseOption() {
    return {
      backgroundColor: "transparent",
      animation: true,
      animationDuration: 600,
      animationEasing: "cubicOut",
      textStyle: { fontFamily: FONT_SANS, color: TEXT_SECONDARY, fontSize: 12 },
      tooltip: {
        backgroundColor: "rgba(17,17,17,0.95)",
        borderColor: "rgba(255,255,255,0.08)",
        borderWidth: 1,
        textStyle: { color: TEXT_PRIMARY, fontSize: 12, fontFamily: FONT_SANS },
        extraCssText: "border-radius: 8px; box-shadow: 0 8px 28px rgba(0,0,0,0.5);",
      },
      grid: { left: 60, right: 24, top: 24, bottom: 36, containLabel: true },
    };
  }

  function axisStyle() {
    return {
      axisLine: { lineStyle: { color: TEXT_MUTED } },
      axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO, fontSize: 11 },
      splitLine: { lineStyle: { color: GRID_LINE } },
      axisTick: { lineStyle: { color: TEXT_MUTED } },
    };
  }

  // ============================================================
  // Crear las 4 instancias ECharts
  // ============================================================
  const chart_country = echarts.init(document.getElementById("chart-countries"), null, { renderer: "canvas" });
  const chart_mag     = echarts.init(document.getElementById("chart-magnitude"), null, { renderer: "canvas" });
  const chart_depth   = echarts.init(document.getElementById("chart-depth"), null, { renderer: "canvas" });
  const chart_time    = echarts.init(document.getElementById("chart-timeline"), null, { renderer: "canvas" });
  const chart_pager   = echarts.init(document.getElementById("chart-pager"), null, { renderer: "canvas" });
  const chart_trend   = echarts.init(document.getElementById("chart-trend"), null, { renderer: "canvas" });
  const chart_scatter = echarts.init(document.getElementById("chart-scatter"), null, { renderer: "canvas" });

  window.addEventListener("resize", () => {
    [chart_country, chart_mag, chart_depth, chart_time,
     chart_pager, chart_trend, chart_scatter].forEach(c => c.resize());
  });

  // ============================================================
  // Renders
  // ============================================================
  function renderCountries(data) {
    if (!data || data.length === 0) {
      chart_country.clear();
      return;
    }
    // Invertimos para que el "top 1" quede arriba en barras horizontales
    const items = [...data].reverse();
    chart_country.setOption({
      ...baseOption(),
      grid: { left: 100, right: 32, top: 8, bottom: 16, containLabel: true },
      xAxis: { type: "value", ...axisStyle() },
      yAxis: { type: "category", data: items.map(d => d.name), ...axisStyle() },
      series: [{
        type: "bar",
        data: items.map(d => d.count),
        barMaxWidth: 18,
        itemStyle: {
          color: { type: "linear", x: 0, y: 0, x2: 1, y2: 0,
                   colorStops: [
                     { offset: 0, color: ACCENT_2 + "33" },
                     { offset: 1, color: ACCENT },
                   ] },
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true, position: "right",
          color: TEXT_PRIMARY, fontFamily: FONT_MONO, fontSize: 11,
        },
      }],
    });
  }

  function renderMagnitude(buckets) {
    if (!buckets || buckets.length === 0) {
      chart_mag.clear();
      return;
    }
    chart_mag.setOption({
      ...baseOption(),
      xAxis: { type: "category", data: buckets.map(b => b.label), ...axisStyle() },
      yAxis: { type: "value", name: t("web.dashboard.axis.events"), nameTextStyle: { color: TEXT_MUTED }, ...axisStyle() },
      series: [{
        type: "bar",
        data: buckets.map(b => ({
          value: b.count,
          itemStyle: { color: b.color || ACCENT, borderRadius: [4, 4, 0, 0] },
        })),
        barMaxWidth: 36,
        label: {
          show: true, position: "top",
          color: TEXT_PRIMARY, fontFamily: FONT_MONO, fontSize: 11,
        },
      }],
    });
  }

  function renderDepth(buckets) {
    if (!buckets || buckets.length === 0) {
      chart_depth.clear();
      return;
    }
    chart_depth.setOption({
      ...baseOption(),
      xAxis: { type: "category", data: buckets.map(b => b.label),
               name: t("web.dashboard.axis.depth_km"), nameTextStyle: { color: TEXT_MUTED },
               nameGap: 28, ...axisStyle() },
      yAxis: { type: "value", name: t("web.dashboard.axis.events"), nameTextStyle: { color: TEXT_MUTED }, ...axisStyle() },
      series: [{
        type: "bar",
        data: buckets.map(b => b.count),
        barMaxWidth: 32,
        itemStyle: {
          color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
                   colorStops: [
                     { offset: 0, color: "#0ea5e9" },
                     { offset: 1, color: "#1d4ed8" },
                   ] },
          borderRadius: [4, 4, 0, 0],
        },
      }],
    });
  }

  // Color por bucket de magnitud (compartido scatter y burbujas)
  const colorForMag = m => {
    if (m < 3.0) return "#38bdf8";
    if (m < 4.5) return "#facc15";
    if (m < 6.0) return "#fb923c";
    if (m < 7.5) return "#ef4444";
    return "#a855f7";
  };

  // Modo "scatter" — vista clásica para ≤ 24 h.
  function renderTimelineScatter(events) {
    if (!events || events.length === 0) {
      chart_time.clear();
      return;
    }
    const points = events.map(e => ({
      value: [e.ts * 1000, e.mag],
      symbolSize: Math.max(6, e.mag * 3.5),
      itemStyle: { color: colorForMag(e.mag), opacity: 0.9 },
      place: e.place,
    }));

    chart_time.setOption({
      ...baseOption(),
      tooltip: {
        ...baseOption().tooltip,
        formatter: (p) => {
          const dt = formatLocalDateTime(p.value[0], {
            year: "numeric", month: "short", day: "2-digit",
            hour: "2-digit", minute: "2-digit", second: "2-digit",
            timeZoneName: "short",
          });
          return `<div><b>M ${p.value[1].toFixed(1)}</b></div>`
               + `<div style="color:${TEXT_SECONDARY}">${p.data.place || ""}</div>`
               + `<div style="color:${TEXT_MUTED};font-family:${FONT_MONO}">${dt}</div>`;
        },
      },
      xAxis: { type: "time", ...axisStyle() },
      yAxis: { type: "value", name: t("web.dashboard.axis.magnitude"),
               nameTextStyle: { color: TEXT_MUTED }, ...axisStyle() },
      series: [{
        type: "scatter",
        data: points,
        emphasis: { focus: "series" },
      }],
    }, true /* notMerge */);
  }

  // Modo "density" — vista de burbujas diarias para > 24 h.
  // Cada burbuja = un día con eventos; tamaño = nº eventos, color = mag máx.
  function renderTimelineDensity(buckets) {
    if (!buckets || buckets.length === 0) {
      chart_time.clear();
      return;
    }
    const maxCount = Math.max(1, ...buckets.map(b => b.count));
    const data = buckets.map(b => ({
      value: [b.ts, b.max_mag],
      // Tamaño ∝ √count para no aplastar valores extremos
      symbolSize: 10 + 26 * Math.sqrt(b.count / maxCount),
      itemStyle: { color: colorForMag(b.max_mag), opacity: 0.85 },
      raw: b,
    }));

    chart_time.setOption({
      ...baseOption(),
      tooltip: {
        ...baseOption().tooltip,
        formatter: (p) => {
          const day = formatLocalDateTime(p.value[0], {
            weekday: "short", year: "numeric",
            month: "short", day: "2-digit",
          });
          const b = p.data.raw;
          return `<div><b>${day}</b></div>`
               + `<div style="color:${TEXT_SECONDARY}">${t("web.dashboard.tooltip.events_max_mag", {count: b.count, max: b.max_mag})}</div>`
               + `<div style="color:${TEXT_MUTED};font-family:${FONT_MONO}">${t("web.dashboard.tooltip.mean_mag", {mean: b.avg_mag})}</div>`;
        },
      },
      xAxis: { type: "time", ...axisStyle() },
      yAxis: {
        type: "value", name: t("web.dashboard.axis.magnitude_max"),
        min: 0,
        nameTextStyle: { color: TEXT_MUTED }, ...axisStyle(),
      },
      series: [{
        type: "scatter",
        data,
        emphasis: { focus: "series", scale: 1.15 },
      }],
    }, true /* notMerge */);
  }

  // Dispatcher: el JS decide entre los dos modos según el campo
  // ``timeline_mode`` que viene del payload Python.
  function renderTimeline(payload) {
    const titleText = document.getElementById("timeline-title-text");
    const windowLabel = document.getElementById("timeline-window-label");
    const baseTitle = t("web.dashboard.chart.timeline");
    if (titleText) titleText.textContent = baseTitle;

    if (payload.timeline_mode === "density") {
      renderTimelineDensity(payload.timeline_density);
      if (windowLabel) {
        const days = Math.round((payload.period_seconds || 0) / 86400);
        windowLabel.textContent = t("web.dashboard.chart.timeline_density",
          {days: days});
      }
    } else {
      renderTimelineScatter(payload.timeline_24h);
      if (windowLabel) {
        const tlSec = Math.min(payload.period_seconds || 86400, 24 * 3600);
        windowLabel.textContent = t("web.dashboard.chart.timeline_window",
          {period: humanizePeriod(tlSec)});
      }
    }
  }

  // ============================================================
  // Avanzado · PAGER (radar)
  // ============================================================
  function renderPager(data) {
    if (!data || data.length === 0 || data.every(d => d.count === 0)) {
      chart_pager.clear();
      return;
    }
    const max = Math.max(5, ...data.map(d => d.count));
    chart_pager.setOption({
      ...baseOption(),
      grid: undefined,
      tooltip: { ...baseOption().tooltip, trigger: "item" },
      radar: {
        indicator: data.map(d => ({ name: d.label, max })),
        center: ["50%", "55%"],
        radius: "62%",
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
        splitArea: { areaStyle: { color: ["rgba(255,255,255,0.02)", "rgba(255,255,255,0.04)"] } },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.10)" } },
        axisName: {
          color: TEXT_PRIMARY, fontSize: 11, fontFamily: FONT_SANS,
          backgroundColor: "transparent",
        },
      },
      series: [{
        type: "radar",
        symbolSize: 6,
        lineStyle: { color: ACCENT, width: 2 },
        areaStyle: { color: "rgba(59,130,246,0.18)" },
        itemStyle: {
          color: (params) => data[params.dataIndex]?.color || ACCENT,
        },
        data: [{
          value: data.map(d => d.count),
          name: t("web.dashboard.series.pager"),
        }],
      }],
    });
  }

  // ============================================================
  // Avanzado · Distribución por periodo (histograma adaptativo)
  // ------------------------------------------------------------
  // El backend nos devuelve { bucket_label, buckets[{ts,count,max_mag}] }.
  // El ancho de la barra se elige según ``bucket_label`` para evitar
  // huecos visuales o solapamientos.
  // ============================================================
  function renderTrend(histogram) {
    const buckets = histogram?.buckets || [];
    const label = histogram?.bucket_label || "1 h";
    const trendLabel = document.getElementById("trend-bucket-label");
    if (trendLabel) {
      trendLabel.textContent = t("web.dashboard.chart.trend_bucket",
        {label: label});
    }
    if (buckets.length === 0) {
      chart_trend.clear();
      return;
    }
    const x = buckets.map(b => b.ts);
    const counts = buckets.map(b => b.count);
    const maxMags = buckets.map(b => b.max_mag || null);

    // Ancho de barra en píxeles según bucket. ECharts auto-ajusta si
    // pasamos null/auto, pero para histogramas largos queda mejor fijar.
    const barWidthByLabel = {
      "5 min": 4, "30 min": 6, "1 h": 8, "1 día": 14,
    };
    const barMaxWidth = barWidthByLabel[label] || 8;

    chart_trend.setOption({
      ...baseOption(),
      tooltip: {
        ...baseOption().tooltip,
        trigger: "axis",
        axisPointer: { type: "cross", crossStyle: { color: TEXT_MUTED } },
      },
      legend: {
        data: [t("web.dashboard.series.events_per", {bucket: label}),
               t("web.dashboard.series.max_mag")],
        textStyle: { color: TEXT_SECONDARY, fontSize: 11 },
        top: 4, right: 8,
      },
      xAxis: { type: "time", ...axisStyle() },
      yAxis: [
        { type: "value", name: t("web.dashboard.axis.events"),
          nameTextStyle: { color: TEXT_MUTED }, ...axisStyle() },
        { type: "value", name: t("web.dashboard.axis.magnitude_short"), min: 0, max: 9,
          nameTextStyle: { color: TEXT_MUTED }, ...axisStyle() },
      ],
      grid: { left: 50, right: 50, top: 32, bottom: 32, containLabel: true },
      series: [
        {
          name: t("web.dashboard.series.events_per", {bucket: label}),
          type: "bar",
          data: x.map((tx, i) => [tx, counts[i]]),
          itemStyle: { color: ACCENT_2 + "aa" },
          barMaxWidth,
          yAxisIndex: 0,
        },
        {
          name: t("web.dashboard.series.max_mag"),
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 6,
          data: x.map((tx, i) => [tx, maxMags[i]]),
          itemStyle: { color: "#fb923c" },
          lineStyle: { color: "#fb923c", width: 2 },
          connectNulls: false,
          yAxisIndex: 1,
        },
      ],
    }, true /* notMerge */);
  }

  // ============================================================
  // Filtro de región del radar PAGER (desplegable dentro del card)
  // ------------------------------------------------------------
  // Repoblamos las opciones cada vez que llega un payload (la lista de
  // regiones cambia con el periodo seleccionado). Se conserva el valor
  // actual si sigue existiendo; si desaparece, se vuelve a "all".
  // ============================================================
  function syncPagerRegionOptions(payload) {
    const sel = document.getElementById("pager-region-select");
    if (!sel) return;
    const previous = sel.value || payload.pager_region || "all";
    const regions = payload.region_options || [];
    const allLabel = t("web.dashboard.pager.select.all");
    const opts = [`<option value="all">${allLabel}</option>`]
      .concat(regions.map(r =>
        `<option value="${r.replace(/"/g, "&quot;")}">${r}</option>`));
    sel.innerHTML = opts.join("");
    // Conservar selección si sigue válida
    if (previous && [...sel.options].some(o => o.value === previous)) {
      sel.value = previous;
    } else {
      sel.value = "all";
    }
  }

  // ============================================================
  // Avanzado · Scatter profundidad × magnitud
  // ============================================================
  function renderScatter(points) {
    if (!points || points.length === 0) {
      chart_scatter.clear();
      return;
    }
    const PAGER_COLOR = {
      green: "#10b981", yellow: "#facc15",
      orange: "#fb923c", red: "#ef4444", null: TEXT_MUTED,
    };
    const data = points.map(p => ({
      value: [p.depth, p.mag],
      symbolSize: Math.max(6, p.mag * 2.6),
      itemStyle: { color: PAGER_COLOR[p.pager] || TEXT_MUTED, opacity: 0.85 },
      place: p.place,
    }));
    chart_scatter.setOption({
      ...baseOption(),
      tooltip: {
        ...baseOption().tooltip,
        formatter: (p) => {
          return `<div><b>M ${p.value[1].toFixed(1)}</b></div>`
               + `<div style="color:${TEXT_SECONDARY}">${p.data.place}</div>`
               + `<div style="color:${TEXT_MUTED};font-family:${FONT_MONO}">`
               + `${t("web.dashboard.tooltip.depth_km", {depth: p.value[0]})}</div>`;
        },
      },
      xAxis: {
        type: "value", name: t("web.dashboard.axis.depth_km"),
        nameTextStyle: { color: TEXT_MUTED },
        nameLocation: "middle", nameGap: 28,
        ...axisStyle(),
      },
      yAxis: {
        type: "value", name: t("web.dashboard.axis.magnitude"), min: 0,
        nameTextStyle: { color: TEXT_MUTED },
        ...axisStyle(),
      },
      series: [{ type: "scatter", data }],
    });
  }

  // ============================================================
  // KPI superiores + etiquetas dinámicas de periodo
  // ============================================================
  function humanizePeriod(seconds) {
    if (!seconds) return "24 h";
    if (seconds <= 3600) return "1 h";
    if (seconds <= 6 * 3600) return "6 h";
    if (seconds <= 24 * 3600) return "24 h";
    if (seconds <= 7 * 86400) return "7 d";
    return "30 d";
  }

  function renderKPIs(payload) {
    const periodSec = payload.period_seconds || 86400;
    const periodHuman = humanizePeriod(periodSec);

    // KPI "Sismos / 24h" — label dinámico via i18n
    const countLabelEl = document.getElementById("kpi-count-label");
    if (countLabelEl) {
      countLabelEl.textContent = t("web.dashboard.kpi.count", {period: periodHuman});
    }
    document.getElementById("kpi-count").textContent =
      Number(payload.count_24h || 0).toLocaleString();
    document.getElementById("kpi-max-mag").textContent =
      payload.max_magnitude != null ? `M ${payload.max_magnitude.toFixed(1)}` : "—";

    // País / estación: si tenemos summary mostramos S/U conteos
    const countriesEl = document.getElementById("kpi-countries");
    if (payload.station_summary && payload.station_summary.total > 0) {
      const s = payload.station_summary;
      countriesEl.textContent = `${payload.country_count || 0} · ${s.shakenet}S/${s.usgs}U`;
    } else {
      countriesEl.textContent = Number(payload.country_count || 0).toLocaleString();
    }

    if (payload.latest_iso) {
      const dt = new Date(payload.latest_iso);
      const minsAgo = Math.max(0, Math.round((Date.now() - dt.getTime()) / 60000));
      document.getElementById("kpi-latest").textContent = minsAgo < 60
        ? t("web.dashboard.minutes_ago", {n: minsAgo})
        : t("web.dashboard.hours_ago", {n: (minsAgo / 60).toFixed(1)});
    } else {
      document.getElementById("kpi-latest").textContent = "—";
    }

    // "Resumen" label + ventana entre paréntesis
    const summaryTitle = document.getElementById("row-summary-title");
    if (summaryTitle) {
      summaryTitle.textContent = t("web.dashboard.row.summary");
    }
    const periodLabel = document.getElementById("period-label");
    if (periodLabel) {
      periodLabel.textContent = t("web.dashboard.row.summary_window",
        {period: periodHuman});
    }
    const tl = document.getElementById("timeline-window-label");
    if (tl) {
      const tlSeconds = Math.min(periodSec, 24 * 3600);
      tl.textContent = t("web.dashboard.chart.timeline_window",
        {period: humanizePeriod(tlSeconds)});
    }
  }

  // ============================================================
  // API expuesta a Python
  // ============================================================
  window.shakevisionDashboard = {
    setAggregations(payload) {
      const p = (typeof payload === "string") ? JSON.parse(payload) : payload;
      // Actualizar i18n + timezone si vienen en el payload
      if (p && p.i18n) {
        i18nTable = p.i18n;
        // Aplicar traducciones estáticas (HTML data-i18n attrs)
        applyStaticI18n();
      }
      if (p && p.timezone) {
        userTimezone = p.timezone;
      }
      renderKPIs(p || {});
      renderCountries(p?.country_top10);
      renderMagnitude(p?.magnitude_buckets);
      renderDepth(p?.depth_buckets);
      // Línea temporal: dispatcher decide entre scatter (≤24h) y
      // density (>24h) según p.timeline_mode.
      renderTimeline(p || {});
      // Histograma adaptativo del periodo (sustituye a trend_48h fijo)
      renderTrend(p?.period_histogram);
      renderPager(p?.pager_distribution);
      // Repoblar el dropdown de región del PAGER con el nuevo catálogo
      syncPagerRegionOptions(p || {});
      renderScatter(p?.depth_mag_scatter);
    },
  };

  // ============================================================
  // Selector de periodo (1h / 6h / 24h / 7d / 30d)
  // ============================================================
  let bridgeRef = null;
  document.querySelectorAll(".period-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".period-btn").forEach(b =>
        b.classList.remove("active"));
      btn.classList.add("active");
      const period = btn.dataset.period;
      if (bridgeRef && bridgeRef.on_period_changed) {
        bridgeRef.on_period_changed(period);
      }
    });
  });

  // ============================================================
  // Desplegable de región del radar PAGER
  // ============================================================
  const pagerRegionSel = document.getElementById("pager-region-select");
  if (pagerRegionSel) {
    pagerRegionSel.addEventListener("change", () => {
      const region = pagerRegionSel.value;
      if (bridgeRef && bridgeRef.on_pager_region_changed) {
        bridgeRef.on_pager_region_changed(region);
      }
    });
  }

  // ============================================================
  // Puente con Python
  // ============================================================
  function setupBridge() {
    if (typeof QWebChannel === "undefined") {
      console.warn("QWebChannel no disponible — usando datos de muestra.");
      loadSampleData();
      return;
    }
    new QWebChannel(qt.webChannelTransport, (channel) => {
      bridgeRef = channel.objects.bridge;
      if (bridgeRef && bridgeRef.on_dashboard_ready) {
        bridgeRef.on_dashboard_ready();
      }
    });
  }

  function loadSampleData() {
    window.shakevisionDashboard.setAggregations({
      period_seconds: 86400,
      station_summary: { total: 1820, shakenet: 1426, usgs: 394 },
      count_24h: 87,
      max_magnitude: 6.4,
      latest_iso: new Date(Date.now() - 12*60*1000).toISOString(),
      country_count: 23,
      country_top10: [
        { name: "Indonesia", count: 14 },
        { name: "Japan", count: 11 },
        { name: "United States", count: 9 },
        { name: "Chile", count: 8 },
        { name: "Mexico", count: 7 },
        { name: "Greece", count: 6 },
        { name: "Iran", count: 5 },
        { name: "Philippines", count: 4 },
        { name: "Italy", count: 3 },
        { name: "Turkey", count: 3 },
      ],
      magnitude_buckets: [
        { label: "<3.0",   count: 12, color: "#38bdf8" },
        { label: "3.0–4.5",count: 41, color: "#facc15" },
        { label: "4.5–6.0",count: 26, color: "#fb923c" },
        { label: "6.0–7.5",count: 7,  color: "#ef4444" },
        { label: "≥7.5",   count: 1,  color: "#a855f7" },
      ],
      depth_buckets: [
        { label: "0–10",   count: 28 },
        { label: "10–35",  count: 32 },
        { label: "35–70",  count: 14 },
        { label: "70–150", count: 9 },
        { label: "150–300",count: 3 },
        { label: "≥300",   count: 1 },
      ],
      timeline_24h: Array.from({length: 40}, (_, i) => ({
        ts: Date.now()/1000 - (24*3600) * (i / 40),
        mag: 2 + Math.random() * 5,
        place: "demo",
      })),
      pager_distribution: [
        { level: "green",  label: "GREEN",  count: 18, color: "#10b981" },
        { level: "yellow", label: "YELLOW", count: 6,  color: "#facc15" },
        { level: "orange", label: "ORANGE", count: 2,  color: "#fb923c" },
        { level: "red",    label: "RED",    count: 1,  color: "#ef4444" },
      ],
      trend_48h: Array.from({length: 48}, (_, i) => ({
        ts: Date.now() - (48-i)*3600*1000,
        count: Math.floor(Math.random()*8),
        max_mag: i % 6 === 0 ? 4.5 + Math.random()*2 : 0,
      })),
      timeline_mode: "scatter",
      timeline_density: [],
      period_histogram: {
        bucket_label: "1 h",
        buckets: Array.from({length: 24}, (_, i) => ({
          ts: Date.now() - (24-i)*3600*1000,
          count: Math.floor(Math.random()*7),
          max_mag: i % 5 === 0 ? 4 + Math.random()*2 : 0,
        })),
      },
      pager_region: "all",
      region_options: ["Chile", "Greece", "Indonesia", "Japan", "Mexico"],
      depth_mag_scatter: Array.from({length: 50}, () => ({
        depth: Math.random()*200,
        mag: 2 + Math.random()*5,
        place: "demo",
        ts: Date.now(),
        pager: ["green","yellow","orange","red",null][Math.floor(Math.random()*5)],
      })),
    });
  }

  setupBridge();
})();
