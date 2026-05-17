/* ============================================================
   ShakeVision · Globo · Implementación con ECharts-GL.
   ------------------------------------------------------------
   Reemplazamos Globe.gl/Three.js por echarts-gl (mismo motor que
   ya usa el dashboard). Ventajas:
     - Una sola dependencia gráfica (echarts) en todo el proyecto
     - CDN ya validado en el entorno del usuario
     - API JSON declarativa (no hay que llamar a Three.js a mano)
     - Series scatter3D + lines3D + post-effects nativos
   ============================================================ */

(() => {
  // Estado global
  const state = {
    devices: [],
    quakes: [],
    activeLayer: "quakes",
    bridge: null,
  };

  // ─── i18n ───
  // Tabla de traducciones inyectada por Python (vía setI18n). Hasta
  // que llegue, t() devuelve la clave misma → fácil ver qué falta.
  let i18nTable = {};
  function t(key, vars) {
    const v = i18nTable[key];
    if (v == null) return key;
    if (vars) {
      return v.replace(/\{(\w+)(?::[^}]*)?\}/g, (m, k) =>
        (k in vars ? vars[k] : m));
    }
    return v;
  }

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

  // ============================================================
  // Codificación visual por magnitud
  // ------------------------------------------------------------
  // Paleta elegida para máximo contraste entre niveles:
  //  - Micro (<3): gris pizarra apagado, no compite por la atención
  //  - Ligero (3–4.5): amarillo intenso — el primer color "vivo"
  //  - Moderado (4.5–6): naranja oscuro — claramente distinto del amarillo
  //  - Fuerte (6–7.5): rojo profundo — alarma
  //  - Mayor (>7.5): violeta — único, jamás se confunde con rojo
  // ============================================================
  // Cada bucket lleva un ``i18nKey`` en vez de label fijo. La función
  // ``magLabel(bucket)`` resuelve al idioma actual cuando se necesita.
  const MAG_BUCKETS = [
    { max: 3.0, color: "#94a3b8", radius: 3,  i18nKey: "web.globe.mag_bucket.micro" },
    { max: 4.5, color: "#facc15", radius: 7,  i18nKey: "web.globe.mag_bucket.light" },
    { max: 6.0, color: "#f97316", radius: 13, i18nKey: "web.globe.mag_bucket.moderate" },
    { max: 7.5, color: "#dc2626", radius: 22, i18nKey: "web.globe.mag_bucket.strong" },
    { max: 99,  color: "#a855f7", radius: 32, i18nKey: "web.globe.mag_bucket.major" },
  ];

  function bucketFor(mag) {
    return MAG_BUCKETS.find(b => mag < b.max) || MAG_BUCKETS[MAG_BUCKETS.length - 1];
  }

  function magLabel(bucket) {
    return t(bucket.i18nKey);
  }

  // Inicializar el chart ECharts
  const container = document.getElementById("globe");
  const chart = echarts.init(container, null, { renderer: "canvas" });
  window.addEventListener("resize", () => chart.resize());

  // Configuración base del globo (estilo "ciencia oscura")
  const baseOption = {
    backgroundColor: "transparent",
    globe: {
      // Texturas locales (las descarga install_libs.sh); echarts-gl
      // tolera URLs HTTPS también si las locales fallan.
      baseTexture: "lib/earth-night.jpg",
      heightTexture: "lib/earth-topology.png",
      // displacementScale: 0  → la superficie queda perfectamente
      // esférica (sin relieve montañoso). Imprescindible para que
      // los puntos scatter3D se posicionen exactamente sobre las
      // coordenadas reportadas por USGS.
      displacementScale: 0,
      shading: "realistic",
      realisticMaterial: {
        roughness: 0.85,
        metalness: 0,
      },
      environment: "#000",
      // Iluminación tenue para mantener el aspecto nocturno con
      // las luces de las ciudades visibles
      light: {
        ambient: { intensity: 0.35 },
        main:    { intensity: 0.6, alpha: 30 },
      },
      // Cámara y controles (rotación lenta automática)
      // ─── LÍMITES DE DISTANCIA ───
      // minDistance: 20 permite hacer zoom hasta escala "país pequeño"
      // (la antigua 130 capaba todo zoom programático a vista mundial).
      // Por debajo de ~20 empieza el clipping del near-plane interno de
      // ECharts-GL (no expuesto), así que dejamos 20 como suelo absoluto.
      // maxDistance: 400 da margen para que el usuario se aleje con la
      // rueda más allá de la posición de reposo (200).
      //
      // ─── LÍMITES DE ALPHA (CRÍTICO PARA EL CENTRADO) ───
      // Por defecto ECharts-GL fija minAlpha: 5, lo que hace IMPOSIBLE
      // que la cámara se incline para mirar el hemisferio sur — al
      // clickear un punto a latitud negativa (Chile, Argentina, etc.)
      // la cámara se quedaba en alpha=5 y el "centrado" parecía no
      // funcionar. Abrimos el rango completo [-90, 90].
      //
      // ─── AUTO-RESTART DE LA ROTACIÓN ───
      // autoRotateAfterStill (default 8 s) reanuda automáticamente la
      // rotación 8 s después del último click/drag. Esto rompe nuestro
      // "centrado" — apenas terminamos de animar el zoom, comienza la
      // cuenta atrás y a los 8 s la cámara empieza a girar borrando la
      // referencia centrada. Lo desactivamos completamente (1e9 s ≈
      // "nunca"); el control de pausa/reanuda lo gestionamos nosotros.
      viewControl: {
        autoRotate: true,
        autoRotateSpeed: 5,
        autoRotateAfterStill: 1e9,
        damping: 0.85,
        rotateSensitivity: 1.2,
        zoomSensitivity: 1.0,
        minDistance: 20,
        maxDistance: 400,
        minAlpha: -90,
        maxAlpha: 90,
      },
      // Bloom muy sutil — antes 0.18 hacía que los puntos ya brillantes
      // (naranja, amarillo) parecieran "hiper-iluminados". Con 0.06
      // queda solo un toque de glow en luces de ciudad.
      postEffect: {
        enable: true,
        bloom: {
          enable: true,
          intensity: 0.06,
        },
        SSAO: { enable: true, radius: 1, intensity: 1.0 },
      },
      temporalSuperSampling: { enable: true },
    },
    series: [],
  };

  chart.setOption(baseOption);

  // ============================================================
  // Construcción dinámica de las series según la capa activa
  // ============================================================
  function applyActiveLayer() {
    const showDevices = state.activeLayer === "devices" || state.activeLayer === "both";
    const showQuakes  = state.activeLayer === "quakes"  || state.activeLayer === "both";

    const series = [];

    // ⚠ IMPORTANTE: para echarts-gl scatter3D sobre globe, value debe
    // ser SOLO [lng, lat]. Si añadimos un tercer elemento, echarts-gl
    // lo interpreta como "altura sobre la superficie" y los puntos
    // flotan en el espacio. Cualquier metadato (mag, place...) va en
    // campos auxiliares del objeto, no en value.

    if (showDevices) {
      // Separamos por proveedor para colorearlos distinto:
      //  - Raspberry Shake (provider="shakenet" o ausente) → cyan
      //  - USGS / IRIS profesional (provider="usgs")         → ámbar dorado
      const shake = state.devices.filter(d =>
        !d.provider || d.provider === "shakenet");
      const usgs = state.devices.filter(d => d.provider === "usgs");

      // Paleta verde: Shake en verde profundo (gran masa de fondo),
      // USGS en menta pálida (puntos clave que destacan).
      if (shake.length > 0) {
        series.push({
          name: t("web.globe.series.shake"),
          type: "scatter3D",
          coordinateSystem: "globe",
          blendMode: "source-over",
          symbolSize: 4,
          itemStyle: { color: "#16a34a", opacity: 0.85 },   // verde profundo
          data: shake.map(d => ({
            value: [d.lng, d.lat],
            raw: d, kind: "device",
          })),
        });
      }

      if (usgs.length > 0) {
        // Halo: scatter más grande y semi-transparente como aureola,
        // dibujado ANTES del punto principal para que quede debajo.
        // ─── TAMAÑO ───
        // symbolSize es en píxeles de pantalla (no en unidades de
        // mundo), por lo que el halo crece relativamente al hacer zoom.
        // Con el nuevo zoom a distance=45 un halo de 18 px tapaba el
        // país entero; lo reducimos a 11 px para que siga siendo
        // visible en vista mundial pero no domine al acercar.
        series.push({
          name: t("web.globe.series.usgs_halo"),
          type: "scatter3D",
          coordinateSystem: "globe",
          blendMode: "lighter",   // suma luz → halo visible
          symbolSize: 11,
          itemStyle: { color: "#86efac", opacity: 0.30 },
          silent: true,           // no roba el click al punto central
          data: usgs.map(d => ({
            value: [d.lng, d.lat],
            raw: d, kind: "device",
          })),
        });
        // Punto principal — verde menta brillante de buena saturación
        series.push({
          name: t("web.globe.series.usgs"),
          type: "scatter3D",
          coordinateSystem: "globe",
          blendMode: "source-over",
          symbolSize: 7,
          itemStyle: { color: "#86efac", opacity: 1.0 },
          emphasis: {
            itemStyle: { borderColor: "#ffffff", borderWidth: 2 },
          },
          data: usgs.map(d => ({
            value: [d.lng, d.lat],
            raw: d, kind: "device",
          })),
        });
      }
    }

    if (showQuakes) {
      // Asignamos symbolSize y color a cada punto INDIVIDUALMENTE
      // (no por callback). Esto evita problemas de echarts-gl que a
      // veces no preserva campos custom en los params del callback,
      // resultando en puntos que aparecen con el color por defecto
      // (azul brillante) en vez del color de su magnitud.
      series.push({
        name: t("web.globe.series.quakes_24h"),
        type: "scatter3D",
        coordinateSystem: "globe",
        blendMode: "source-over",   // ya no "lighter" → evita brillos extraños
        emphasis: {
          itemStyle: { borderColor: "#ffffff", borderWidth: 1.5 },
        },
        data: state.quakes.map(q => {
          const b = bucketFor(q.mag);
          return {
            value: [q.lng, q.lat],
            symbolSize: b.radius,
            itemStyle: {
              color: b.color,
              opacity: 0.92,
            },
            raw: q,
            kind: "quake",
          };
        }),
      });

      // Halos: solo para sismos REALMENTE significativos
      // (M ≥ 6.0 y últimas 6 h). Antes incluía M ≥ 4.5 lo cual
      // pintaba demasiados halos y daba sensación de "ruido brillante".
      const sixHoursAgo = (Date.now() / 1000) - 6 * 3600;
      const recentSig = state.quakes.filter(q =>
        q.ts >= sixHoursAgo && q.mag >= 6.0
      );
      if (recentSig.length > 0) {
        series.push({
          name: t("web.globe.series.halos"),
          type: "scatter3D",
          coordinateSystem: "globe",
          blendMode: "source-over",
          silent: true,
          data: recentSig.map(q => {
            const b = bucketFor(q.mag);
            return {
              value: [q.lng, q.lat],
              symbolSize: b.radius * 2.4,
              itemStyle: {
                color: b.color,
                opacity: 0.10,        // muy sutil
              },
              raw: q,
            };
          }),
        });
      }
    }

    chart.setOption({
      tooltip: {
        backgroundColor: "rgba(17,17,17,0.95)",
        borderColor: "rgba(255,255,255,0.08)",
        borderWidth: 1,
        textStyle: { color: "#fafafa", fontSize: 12 },
        extraCssText: "border-radius:8px; box-shadow:0 8px 28px rgba(0,0,0,0.5);",
        formatter: (params) => renderTooltip(params.data),
      },
      series: series,
    }, { replaceMerge: ["series"] });

    updateLegend();
    updateCounter();
  }

  function renderTooltip(data) {
    if (!data || !data.raw) return "";
    if (data.kind === "device") {
      const d = data.raw;
      return `<div style="font-weight:600;margin-bottom:4px">📡 ${d.network}.${d.code}</div>`
           + `<div style="color:#a1a1aa;font-family:monospace">${t("web.globe.tooltip.lat")}: ${d.lat.toFixed(3)}°</div>`
           + `<div style="color:#a1a1aa;font-family:monospace">${t("web.globe.tooltip.lng")}: ${d.lng.toFixed(3)}°</div>`
           + `<div style="color:#a1a1aa;font-family:monospace">${t("web.globe.tooltip.alt")}: ${d.elevation.toFixed(0)} m</div>`
           + (d.site ? `<div style="color:#71717a;margin-top:4px">${d.site}</div>` : "");
    }
    const q = data.raw;
    const dt = new Date(q.ts * 1000).toUTCString().replace("GMT", "UTC");
    const b = bucketFor(q.mag);
    // ─── FIX BUG ───
    // MAG_BUCKETS dejó de tener ``label`` literal (ahora son i18nKey).
    // Resolvemos la etiqueta vía magLabel() y extraemos el descriptor
    // que va tras el doble espacio (p.ej. "Moderado", "Moderate", "中等").
    // Si el formato no contiene "  " (alguna traducción cambia el separador),
    // mostramos la etiqueta completa como fallback en vez de crashear.
    const fullMag = magLabel(b) || "";
    const parts = fullMag.split("  ");
    const magDesc = parts.length > 1 ? parts[1] : fullMag;
    return `<div style="font-weight:600;margin-bottom:4px">M ${q.mag.toFixed(1)}  ·  ${magDesc}</div>`
         + `<div>${q.place}</div>`
         + `<div style="color:#a1a1aa;font-family:monospace">${t("web.globe.tooltip.depth", {km: q.depth})}</div>`
         + `<div style="color:#71717a;font-family:monospace">${dt}</div>`
         + (q.pager ? `<div style="color:${b.color};margin-top:4px"><b>${t("web.globe.tooltip.pager")}</b> ${q.pager}</div>` : "");
  }

  // ============================================================
  // Click → zoom (sin "snap" de centrado) + bridge — MÁQUINA DE ESTADOS
  // ------------------------------------------------------------
  // NOTA: el snap de centrado (alpha/beta hacia el punto clicado) se
  // ELIMINÓ porque ECharts-GL no expone un mapeo lng/lat→beta fiable
  // entre versiones y no podemos calibrarlo en este sandbox. Quedó
  // únicamente el zoom de distance, que sí funciona de forma
  // determinista. El usuario puede arrastrar manualmente para mirar
  // alrededor en estado ZOOMED-IN.
  //
  // Estados implícitos:
  //
  //   ┌─────────────┐   click photopoint    ┌──────────────────┐
  //   │   RESPOSO   │ ────────────────────▶ │   ZOOMED-IN      │
  //   │ (distance   │                       │ (distance 45,    │
  //   │  200, rota  │ ◀── Esc / rueda hasta │  NO rota, permite│
  //   │  si !paused)│      distance ≥ 100   │  drag libre)     │
  //   └─────────────┘                       └──────────────────┘
  //
  // Reglas:
  //   * userPausedRotation = "intención" del usuario (botón pausa).
  //     focusOnPoint NO lo modifica.
  //   * resetView (Esc o rueda hacia atrás) reanuda autoRotate solo si
  //     !userPausedRotation.
  //   * Click sobre fondo NO sale del zoom (no estorbar al drag).
  //   * Click sobre otro photopoint en ZOOMED-IN → solo pasa al bridge
  //     (sin re-centrar; el zoom ya está aplicado).
  // ============================================================
  const DEFAULT_VIEW = { distance: 200, alpha: 30, beta: 0 };
  // Distancia para zoom "país mediano".
  const ZOOM_VIEW_DISTANCE = 45;
  // Umbral: cuando la rueda lleva la cámara más allá de esta distancia
  // abandonamos ZOOMED-IN.
  const EXIT_ZOOM_THRESHOLD = 100;
  // Duración de las animaciones de entrada/salida del zoom (ms).
  const ZOOM_ANIM_MS = 700;
  const EXIT_ANIM_MS = 750;

  // ─── ESTADO ───
  let zoomedIn = false;
  let userPausedRotation = false;
  let suppressWheelExit = false;   // evita reentrada del listener wheel

  function getCurrentDistance() {
    const opt = chart.getOption();
    const d = opt.globe?.[0]?.viewControl?.distance;
    return (typeof d === "number") ? d : DEFAULT_VIEW.distance;
  }

  function syncRotateBtnUI(isRotating) {
    rotateBtn.textContent = isRotating ? "⏸" : "▶";
    rotateBtn.classList.toggle("paused", !isRotating);
  }

  // Entra en ZOOMED-IN: solo cambia distance y para autoRotate.
  // alpha/beta se DEJAN tal cual estaban (sin snap → sin riesgo de
  // desorientación por mala fórmula de mapeo).
  function focusOnPoint(/* lng, lat — no usados intencionalmente */) {
    if (zoomedIn) {
      // Ya estamos en zoom; no hace falta volver a animar la cámara.
      // El click se propaga al bridge por el handler del chart.
      return;
    }
    zoomedIn = true;
    rotating = false;
    syncRotateBtnUI(false);

    suppressWheelExit = true;
    chart.setOption({
      globe: {
        viewControl: {
          distance: ZOOM_VIEW_DISTANCE,
          autoRotate: false,
          animation: true,
          animationDurationUpdate: ZOOM_ANIM_MS,
          animationEasingUpdate: "cubicOut",
        }
      }
    });
    // Esperar a que termine la animación antes de volver a escuchar la
    // rueda (si no, el propio cambio de distance dispararía el listener).
    setTimeout(() => { suppressWheelExit = false; }, ZOOM_ANIM_MS + 50);
  }

  function resetView() {
    if (!zoomedIn) return;     // idempotente

    const willRotate = !userPausedRotation;
    suppressWheelExit = true;
    chart.setOption({
      globe: {
        viewControl: {
          distance: DEFAULT_VIEW.distance,
          autoRotate: willRotate,
          animation: true,
          animationDurationUpdate: EXIT_ANIM_MS,
          animationEasingUpdate: "cubicOut",
        }
      }
    });
    zoomedIn = false;
    rotating = willRotate;
    syncRotateBtnUI(willRotate);
    setTimeout(() => { suppressWheelExit = false; }, EXIT_ANIM_MS + 50);
  }

  // ─── Click sobre un photopoint → zoom (si aplica) + bridge ───
  chart.on("click", (params) => {
    if (!params.data) return;
    const data = params.data;
    if (Array.isArray(data.value) && data.value.length >= 2) {
      focusOnPoint(data.value[0], data.value[1]);
    }
    if (state.bridge) {
      if (data.kind === "device") {
        state.bridge.on_station_clicked(data.raw.network, data.raw.code);
      } else if (data.kind === "quake") {
        state.bridge.on_earthquake_clicked(data.raw.id);
      }
    }
  });

  // ─── Rueda hacia atrás (alejar) → salida del zoom ───
  chart.getZr().on("mousewheel", () => {
    if (!zoomedIn || suppressWheelExit) return;
    requestAnimationFrame(() => {
      if (zoomedIn && getCurrentDistance() >= EXIT_ZOOM_THRESHOLD) {
        resetView();
      }
    });
  });

  // ─── Esc → vuelve a vista global ───
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && zoomedIn) resetView();
  });

  // ============================================================
  // Leyenda y contador
  // ============================================================
  function updateLegend() {
    const wrap = document.getElementById("legend-content");
    const title = document.getElementById("legend-title");

    const deviceLegend = `
      <div class="legend-row">
        <span class="legend-dot" style="background:#16a34a;color:#16a34a"></span>
        ${t("web.globe.legend.shake")}
      </div>
      <div class="legend-row">
        <span class="legend-dot" style="background:#86efac;color:#86efac"></span>
        ${t("web.globe.legend.usgs")}
      </div>`;

    if (state.activeLayer === "devices") {
      title.textContent = t("web.globe.legend.devices_title");
      wrap.innerHTML = deviceLegend;
      return;
    }

    title.textContent = state.activeLayer === "both"
      ? t("web.globe.legend.both_title")
      : t("web.globe.legend.title");
    wrap.innerHTML = MAG_BUCKETS.map(b => `
      <div class="legend-row">
        <span class="legend-dot" style="background:${b.color};color:${b.color}"></span>
        ${magLabel(b)}
      </div>
    `).join("");

    if (state.activeLayer === "both") {
      wrap.innerHTML += `<div style="margin-top:6px">${deviceLegend}</div>`;
    }
  }

  function updateCounter() {
    const el = document.getElementById("counter");
    const text = document.getElementById("counter-text");
    const icon = document.getElementById("counter-icon");

    const nShake = state.devices.filter(d =>
      !d.provider || d.provider === "shakenet").length;
    const nUsgs = state.devices.filter(d => d.provider === "usgs").length;

    if (state.activeLayer === "devices") {
      icon.textContent = "📡";
      text.textContent = t("web.globe.counter.devices",
        {shake: nShake, usgs: nUsgs});
    } else if (state.activeLayer === "quakes") {
      icon.textContent = "🌋";
      text.textContent = t("web.globe.counter.quakes",
        {n: state.quakes.length});
    } else {
      icon.textContent = "✨";
      text.textContent = t("web.globe.counter.both",
        {quakes: state.quakes.length, shake: nShake, usgs: nUsgs});
    }
    el.classList.add("ok");
  }

  // ============================================================
  // Selector de capa (botones)
  // ============================================================
  document.querySelectorAll(".seg-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".seg-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeLayer = btn.dataset.layer;
      applyActiveLayer();
      if (state.bridge && state.bridge.on_layer_changed) {
        state.bridge.on_layer_changed(state.activeLayer);
      }
    });
  });

  // ============================================================
  // Selector de periodo (1h / 24h / 7d / 30d)
  // ============================================================
  document.querySelectorAll(".period-btn-globe").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".period-btn-globe").forEach(b =>
        b.classList.remove("active"));
      btn.classList.add("active");
      const period = btn.dataset.period;
      if (state.bridge && state.bridge.on_period_changed) {
        state.bridge.on_period_changed(period);
      }
    });
  });

  // ============================================================
  // Controles de cámara: zoom + reset + pausa rotación
  // ============================================================
  function getCameraDistance() {
    const opt = chart.getOption();
    return (opt.globe?.[0]?.viewControl?.distance) || 200;
  }

  function setCameraDistance(d) {
    chart.setOption({
      globe: { viewControl: { distance: d } }
    });
  }

  // Botones +/-: respetan los nuevos límites globales (20-400) para
  // que el usuario pueda llegar al zoom programático de país y más allá.
  document.getElementById("cam-zoom-in").addEventListener("click", () => {
    setCameraDistance(Math.max(20, getCameraDistance() * 0.85));
  });
  document.getElementById("cam-zoom-out").addEventListener("click", () => {
    setCameraDistance(Math.min(400, getCameraDistance() * 1.18));
  });
  document.getElementById("cam-reset").addEventListener("click", () => {
    // Reset total: vuelve al meridiano 0 y limpia el estado de zoom.
    // Respeta userPausedRotation: si el usuario tenía la rotación
    // pausada, sigue pausada al volver a vista mundial.
    zoomedIn = false;
    const willRotate = !userPausedRotation;
    suppressWheelExit = true;
    chart.setOption({
      globe: {
        viewControl: {
          ...DEFAULT_VIEW,
          autoRotate: willRotate,
          animation: true,
          animationDurationUpdate: 600,
          animationEasingUpdate: "cubicOut",
        }
      }
    });
    rotating = willRotate;
    syncRotateBtnUI(willRotate);
    setTimeout(() => { suppressWheelExit = false; }, 700);
  });

  const rotateBtn = document.getElementById("cam-rotate");
  // ``rotating`` refleja el estado actual del autoRotate de ECharts-GL
  // (puede estar false por estar en ZOOMED-IN aunque userPausedRotation
  // sea false). Solo se usa para sincronizar la UI.
  let rotating = true;
  rotateBtn.addEventListener("click", () => {
    // El botón conmuta la INTENCIÓN del usuario, no el estado
    // instantáneo. La aplicamos siempre, salvo cuando estamos en
    // ZOOMED-IN (en cuyo caso solo se guarda la preferencia y se
    // aplicará al salir del zoom).
    userPausedRotation = !userPausedRotation;
    if (zoomedIn) {
      // En zoom el botón solo guarda la preferencia futura.
      // Visualmente sigue mostrando "▶" (pausado) porque la cámara
      // está realmente parada por el zoom; no la cambiamos para no
      // confundir al usuario.
      syncRotateBtnUI(false);
      return;
    }
    // En vista mundial: aplicar inmediatamente.
    rotating = !userPausedRotation;
    chart.setOption({
      globe: { viewControl: { autoRotate: rotating } }
    });
    syncRotateBtnUI(rotating);
  });

  // ============================================================
  // Puente con Python
  // ============================================================
  function setupBridge() {
    if (typeof QWebChannel === "undefined") {
      console.warn("QWebChannel no disponible — modo demo.");
      loadSampleData();
      return;
    }
    new QWebChannel(qt.webChannelTransport, (channel) => {
      state.bridge = channel.objects.bridge;
      if (state.bridge && state.bridge.on_globe_ready) {
        state.bridge.on_globe_ready();
      }
    });
  }

  // ============================================================
  // API expuesta a Python
  // ============================================================
  window.shakevisionGlobe = {
    setDevices(json) {
      state.devices = (typeof json === "string" ? JSON.parse(json) : json) || [];
      applyActiveLayer();
    },
    setEarthquakes(json) {
      state.quakes = (typeof json === "string" ? JSON.parse(json) : json) || [];
      applyActiveLayer();
    },
    setLayer(name) {
      const btn = document.querySelector(`.seg-btn[data-layer="${name}"]`);
      if (btn) btn.click();
    },
    setI18n(json) {
      // Python empuja la tabla completa de traducciones.
      // Refresca leyenda + contador inmediatamente para que el
      // cambio de idioma se vea sin esperar al próximo data push.
      i18nTable = (typeof json === "string" ? JSON.parse(json) : json) || {};
      applyStaticI18n();
      try { updateLegend(); updateCounter(); } catch (e) { /* aún sin datos */ }
    },
  };

  // ============================================================
  // Datos de muestra (modo standalone para pruebas en navegador)
  // ============================================================
  function loadSampleData() {
    state.devices = [
      { network: "AM", code: "R0E05", lat: 40.4, lng: -3.7, elevation: 650,
        site: "Madrid", provider: "shakenet" },
      { network: "AM", code: "RB5E8", lat: 41.9, lng: 12.5, elevation: 45,
        site: "Roma", provider: "shakenet" },
      { network: "IU", code: "ANMO", lat: 34.9, lng: -106.5, elevation: 1820,
        site: "Albuquerque NM", provider: "usgs" },
      { network: "IU", code: "PMSA", lat: -64.8, lng: -64.0, elevation: 40,
        site: "Palmer Station Antarctica", provider: "usgs" },
    ];
    state.quakes = [
      { id: "x1", ts: Date.now()/1000 - 3600,  lat: 35.7, lng: 139.7, depth: 30, mag: 5.4, place: "Tokio", pager: "yellow" },
      { id: "x2", ts: Date.now()/1000 - 7200,  lat: -33.4, lng: -70.7, depth: 50, mag: 6.2, place: "Santiago", pager: "orange" },
      { id: "x3", ts: Date.now()/1000 - 9000,  lat: 38.9, lng: -77.0, depth: 5,  mag: 3.1, place: "DC" },
      { id: "x4", ts: Date.now()/1000 - 1200,  lat: 28.0, lng: 86.9, depth: 25, mag: 7.8, place: "Himalaya", pager: "red" },
    ];
    applyActiveLayer();
  }

  setupBridge();
  applyActiveLayer();
})();
