/* ============================================================
   SeismicGuard · Datos · Lógica de las 4 gráficas ECharts.
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

  // ─── Idioma de la app para formatear fechas ───
  // v0.7.7 fix: antes formatLocalDateTime usaba ``undefined`` como locale,
  // que Intl resuelve al idioma del SISTEMA (no al de la app). Resultado:
  // los nombres de mes/día en los tooltips del timeline seguían en chino
  // aunque el usuario cambiara el idioma de la app. Ahora usamos el código
  // de idioma que envía Python (``lang`` en el payload / setI18n).
  // ``null`` → fallback al locale del navegador hasta el primer payload.
  let userLocale = null;

  function formatLocalDateTime(ts_ms, opts) {
    // ts_ms: epoch milliseconds. Usa userLocale + userTimezone + opciones.
    try {
      const fmt = new Intl.DateTimeFormat(userLocale || undefined, {
        timeZone: userTimezone,
        ...opts,
      });
      return fmt.format(new Date(ts_ms));
    } catch (e) {
      return new Date(ts_ms).toString();
    }
  }

  // ─── v0.6 Phase 11: paletas duales (dark / light) ───
  // Antes estos eran ``const`` hardcoded → solo se veían bien en tema
  // oscuro. Ahora viven en PALETTES y se reasignan en setTheme().
  // Las funciones que consumen estos valores ya leen las variables
  // top-level cada vez que se llaman (no las cierran en closure),
  // así que el cambio se refleja en el próximo render.
  const PALETTES = {
    dark: {
      TEXT_PRIMARY:   "#fafafa",
      TEXT_SECONDARY: "#a1a1aa",
      TEXT_MUTED:     "#71717a",
      ACCENT:         "#0a84ff",
      ACCENT_2:       "#3395ff",
      PANEL_BG:       "#1a1a1f",
      GRID_LINE:      "rgba(255,255,255,0.06)",
      TOOLTIP_BG:     "rgba(26,26,31,0.95)",
      TOOLTIP_BORDER: "rgba(255,255,255,0.08)",
    },
    light: {
      TEXT_PRIMARY:   "#1d1d1f",
      TEXT_SECONDARY: "#6e6e73",
      TEXT_MUTED:     "#8e8e93",
      ACCENT:         "#0a84ff",
      ACCENT_2:       "#3395ff",
      PANEL_BG:       "#ffffff",
      GRID_LINE:      "rgba(0,0,0,0.06)",
      TOOLTIP_BG:     "rgba(255,255,255,0.96)",
      TOOLTIP_BORDER: "rgba(0,0,0,0.08)",
    },
  };

  // Variables "vivas" — las reasignamos en setTheme() y los siguientes
  // renders de gráficas usan el nuevo valor. Por defecto dark.
  let TEXT_PRIMARY   = PALETTES.dark.TEXT_PRIMARY;
  let TEXT_SECONDARY = PALETTES.dark.TEXT_SECONDARY;
  let TEXT_MUTED     = PALETTES.dark.TEXT_MUTED;
  let ACCENT         = PALETTES.dark.ACCENT;
  let ACCENT_2       = PALETTES.dark.ACCENT_2;
  let PANEL_BG       = PALETTES.dark.PANEL_BG;
  let GRID_LINE      = PALETTES.dark.GRID_LINE;
  let TOOLTIP_BG     = PALETTES.dark.TOOLTIP_BG;
  let TOOLTIP_BORDER = PALETTES.dark.TOOLTIP_BORDER;
  // Tema actual + último payload para poder re-renderizar al cambiar
  // de tema sin esperar al próximo data push.
  let currentTheme   = "dark";
  let lastPayload    = null;

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
        // v0.6 Phase 11: tooltip dinámico — fondo blanco semitransparent
        // en tema claro, gris-negro en oscuro. La sombra también más
        // sutil en claro porque el panel base ya es brillante.
        backgroundColor: TOOLTIP_BG,
        borderColor: TOOLTIP_BORDER,
        borderWidth: 1,
        textStyle: { color: TEXT_PRIMARY, fontSize: 12, fontFamily: FONT_SANS },
        extraCssText: "border-radius: 8px; box-shadow: 0 8px 28px "
                      + (currentTheme === "light"
                          ? "rgba(0,0,0,0.12)"
                          : "rgba(0,0,0,0.5)") + ";",
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
  const chart_epi     = echarts.init(document.getElementById("chart-epicenters"), null, { renderer: "canvas" });
  const chart_magtime = echarts.init(document.getElementById("chart-magtime"), null, { renderer: "canvas" });
  const chart_depthdist = echarts.init(document.getElementById("chart-depthdist"), null, { renderer: "canvas" });
  // Capa profesional (los contenedores arrancan ocultos → 0px; se redimensionan
  // al desplegar la fila).
  const chart_gr       = echarts.init(document.getElementById("chart-gr"), null, { renderer: "canvas" });
  const chart_energy   = echarts.init(document.getElementById("chart-energy"), null, { renderer: "canvas" });
  const chart_spatial = echarts.init(document.getElementById("chart-spatial"), null, { renderer: "canvas" });
  const chart_depthsec = echarts.init(document.getElementById("chart-depthsec"), null, { renderer: "canvas" });
  const chart_mcb      = echarts.init(document.getElementById("chart-mcb"), null, { renderer: "canvas" });
  const chart_interevent = echarts.init(document.getElementById("chart-interevent"), null, { renderer: "canvas" });

  window.addEventListener("resize", () => {
    [chart_country, chart_mag, chart_depth, chart_time,
     chart_pager, chart_trend, chart_scatter, chart_epi, chart_magtime, chart_depthdist,
     chart_gr, chart_energy, chart_spatial, chart_depthsec, chart_mcb, chart_interevent]
      .forEach(c => c.resize());
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
  // Tasa de eventos (sustituye al radar PAGER): área-línea de nº de eventos
  // por bin temporal a lo largo de la ventana.
  function renderEventRate(data) {
    if (!data || data.length === 0 || data.every(d => d.n === 0)) {
      chart_pager.clear();
      return;
    }
    const pts = data.map(d => [d.ts * 1000, d.n]);
    chart_pager.setOption({
      backgroundColor: "transparent",
      grid: { left: 44, right: 16, top: 16, bottom: 28 },
      tooltip: { trigger: "axis", backgroundColor: TOOLTIP_BG,
        borderColor: TOOLTIP_BORDER, textStyle: { color: TEXT_PRIMARY } },
      xAxis: { type: "time", splitLine: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO,
          fontSize: 10 } },
      yAxis: { type: "value", name: t("web.dashboard.axis.events"),
        nameTextStyle: { color: TEXT_MUTED, fontSize: 10 },
        axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO,
          fontSize: 10 },
        splitLine: { lineStyle: { color: GRID_LINE } } },
      series: [{ type: "line", smooth: true, showSymbol: false, data: pts,
        lineStyle: { color: ACCENT, width: 2 },
        areaStyle: { color: ACCENT, opacity: 0.15 } }],
    }, true);
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
    if (seconds <= 45 * 86400) return "30 d";
    const days = seconds / 86400;
    if (days < 330) return `${Math.round(days / 30)} mo`;
    const years = seconds / (365 * 86400);
    return years < 1.5 ? "1 y" : `${Math.round(years)} y`;
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

    // Regiones afectadas: solo el nº de regiones (el conteo de estaciones que
    // se anexaba aquí confundía y venía con cifras erróneas).
    document.getElementById("kpi-countries").textContent =
      Number(payload.country_count || 0).toLocaleString();

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
      // v0.6 Phase 11: cachear el payload para que setTheme() pueda
      // re-renderizar sin esperar al próximo data push.
      lastPayload = p || {};
      if (p && p.i18n) {
        i18nTable = p.i18n;
        applyStaticI18n();
      }
      if (p && p.lang) {
        userLocale = p.lang;
      }
      if (p && p.timezone) {
        userTimezone = p.timezone;
      }
      _renderAll(p || {});
    },
    // v0.7.7 fix: cambio de idioma en caliente (espejo de globe.setI18n).
    // Python lo llama al cambiar LocaleService, así el dashboard re-traduce
    // textos estáticos, fechas (Intl con el locale de la app) y re-pinta
    // las gráficas SIN esperar al próximo refresco de datos.
    setI18n(table, lang) {
      const t2 = (typeof table === "string") ? JSON.parse(table) : table;
      if (t2) { i18nTable = t2; applyStaticI18n(); }
      if (lang) { userLocale = lang; }
      if (lastPayload) {
        if (t2) lastPayload.i18n = t2;
        if (lang) lastPayload.lang = lang;
        _renderAll(lastPayload);
      }
    },
    // v0.6 Phase 11: cambio de tema en caliente. Acepta "dark" | "light".
    // Llamado desde Python al cambiar ThemeManager. Re-pinta TODAS las
    // gráficas con la paleta nueva — sin perder datos.
    setTheme(name) {
      if (name !== "dark" && name !== "light") return;
      if (name === currentTheme) return;
      currentTheme = name;
      // Reasignar las variables vivas a la paleta nueva
      const p = PALETTES[name];
      TEXT_PRIMARY   = p.TEXT_PRIMARY;
      TEXT_SECONDARY = p.TEXT_SECONDARY;
      TEXT_MUTED     = p.TEXT_MUTED;
      ACCENT         = p.ACCENT;
      ACCENT_2       = p.ACCENT_2;
      PANEL_BG       = p.PANEL_BG;
      GRID_LINE      = p.GRID_LINE;
      TOOLTIP_BG     = p.TOOLTIP_BG;
      TOOLTIP_BORDER = p.TOOLTIP_BORDER;
      // Reflejar en el atributo del <html> para que el CSS active
      // las reglas [data-theme="light"].
      document.documentElement.setAttribute("data-theme", name);
      // Re-render con el payload cacheado (si lo hay)
      if (lastPayload) _renderAll(lastPayload);
    },
    currentTheme() { return currentTheme; },
  };

  // ============================================================
  // Capa de análisis PROFESIONAL (b-value / energía / densidad espacial / profundidad)
  // ============================================================
  const _axis = (name) => ({
    nameTextStyle: { color: TEXT_MUTED, fontSize: 11 },
    axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO, fontSize: 11 },
    splitLine: { lineStyle: { color: GRID_LINE } },
    name,
  });
  const _tip = () => ({ backgroundColor: TOOLTIP_BG, borderColor: TOOLTIP_BORDER,
    textStyle: { color: TEXT_PRIMARY } });

  function renderGR(pro) {
    if (!pro || !pro.fmd || !pro.fmd.mag.length) { chart_gr.clear(); return; }
    const f = pro.fmd;
    const cum = f.mag.map((m, i) => [m, f.cumulative[i]]).filter(p => p[1] > 0);
    const inc = f.mag.map((m, i) => [m, f.incremental[i]]).filter(p => p[1] > 0);
    const series = [
      { name: t("web.dashboard.series.gr_cum"), type: "scatter", data: cum,
        symbolSize: 7, itemStyle: { color: ACCENT } },
      { name: "inc", type: "scatter", data: inc, symbolSize: 4,
        itemStyle: { color: TEXT_MUTED, opacity: 0.5 } },
    ];
    let subtext = "";
    if (pro.b_value) {
      const bv = pro.b_value;
      const fit = [];
      for (let m = bv.mc; m <= f.mag[f.mag.length - 1] + 0.1; m += 0.1) {
        const nfit = Math.pow(10, bv.a - bv.b * m);
        if (nfit >= 0.8) fit.push([m, nfit]);
      }
      series.push({ name: t("web.dashboard.series.gr_fit"), type: "line",
        data: fit, showSymbol: false,
        lineStyle: { color: ACCENT_2, type: "dashed", width: 2 } });
      subtext = t("web.dashboard.pro.bvalue", { b: bv.b.toFixed(2),
        err: bv.b_err.toFixed(2), mc: bv.mc.toFixed(1), n: bv.n });
    }
    chart_gr.setOption({
      backgroundColor: "transparent",
      title: subtext ? { text: subtext, left: "center", top: 4,
        textStyle: { color: TEXT_SECONDARY, fontSize: 11, fontFamily: FONT_MONO,
          fontWeight: 400 } } : undefined,
      grid: { left: 48, right: 16, top: subtext ? 32 : 16, bottom: 36 },
      tooltip: Object.assign({ trigger: "item" }, _tip()),
      xAxis: Object.assign({ type: "value", nameLocation: "middle", nameGap: 22 },
        _axis(t("web.dashboard.axis.magnitude"))),
      yAxis: Object.assign({ type: "log" }, _axis("N")),
      series,
    }, true);
  }

  function renderEnergy(pro) {
    if (!pro || !pro.cumulative || !pro.cumulative.t.length) {
      chart_energy.clear(); return;
    }
    const c = pro.cumulative;
    const cnt = c.t.map((ts, i) => [ts * 1000, c.count[i]]);
    const ene = c.t.map((ts, i) => [ts * 1000, c.energy_cum[i]]);
    chart_energy.setOption({
      backgroundColor: "transparent",
      grid: { left: 52, right: 58, top: 28, bottom: 32 },
      tooltip: Object.assign({ trigger: "axis" }, _tip()),
      legend: { top: 2, textStyle: { color: TEXT_MUTED, fontSize: 10 },
        data: [t("web.dashboard.series.cum_count"),
          t("web.dashboard.series.cum_energy")] },
      xAxis: { type: "time", splitLine: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO, fontSize: 10 } },
      yAxis: [
        Object.assign({ type: "value" }, _axis(t("web.dashboard.axis.cum_count"))),
        Object.assign({ type: "log", position: "right",
          splitLine: { show: false } }, _axis("J")),
      ],
      series: [
        { name: t("web.dashboard.series.cum_count"), type: "line",
          showSymbol: false, yAxisIndex: 0, data: cnt,
          lineStyle: { color: ACCENT, width: 2 },
          areaStyle: { color: ACCENT, opacity: 0.12 } },
        { name: t("web.dashboard.series.cum_energy"), type: "line",
          showSymbol: false, yAxisIndex: 1, data: ene,
          lineStyle: { color: "#ff9f0a", width: 2 } },
      ],
    }, true);
  }

  // ANÁLISIS: densidad espacial (rejilla lon × lat). Cada celda = un cuadro
  // coloreado por nº de eventos (azul→rojo): muestra DÓNDE se concentra la
  // actividad en un panorama de gran área. Datos: [lon, lat, conteo, mag_máx].
  function renderSpatial(pro) {
    const sp = pro && pro.spatial;
    const cells = sp && sp.cells;
    if (!cells || !cells.length) { chart_spatial.clear(); return; }
    const maxc = cells.reduce((a, c) => Math.max(a, c[2]), 1);
    chart_spatial.setOption({
      backgroundColor: "transparent",
      grid: { left: 48, right: 16, top: 14, bottom: 28 },
      tooltip: Object.assign({ trigger: "item",
        formatter: p => `${p.data[2]}× · M≤${p.data[3].toFixed(1)} · ` +
          `${p.data[1].toFixed(1)}°, ${p.data[0].toFixed(1)}°` }, _tip()),
      xAxis: Object.assign({ type: "value", scale: true },
        _axis(t("web.dashboard.axis.longitude"))),
      yAxis: Object.assign({ type: "value", scale: true },
        _axis(t("web.dashboard.axis.latitude"))),
      visualMap: { show: false, min: 1, max: maxc, dimension: 2,
        inRange: { color: ["#1e3a8a", "#3b82f6", "#10b981", "#f59e0b",
          "#ef4444"] } },
      series: [{ type: "scatter", data: cells, symbol: "rect",
        symbolSize: 13, itemStyle: { opacity: 0.82 } }],
    }, true);
  }

  function renderDepthSection(pro) {
    const sec = pro && pro.section;
    if (!sec || !sec.length) { chart_depthsec.clear(); return; }
    chart_depthsec.setOption({
      backgroundColor: "transparent",
      grid: { left: 52, right: 16, top: 16, bottom: 40 },
      tooltip: Object.assign({ trigger: "item",
        formatter: pp => `M ${pp.data[2].toFixed(1)} · ` +
          `${t("web.dashboard.axis.depth_km")} ${pp.data[1].toFixed(0)}` }, _tip()),
      xAxis: Object.assign({ type: "value", nameLocation: "middle", nameGap: 24,
        scale: true }, _axis(t("web.dashboard.axis.distance"))),
      yAxis: Object.assign({ type: "value", inverse: true, scale: true },
        _axis(t("web.dashboard.axis.depth_km"))),
      visualMap: { show: false, min: 0, max: 8, dimension: 2,
        inRange: { color: ["#66bb6a", "#fbc02d", "#f4511e", "#c62828"] } },
      series: [{ type: "scatter", data: sec,
        symbolSize: pp => 3 + pp[2] * 1.6 }],
    }, true);
  }

  // Calidad del catálogo: Mc(t) y b(t) en ventanas (con banda de error en b).
  function renderMcB(pro) {
    const s = pro && pro.mc_b;
    if (!s || !s.t || s.t.length < 2) {
      chart_mcb.setOption({ backgroundColor: "transparent",
        title: { text: t("web.dashboard.pro.insufficient"), left: "center",
          top: "center", textStyle: { color: TEXT_MUTED, fontSize: 12,
            fontWeight: 400 } },
        xAxis: { show: false }, yAxis: { show: false }, series: [] }, true);
      return;
    }
    const tms = s.t.map(x => x * 1000);
    const bpts = s.t.map((x, i) => [tms[i], s.b[i]]);
    const mcpts = s.t.map((x, i) => [tms[i], s.mc[i]]);
    chart_mcb.setOption({
      backgroundColor: "transparent",
      grid: { left: 44, right: 44, top: 24, bottom: 28 },
      tooltip: Object.assign({ trigger: "axis" }, _tip()),
      legend: { top: 2, textStyle: { color: TEXT_MUTED, fontSize: 10 },
        data: ["b", "Mc"] },
      xAxis: { type: "time", splitLine: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO,
          fontSize: 10 } },
      yAxis: [
        Object.assign({ type: "value", scale: true }, _axis("b")),
        Object.assign({ type: "value", scale: true, position: "right",
          splitLine: { show: false } }, _axis("Mc")),
      ],
      series: [
        { name: "b", type: "line", data: bpts, yAxisIndex: 0,
          showSymbol: true, symbolSize: 5,
          lineStyle: { color: ACCENT, width: 2 } },
        { name: "Mc", type: "line", data: mcpts, yAxisIndex: 1,
          showSymbol: true, symbolSize: 4,
          lineStyle: { color: "#ff9f0a", width: 2, type: "dashed" } },
      ],
    }, true);
  }

  // EN VIVO: dispersión de epicentros (lon × lat) coloreada por magnitud.
  function renderEpicenters(pts) {
    if (!pts || !pts.length) { chart_epi.clear(); return; }
    chart_epi.setOption({
      backgroundColor: "transparent",
      grid: { left: 46, right: 16, top: 12, bottom: 34 },
      tooltip: Object.assign({ trigger: "item",
        formatter: p => `M ${p.data[2].toFixed(1)} · ` +
          `${p.data[1].toFixed(1)}°, ${p.data[0].toFixed(1)}°` }, _tip()),
      xAxis: Object.assign({ type: "value", scale: true,
        nameLocation: "middle", nameGap: 22 },
        _axis(t("web.dashboard.axis.longitude"))),
      yAxis: Object.assign({ type: "value", scale: true },
        _axis(t("web.dashboard.axis.latitude"))),
      visualMap: { show: false, min: 0, max: 8, dimension: 2,
        inRange: { color: ["#66bb6a", "#fbc02d", "#f4511e", "#c62828"] } },
      series: [{ type: "scatter", data: pts,
        symbolSize: p => 3 + p[2] * 1.4 }],
    }, true);
  }

  // ANÁLISIS: magnitud vs tiempo (secuencia de eventos en la ventana).
  function renderMagTime(pts) {
    if (!pts || !pts.length) { chart_magtime.clear(); return; }
    chart_magtime.setOption({
      backgroundColor: "transparent",
      grid: { left: 40, right: 16, top: 12, bottom: 28 },
      tooltip: Object.assign({ trigger: "item",
        formatter: p => `M ${p.data[1].toFixed(1)}` }, _tip()),
      xAxis: { type: "time", splitLine: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO,
          fontSize: 10 } },
      yAxis: Object.assign({ type: "value", scale: true },
        _axis(t("web.dashboard.axis.magnitude"))),
      visualMap: { show: false, min: 0, max: 8, dimension: 1,
        inRange: { color: ["#66bb6a", "#fbc02d", "#f4511e", "#c62828"] } },
      series: [{ type: "scatter", data: pts,
        symbolSize: p => 3 + p[1] * 1.2 }],
    }, true);
  }

  // ANÁLISIS: distribución de profundidad (histograma del catálogo de la
  // ventana). Barras horizontales, someras arriba → profundas abajo.
  function renderDepthDist(pro) {
    const h = pro && pro.depth_hist;
    if (!h || !h.counts || !h.counts.length) { chart_depthdist.clear(); return; }
    const labels = h.counts.map((_, i) =>
      `${Math.round(h.edges[i])}–${Math.round(h.edges[i + 1])}`);
    chart_depthdist.setOption({
      backgroundColor: "transparent",
      grid: { left: 64, right: 18, top: 12, bottom: 28 },
      tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" },
        formatter: p => `${p[0].name} km · ${p[0].value}` }, _tip()),
      xAxis: Object.assign({ type: "value", minInterval: 1 },
        _axis(t("web.dashboard.axis.count"))),
      yAxis: Object.assign({ type: "category", inverse: true, data: labels,
        nameLocation: "end" }, _axis(t("web.dashboard.axis.depth_km"))),
      series: [{ type: "bar", data: h.counts, barWidth: "62%",
        itemStyle: { color: "#0ea5e9", borderRadius: [0, 3, 3, 0] } }],
    }, true);
  }

  // ANÁLISIS: distribución (log) de intervalos entre eventos consecutivos.
  // Pico en intervalos cortos → catálogo agrupado (réplicas/enjambre);
  // distribución ancha → proceso ~Poissoniano (aleatorio).
  function renderInterEvent(pro) {
    const ie = pro && pro.inter_event;
    if (!ie || !ie.counts || !ie.counts.length) { chart_interevent.clear(); return; }
    const fmtH = hrs => {
      if (hrs < 1 / 60) return `${Math.round(hrs * 3600)}s`;
      if (hrs < 1) return `${Math.round(hrs * 60)}m`;
      if (hrs < 48) return `${hrs.toFixed(hrs < 10 ? 1 : 0)}h`;
      return `${(hrs / 24).toFixed(hrs < 240 ? 1 : 0)}d`;
    };
    const labels = ie.hours.map(fmtH);
    const subtitle = t("web.dashboard.pro.median_gap", { v: fmtH(ie.median_h) });
    chart_interevent.setOption({
      backgroundColor: "transparent",
      title: { text: subtitle, left: "center", top: 2,
        textStyle: { color: TEXT_MUTED, fontSize: 10, fontWeight: 400 } },
      grid: { left: 40, right: 16, top: 26, bottom: 30 },
      tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" } }, _tip()),
      xAxis: Object.assign({ type: "category", data: labels,
        axisLabel: { color: TEXT_SECONDARY, fontFamily: FONT_MONO, fontSize: 9,
          interval: "auto", hideOverlap: true } },
        _axis(t("web.dashboard.axis.gap"))),
      yAxis: Object.assign({ type: "value", minInterval: 1 },
        _axis(t("web.dashboard.axis.count"))),
      series: [{ type: "bar", data: ie.counts, barWidth: "92%",
        itemStyle: { color: "#a855f7" } }],
    }, true);
  }

  function renderPro(pro) {
    const summaryEl = document.getElementById("pro-summary");
    if (summaryEl) {
      summaryEl.textContent = (pro && pro.b_value)
        ? t("web.dashboard.pro.bvalue", { b: pro.b_value.b.toFixed(2),
            err: pro.b_value.b_err.toFixed(2), mc: pro.b_value.mc.toFixed(1),
            n: pro.b_value.n })
        : "";
    }
    // Solo pintar las gráficas pro si la PÁGINA de análisis está visible
    // (evita trabajo en cada push del feed en vivo).
    const pa = document.getElementById("page-analysis");
    if (pa && pa.style.display !== "none") {
      renderGR(pro); renderEnergy(pro); renderSpatial(pro);
      renderDepthSection(pro); renderMcB(pro);
      renderDepthDist(pro); renderInterEvent(pro);
    }
  }

  // Helper interno reutilizable por setAggregations y setTheme.
  function _renderAll(p) {
    renderKPIs(p);
    renderCountries(p.country_top10);
    renderMagnitude(p.magnitude_buckets);
    renderDepth(p.depth_buckets);
    renderTimeline(p);
    renderTrend(p.period_histogram);
    renderEventRate(p.event_rate);
    renderScatter(p.depth_mag_scatter);
    renderEpicenters(p.epicenters);
    renderMagTime(p.mag_time);
    renderPro(p.pro);
  }

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
  // Plegar/desplegar la fila de análisis profesional (opt-in)
  // ============================================================
  (function () {
    const toggle = document.getElementById("pro-toggle");
    const grid = document.getElementById("pro-grid");
    if (!toggle || !grid) return;
    toggle.addEventListener("click", () => {
      const opening = grid.style.display === "none";
      grid.style.display = opening ? "" : "none";
      toggle.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        // Los contenedores estaban a 0px → redimensionar y pintar ahora.
        [chart_gr, chart_energy, chart_spatial, chart_depthsec, chart_mcb]
          .forEach(c => c.resize());
        if (lastPayload) renderPro(lastPayload.pro);
      }
    });
  })();

  // ============================================================
  // Conmutación de PÁGINA (En vivo / Análisis) — la dispara Qt vía
  // window.setDashboardMode(). Son DOS páginas independientes: cada gráfica
  // pertenece a una sola; cambiar de modo solo muestra/oculta su contenedor.
  // ============================================================
  window.setDashboardMode = function (mode) {
    const isLive = mode !== "analysis";
    const pl = document.getElementById("page-live");
    const pa = document.getElementById("page-analysis");
    if (pl) pl.style.display = isLive ? "" : "none";
    if (pa) pa.style.display = isLive ? "none" : "";
    if (!isLive && lastPayload) renderPro(lastPayload.pro);
    setTimeout(() => {
      [chart_country, chart_mag, chart_depth, chart_time, chart_pager,
       chart_trend, chart_scatter, chart_epi, chart_magtime, chart_depthdist,
       chart_gr, chart_energy, chart_spatial, chart_depthsec, chart_mcb,
       chart_interevent]
        .forEach(c => c.resize());
    }, 60);
  };
  window.setDashboardMode("live");   // estado inicial

  // ============================================================
  // Desplegable de región del radar PAGER (legacy; elemento ya removido)
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
