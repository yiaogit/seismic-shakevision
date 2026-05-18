/* ============================================================
   SeismicGuard · Globo · Implementación con ECharts-GL.
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
    // ─── Modo visual del globo ───
    // "night"        → texto-noche con luces de ciudades (clásico)
    // "day"          → relieve topográfico iluminado (paramétrico, sin
    //                  texturas adicionales: reutiliza earth-topology)
    // "holographic"  → globo sin textura, shading=color, bloom alto.
    //                  Se activa con LayerModeManager="professional".
    // Python (globe_view.py) deriva el modo de Theme × LayerMode y lo
    // empuja vía window.shakevisionGlobe.setVisualMode().
    visualMode: "night",
    // v0.6 G: tema activo de la app Qt (dark/light). Python lo empuja
    // junto al modo. Solo influye en el sub-modo "holographic" — los
    // modos day/night ya son theme-specific por definición.
    visualTheme: "dark",
    // v0.6 D: textura "Blue Marble" para modo día. Se asume null hasta
    // que el preflight detecte el JPG opcional. Si existe se usa; si
    // no, fallback a la topología B/N gris.
    dayTextureUrl: null,
    // v0.6 E: GeoJSON de fronteras de países (lazy-loaded para Pro).
    // null = no cargado; [] = cargado pero vacío; [...] = listo.
    countryBorderLines: null,
    // v0.6 Phase 10: etiquetas de nombre de país (también de world.json).
    // Cada item: { value: [lng,lat], name: "...", rank: int }.
    // ``rank`` es el puesto por área (0 = el más grande) — se usa
    // para mostrar solo los primeros N en vistas alejadas.
    countryLabels: null,
    // Idioma actual de la UI (en/es/zh/fr). Lo empuja Python en
    // setI18n() para que las etiquetas de país se traduzcan.
    lang: "en",
    // v0.6 Phase 13: IDs de eventos sísmicos en favoritos. Python lo
    // empuja con setFavoritedEventIds(); el JS resalta esos puntos
    // con un símbolo ★ y borde dorado.
    favoritedEventIds: new Set(),
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

  // ============================================================
  // Inicialización del chart con auto-recuperación de WebGL/canvas
  // ------------------------------------------------------------
  // Problema observado en Windows: tras minimizar/restaurar la ventana
  // o cuando el proceso GPU de Chromium reinicia, el contexto WebGL
  // del canvas se pierde y zrender se queda con un "root" null. El
  // siguiente setOption explota con
  //     Uncaught TypeError: Cannot read properties of null
  //                          (reading 'getRoots')
  //
  // Mecánica de recuperación:
  //   1. Mantenemos ``chart`` en una variable mutable (no const).
  //   2. ``installContextLostHandler()`` engancha 'webglcontextlost'
  //      y 'webglcontextrestored' al canvas para reaccionar inmediato.
  //   3. ``safeSetOption()`` envuelve TODOS los setOption: si captura
  //      el error de getRoots o detecta isDisposed/getZr() null,
  //      reconstruye la instancia entera y re-aplica el último estado.
  //   4. ``visibilitychange`` y un latido de 10 s vigilan el estado
  //      por si el evento webglcontextlost no se disparara en algún
  //      driver Windows / GPU.
  // ============================================================
  const container = document.getElementById("globe");
  // ``chart`` es ``let`` para poder sustituirlo al reinicializar.
  let chart = createChart();

  // v0.6 Phase 13-fix v6: si el contenedor estaba a 0×0 al cargar
  // (caso típico cuando QWebEngineView aún se está layouting), el
  // echarts.init imprime "Dom has no width or height" y el
  // coordinateSystem 'globe' queda a medio bootstrap →
  // chart.convertToPixel devuelve null permanentemente → el right-
  // click hit-test nunca encuentra ningún sismo.
  //
  // ResizeObserver es más fiable que window.resize cuando el
  // tamaño del contenedor cambia por relayout interno de Qt en
  // lugar de por cambio de tamaño de ventana. Al primer cambio
  // a dimensiones reales forzamos chart.resize() para que echarts
  // re-bootstrappee la cámara del globo. Una vez ya tiene buenas
  // dimensiones, seguimos llamando resize en cada cambio (no es
  // caro) para mantener todo sincronizado.
  // ResizeObserver para mantener chart.resize() sincronizado con
  // cambios de layout (Qt no siempre dispara window.resize).
  //
  // v6 IMPORTANTE: una versión previa de este bloque llamaba a
  // rebuildChart() la primera vez que el contenedor pasaba de 0×0 a
  // tener dimensiones reales, con la idea de re-bootstrappear el
  // coordinateSystem 'globe'. PERO rebuildChart() hace
  // chart.dispose() + crea uno nuevo, y todos los chart.on(...)
  // (incluyendo el click handler que dispatcha station_clicked /
  // earthquake_clicked al puente Python) viven en la instancia VIEJA
  // → después del rebuild, el nuevo chart no tiene listeners → todos
  // los clicks dejan de responder. Por eso ahora SOLO llamamos a
  // resize(), nunca rebuild. El warning "Dom has no width or height"
  // del primer init en container 0×0 se ignora — resize() después
  // arregla el layout.
  if (typeof ResizeObserver !== "undefined") {
    try {
      const ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const cr = entry.contentRect;
          if (cr.width <= 0 || cr.height <= 0) continue;
          if (isChartAlive(chart)) {
            try { chart.resize(); } catch (_) { /* ignore */ }
          }
        }
      });
      ro.observe(container);
    } catch (_) { /* ResizeObserver no soportado — usamos window.resize */ }
  }

  function createChart() {
    const c = echarts.init(container, null, { renderer: "canvas" });
    installContextLostHandler(c);
    return c;
  }

  function installContextLostHandler(c) {
    // El canvas vive dentro del div container; ECharts lo crea como
    // primer hijo. Lo buscamos por type para resistir versiones.
    const canvas = container.querySelector("canvas");
    if (!canvas) return;
    canvas.addEventListener("webglcontextlost", (ev) => {
      // Sin preventDefault Chromium NO dispara webglcontextrestored.
      ev.preventDefault();
      console.warn("Globe: WebGL context lost — programando recuperación");
      // Pequeño debounce: a veces Chromium emite lost+restored seguidos
      setTimeout(rebuildChart, 250);
    }, false);
    canvas.addEventListener("webglcontextrestored", () => {
      console.info("Globe: WebGL context restored — reconstruyendo chart");
      rebuildChart();
    }, false);
  }

  function isChartAlive(c) {
    try {
      if (!c || typeof c.isDisposed !== "function") return false;
      if (c.isDisposed()) return false;
      const zr = c.getZr && c.getZr();
      // zrender expone getRoots(); si throw o devuelve null, está roto.
      if (!zr || typeof zr.painter === "undefined") return false;
      return true;
    } catch (_) {
      return false;
    }
  }

  function rebuildChart() {
    try { if (chart) chart.dispose(); } catch (_) { /* ignore */ }
    chart = createChart();
    // Restaurar el estado completo: base option + modo visual + datos.
    // ``baseOption`` se construyó con el modo visual inicial — si el
    // usuario lo cambió en caliente, re-aplicamos el modo guardado en
    // state.visualMode para evitar que el rebuild vuelva al "modo de
    // arranque" tras una pérdida de contexto WebGL.
    try {
      chart.setOption({
        backgroundColor: "transparent",
        globe: buildGlobeBase(state.visualMode),
        series: [],
      });
    } catch (_) { /* ignore primer pinta */ }
    // ``applyActiveLayer`` repinta todas las series con los datos
    // cacheados en ``state``; si aún no hay datos, no hace nada visible.
    try { applyActiveLayer(); } catch (_) { /* idem */ }
  }

  // Wrapper defensivo de setOption. Devuelve true si OK, false si falló.
  function safeSetOption(opt, extra) {
    if (!isChartAlive(chart)) {
      console.warn("Globe: chart no vivo, reconstruyendo antes de setOption");
      rebuildChart();
    }
    try {
      if (extra !== undefined) chart.setOption(opt, extra);
      else chart.setOption(opt);
      return true;
    } catch (err) {
      const msg = (err && err.message) || String(err);
      // Cualquier error que huela a "root null" / "getRoots" / "dispose":
      if (/getRoots|root|dispose|disposed|null/i.test(msg)) {
        console.warn("Globe: setOption falló (" + msg + "), reconstruyendo");
        rebuildChart();
        try {
          if (extra !== undefined) chart.setOption(opt, extra);
          else chart.setOption(opt);
          return true;
        } catch (err2) {
          console.error("Globe: setOption falló también tras rebuild", err2);
          return false;
        }
      }
      // Otros errores: re-lanzar para no enmascarar bugs reales.
      throw err;
    }
  }

  window.addEventListener("resize", () => {
    if (isChartAlive(chart)) {
      try { chart.resize(); } catch (_) { rebuildChart(); }
    } else {
      rebuildChart();
    }
  });

  // Cuando la pestaña/ventana vuelve a ser visible, verifica salud.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && !isChartAlive(chart)) {
      console.warn("Globe: chart muerto al recuperar visibilidad, rebuild");
      rebuildChart();
    }
  });

  // Latido de seguridad cada 10 s — en algunos drivers Windows el
  // evento webglcontextlost no llega y solo descubrimos el problema
  // al siguiente push de datos. El check es baratísimo.
  setInterval(() => {
    if (!isChartAlive(chart)) {
      console.warn("Globe: heartbeat detectó chart muerto, rebuild");
      rebuildChart();
    }
  }, 10000);

  // ============================================================
  // Modos visuales — paramétricos (sin texturas adicionales)
  // ------------------------------------------------------------
  // Cada modo describe ÚNICAMENTE las propiedades visuales del
  // globo (textura, shading, luces, post-effects). La cámara,
  // controles y series se mantienen iguales — así un cambio de
  // modo nunca pierde la posición ni los datos del usuario.
  //
  // Filosofía: cero assets nuevos. Reutilizamos los dos PNG ya
  // descargados (earth-night.jpg + earth-topology.png) más una
  // variante "color puro" para el modo holográfico.
  // ============================================================
  const VISUAL_MODES = {
    // Noche — v0.6 Phase 12.4 REPLANTEO COMPLETO:
    //
    // Por qué los intentos anteriores fallaron: Black Marble es una
    // textura inherentemente ~99% negra. Bajo CUALQUIER iluminación,
    // si renderizas píxeles 0/255 obtienes negro. Las "ciudades" son
    // píxeles aislados de 100-200/255 que a distancia se vuelven
    // sub-pixel y desaparecen visualmente. No es un problema de
    // shading, es la textura.
    //
    // Solución estándar de la industria (Cesium, NASA Worldview,
    // Google Earth at night): NO usar Black Marble como base. Usar
    // Blue Marble (textura DIURNA) oscurecida + luz de luna fría +
    // overlay de luces de ciudad encima. Resultado: continentes
    // perfectamente visibles en tono azul-noche, ciudades brillan
    // por encima.
    //
    // Implementación:
    //   * baseTexture = earth-day.jpg (Blue Marble — continentes claros)
    //   * baseColor multiplica oscureciendo → tono "luz lunar"
    //   * ambient azul frío + main blanco como reflejo lunar
    //   * layers[]: capa adicional con earth-night.jpg como
    //     "emisión" → ciudades brillan sin alterar el resto
    //   * bloom moderado realza ciudades en bloom-aware
    //
    // ECharts-GL globe.layers requiere la propiedad name + type
    // "blend" o "overlay". Usamos "blend" con blendTo="emission"
    // para que la noche se sume sin restar contraste a la base.
    night: {
      baseTexture: "lib/earth-day.jpg",
      heightTexture: "lib/earth-topology.png",
      shading: "lambert",
      // baseColor multiplicativo: oscurece + tinta toda la textura
      // hacia azul-noche. Sin esto el modo noche se vería como un
      // día normal apenas atenuado.
      baseColor: "#3a4a6e",
      environment: "#000010",
      light: {
        // Ambient azul: simula luz dispersa de la atmósfera nocturna.
        ambient: { intensity: 0.55, color: "#5a7aa8" },
        // Main = "luz lunar" — fría, suave, desde un ángulo bajo.
        main:    { intensity: 0.65, alpha: 25, color: "#dce6ff" },
      },
      // Capa adicional de luces de ciudad encima del Blue Marble.
      // Si earth-night.jpg no carga (ej. install_libs no se corrió)
      // la capa simplemente no aporta nada — el resto sigue OK.
      layers: [
        {
          type: "blend",
          blendTo: "emission",
          texture: "lib/earth-night.jpg",
          intensity: 0.85,
        },
      ],
      postEffect: {
        enable: true,
        // Bloom moderado: las luces de ciudad (capa emisiva) generan
        // halo, pero el cuerpo del globo no se "lava".
        bloom: { enable: true, intensity: 0.35 },
        SSAO:  { enable: true, radius: 1.2, intensity: 0.8 },
      },
    },
    // Día (v0.6 D dual-source):
    //   * Si existe ``lib/earth-day.jpg`` (Blue Marble) → satélite real:
    //     shading=realistic + textura Blue Marble + entorno cielo →
    //     se ve como la portada de un atlas profesional.
    //   * Si NO existe → fallback al topology PNG: lambert + tierra
    //     azul-verde + entorno crepúsculo, como un globo de despacho.
    //
    // ``baseTexture`` lo decide ``buildGlobeBase()`` en runtime leyendo
    // state.dayTextureUrl (poblado por preflightDayTexture al arrancar).
    // Las claves listadas aquí son el VALOR PROVISIONAL del fallback —
    // se sobreescriben dinámicamente si tenemos Blue Marble.
    day: {
      baseTexture: "lib/earth-topology.png",
      heightTexture: "lib/earth-topology.png",
      shading: "lambert",
      baseColor: "#5a7d8c",
      environment: "#bfd8e8",
      light: {
        ambient: { intensity: 1.05, color: "#e0ecf5" },
        main:    { intensity: 1.20, alpha: 45, color: "#fff6e2" },
      },
      postEffect: {
        enable: true,
        bloom: { enable: false },
        SSAO:  { enable: false },
      },
    },
    // Holográfico (Modo Profesional) — v0.6 dual-theme:
    // El modo "holographic" base. La variante (dark vs light) se
    // mezcla on-demand desde HOLOGRAPHIC_VARIANTS más abajo según
    // el tema activo de la app (Theme manager Python).
    //
    // Filosofía:
    //   * Tema OSCURO → environment negro espacio profundo, luces cyan
    //     puras → sensación "puente de mando nocturno".
    //   * Tema CLARO  → environment azul crepúsculo + luces más cálidas
    //     → sensación "comando táctico al amanecer".
    // Ambas variantes comparten textura topology + bloom alto.
    holographic: {
      baseTexture: "lib/earth-topology.png",
      heightTexture: "lib/earth-topology.png",
      shading: "lambert",
      baseColor: "#062a3d",
      environment: "#000814",
      light: {
        ambient: { intensity: 1.20, color: "#22d3ee" },
        main:    { intensity: 0.55, alpha: 50, color: "#7dd3fc" },
      },
      postEffect: {
        enable: true,
        bloom: { enable: true, intensity: 0.85 },
        SSAO:  { enable: false },
      },
    },
  };

  // ── v0.6 G: variantes de Modo Profesional según tema (dark/light)
  // El usuario pidió "专业版的宇宙部分颜色根据 白天黑夜颜色进行改变":
  // el espacio negro puro del modo Pro era demasiado severo en tema
  // claro. Esta tabla mezcla un puñado de claves por encima del modo
  // base para suavizar a "azul crepúsculo" en light, mantener negro
  // espacio en dark.
  const HOLOGRAPHIC_VARIANTS = {
    dark: {
      // Ya es el default — repetimos por simetría y para que el merge
      // sea explícito, no dependa del fallback.
      environment: "#000814",
      baseColor:   "#062a3d",
      light: {
        ambient: { intensity: 1.20, color: "#22d3ee" },
        main:    { intensity: 0.55, alpha: 50, color: "#7dd3fc" },
      },
    },
    light: {
      // Azul crepúsculo profundo — ni puro negro ni cielo diurno.
      // Las luces ambientales tienen toque más cálido para no chocar
      // con la UI Qt clara que envuelve el WebView.
      environment: "#15233a",
      baseColor:   "#1a3a5c",
      light: {
        ambient: { intensity: 1.05, color: "#7dd3fc" },
        main:    { intensity: 0.65, alpha: 50, color: "#bae6fd" },
      },
    },
  };

  function visualConfigFor(mode) {
    const base = VISUAL_MODES[mode] || VISUAL_MODES.night;
    // v0.6 G: holographic adopta variante dark/light según tema activo.
    if (mode === "holographic") {
      const theme = state.visualTheme || "dark";
      const variant = HOLOGRAPHIC_VARIANTS[theme] || HOLOGRAPHIC_VARIANTS.dark;
      return Object.assign({}, base, variant);
    }
    // v0.6 D: day usa Blue Marble si está disponible.
    if (mode === "day" && state.dayTextureUrl) {
      return Object.assign({}, base, {
        baseTexture: state.dayTextureUrl,
        heightTexture: state.dayTextureUrl,  // mismo, da relieve sutil
        shading: "realistic",
        realisticMaterial: { roughness: 0.85, metalness: 0 },
        // Con textura real podemos subir el bloom 0 y dejar el realismo
        // hablar por sí mismo — y el cielo más neutro porque la propia
        // textura ya tiene mucho azul océano.
        environment: "#aac4dc",
        light: {
          ambient: { intensity: 0.45, color: "#ffffff" },
          main:    { intensity: 1.10, alpha: 50, color: "#fff6e2" },
        },
      });
    }
    return base;
  }

  // ============================================================
  // v0.6 D — Preflight de la textura Blue Marble (opcional)
  // ============================================================
  // ECharts intenta cargar baseTexture con un <img>; si el archivo no
  // existe, ECharts silenciosamente pinta el globo del baseColor. No
  // queremos eso para el día — preferimos el fallback explícito a
  // earth-topology.png. Así que hacemos un Image() de prueba al
  // arrancar; si carga OK, marcamos state.dayTextureUrl y re-aplicamos
  // el modo si toca.
  function preflightDayTexture() {
    const url = "lib/earth-day.jpg";
    const img = new Image();
    img.onload = () => {
      console.info("Globe: Blue Marble disponible → usando textura real");
      state.dayTextureUrl = url;
      // Si el usuario ya está en modo día, re-aplicar para que se vea
      if (state.visualMode === "day") {
        applyVisualMode("day", state.visualTheme);
      }
    };
    img.onerror = () => {
      console.info("Globe: earth-day.jpg no encontrado — usando "
                   + "fallback topológico (modo día seguirá visible)");
    };
    img.src = url;
  }

  // ============================================================
  // v0.6 E — Loader de fronteras de países (opcional)
  // ============================================================
  // Carga lib/world.json (GeoJSON FeatureCollection) y lo convierte a
  // ``lines3D`` de ECharts: cada anillo exterior de cada Polygon/
  // MultiPolygon → una polilínea sobre la esfera. Cyan + glow sutil.
  // Solo se RENDERIZA en modo holographic — en day/night se omite
  // para no ensuciar la vista satélite.
  //
  // GeoJSON esperado: features con geometry.type "Polygon" o
  // "MultiPolygon" (cualquier ne_50m_admin_0_countries.geojson sirve).
  function loadCountryBordersOnce() {
    if (state.countryBorderLines !== null) return;   // ya cargado
    const url = "lib/world.json";
    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(geoJson => {
        const lines = geoJsonToLines3D(geoJson);
        const labels = geoJsonToCountryLabels(geoJson);
        state.countryBorderLines = lines;
        state.countryLabels = labels;
        console.info(
          "Globe: world.json cargado — " + lines.length + " polilíneas, "
          + labels.length + " etiquetas de país");
        // Si el usuario ya está en holographic, re-renderizar
        if (state.visualMode === "holographic") {
          applyActiveLayer();
        }
      })
      .catch(err => {
        console.info(
          "Globe: world.json no encontrado/inválido — Pro mode "
          + "seguirá sin bordes de país. Error: " + err.message);
        state.countryBorderLines = [];   // marca "intentado, vacío"
        state.countryLabels = [];
      });
  }

  function geoJsonToLines3D(geoJson) {
    // Devuelve [{ coords: [[lng,lat], ...] }, ...]
    const out = [];
    const features = (geoJson && geoJson.features) || [];
    for (const f of features) {
      const g = f.geometry;
      if (!g) continue;
      if (g.type === "Polygon") {
        for (const ring of g.coordinates) {
          out.push({ coords: ring });
        }
      } else if (g.type === "MultiPolygon") {
        for (const poly of g.coordinates) {
          for (const ring of poly) {
            out.push({ coords: ring });
          }
        }
      }
    }
    return out;
  }

  // ============================================================
  // v0.6 Phase 10 — Etiquetas de país sobre el globo holográfico
  // ============================================================
  // Por cada Feature:
  //   1. Sacar un punto representativo (LABEL_X/Y precomputado por
  //      Natural Earth si está, sino bbox-center del polígono más
  //      grande — más rápido que centroide ponderado y suficiente
  //      visualmente para etiquetas).
  //   2. Calcular el área del bbox (para ranking por importancia).
  //   3. Guardar TODAS las traducciones disponibles (name_en, name_zh
  //      etc.) — al cambiar de idioma en caliente no hay que volver
  //      a cargar el GeoJSON.
  function geoJsonToCountryLabels(geoJson) {
    const features = (geoJson && geoJson.features) || [];
    const out = [];
    for (const f of features) {
      const p = f.properties || {};
      const point = labelPoint(f.geometry, p);
      if (!point) continue;
      const area = bboxAreaOfGeometry(f.geometry);
      out.push({
        coord: point,        // [lng, lat]
        area: area,
        // Diccionario de traducciones — Natural Earth ne_110m usa
        // claves mayúscula. Defendemos las dos por si el GeoJSON
        // viene de otro origen con minúsculas.
        names: {
          en: p.NAME_EN || p.name_en || p.NAME || p.name || "?",
          es: p.NAME_ES || p.name_es,
          zh: p.NAME_ZH || p.name_zh,
          fr: p.NAME_FR || p.name_fr,
        },
      });
    }
    // Sort by area DESC. El índice resultante es el "rank":
    // 0 = país más grande, len-1 = más pequeño.
    out.sort((a, b) => b.area - a.area);
    for (let i = 0; i < out.length; i++) out[i].rank = i;
    return out;
  }

  function labelPoint(geom, props) {
    if (!geom) return null;
    // Natural Earth ofrece LABEL_X / LABEL_Y precomputados para muchas
    // versiones — son posiciones manualmente ajustadas (mejor que el
    // centroide para países raros tipo Chile / Noruega).
    const lx = props.LABEL_X !== undefined ? props.LABEL_X : props.label_x;
    const ly = props.LABEL_Y !== undefined ? props.LABEL_Y : props.label_y;
    if (typeof lx === "number" && typeof ly === "number") {
      return [lx, ly];
    }
    if (geom.type === "Polygon") {
      return bboxCenter(geom.coordinates[0]);
    }
    if (geom.type === "MultiPolygon") {
      // Tomamos el bbox del polígono más grande
      let best = null, bestArea = 0;
      for (const poly of geom.coordinates) {
        const ring = poly[0];
        const a = bboxAreaOfRing(ring);
        if (a > bestArea) { bestArea = a; best = ring; }
      }
      return best ? bboxCenter(best) : null;
    }
    return null;
  }

  function bboxCenter(ring) {
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    for (const pt of ring) {
      const x = pt[0], y = pt[1];
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    return [(minX + maxX) / 2, (minY + maxY) / 2];
  }

  function bboxAreaOfRing(ring) {
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    for (const pt of ring) {
      const x = pt[0], y = pt[1];
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    return (maxX - minX) * (maxY - minY);
  }

  function bboxAreaOfGeometry(geom) {
    if (!geom) return 0;
    if (geom.type === "Polygon") {
      return bboxAreaOfRing(geom.coordinates[0]);
    }
    if (geom.type === "MultiPolygon") {
      let total = 0;
      for (const poly of geom.coordinates) {
        total += bboxAreaOfRing(poly[0]);
      }
      return total;
    }
    return 0;
  }

  function pickCountryName(item, lang) {
    return (item.names[lang] || item.names.en || "?");
  }

  function buildGlobeBase(mode) {
    // Construye la sección ``globe`` con la apariencia del modo dado
    // + los parámetros invariantes (displacementScale, viewControl,
    // temporalSuperSampling). Se llama desde baseOption inicial y
    // desde applyVisualMode() al cambiar de modo en caliente.
    const v = visualConfigFor(mode);
    return {
      // displacementScale: 0  → la superficie queda perfectamente
      // esférica (sin relieve montañoso). Imprescindible para que
      // los puntos scatter3D se posicionen exactamente sobre las
      // coordenadas reportadas por USGS.
      displacementScale: 0,
      baseTexture:   v.baseTexture,
      heightTexture: v.heightTexture,
      shading:       v.shading,
      ...(v.baseColor          ? { baseColor: v.baseColor } : {}),
      ...(v.realisticMaterial  ? { realisticMaterial: v.realisticMaterial } : {}),
      // v12.4: propagar layers[] si el modo lo define (modo night usa
      // earth-night.jpg como capa emisiva de ciudades sobre la base
      // Blue Marble). Si el modo no tiene layers pasamos array vacío
      // para que ECharts sobreescriba la capa del modo anterior y no
      // queden luces de ciudad parpadeando en modo día/holographic.
      layers:        v.layers || [],
      environment:   v.environment,
      light:         v.light,
      postEffect:    v.postEffect,
      temporalSuperSampling: { enable: true },
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
    };
  }

  // baseOption ahora se construye a partir del modo visual actual.
  // Cualquier cambio en caliente (window.shakevisionGlobe.setVisualMode)
  // re-emite SOLO la parte ``globe`` vía safeSetOption(), preservando
  // cámara, series y zoom.
  const baseOption = {
    backgroundColor: "transparent",
    globe:  buildGlobeBase(state.visualMode),
    series: [],
  };

  safeSetOption(baseOption);

  // v0.6 D+E: lanzar preflights de assets opcionales. Estos son no
  // bloqueantes — si los archivos no existen el globo sigue funcionando
  // con los fallbacks ya configurados.
  preflightDayTexture();
  loadCountryBordersOnce();

  // ─── API pública: cambio de modo visual en caliente ───
  // v0.6: ahora acepta un segundo argumento ``theme`` ("dark" o
  // "light") usado SOLO por el modo holographic — los modos day/night
  // ya son theme-specific por definición. Python pasa el theme actual
  // en cada llamada para que el fondo del Modo Pro se ajuste.
  function applyVisualMode(mode, theme) {
    if (!VISUAL_MODES[mode]) {
      console.warn("Globe: modo visual desconocido", mode, "→ ignorado");
      return;
    }
    state.visualMode = mode;
    if (theme === "dark" || theme === "light") {
      state.visualTheme = theme;
    }
    const fresh = buildGlobeBase(mode);
    safeSetOption({ globe: fresh });
    // v0.6 E: re-pintar series para meter/quitar fronteras según modo
    applyActiveLayer();
  }

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
          // v0.6 Phase 13: si el sismo está en favoritos, lo agrandamos
          // (+50% radio) y le añadimos un borde dorado para que destaque.
          const isFav = state.favoritedEventIds.has(q.id);
          return {
            value: [q.lng, q.lat],
            symbolSize: isFav ? Math.round(b.radius * 1.5) : b.radius,
            itemStyle: {
              color: b.color,
              opacity: 0.92,
              borderColor: isFav ? "#fcd34d" : undefined,  // amber-300
              borderWidth: isFav ? 2 : 0,
            },
            raw: q,
            kind: "quake",
          };
        }),
      });

      // v0.6 Phase 13: capa adicional con ★ encima de los sismos
      // favoritos. Usamos scatter3D con symbolSize=0 + label.show=true
      // para que el ★ aparezca como texto flotante centrado sobre
      // el punto, en lugar de un símbolo gráfico.
      const favoritedQuakes = state.quakes.filter(
        q => state.favoritedEventIds.has(q.id)
      );
      if (favoritedQuakes.length > 0) {
        series.push({
          name: "favorited_quakes",
          type: "scatter3D",
          coordinateSystem: "globe",
          silent: true,
          symbolSize: 0,
          label: {
            show: true,
            formatter: "★",
            color: "#fcd34d",   // amber-300, contrasta con todos los buckets
            fontSize: 14,
            fontWeight: 700,
            textBorderColor: "#1a1a1f",
            textBorderWidth: 2,
          },
          data: favoritedQuakes.map(q => ({
            value: [q.lng, q.lat],
            raw: q,
          })),
        });
      }

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

    // ── v0.6 E: fronteras de países (solo modo Pro/holographic) ──
    if (state.visualMode === "holographic"
        && Array.isArray(state.countryBorderLines)
        && state.countryBorderLines.length > 0) {
      series.push({
        name: "country_borders",
        type: "lines3D",
        coordinateSystem: "globe",
        silent: true,                  // no roban click a los puntos
        polyline: true,
        effect: { show: false },       // sin animación de "running line"
        blendMode: "lighter",          // sumar luz cyan
        lineStyle: {
          color: "#67e8f9",            // cyan-200 brillante
          width: 1,
          opacity: 0.55,
        },
        data: state.countryBorderLines,
      });
    }

    // ── v0.6 Phase 10/12.3: etiquetas de nombre de país (solo holographic) ──
    // v12.3 cambios:
    //   * MAX_LABELS 50 → 100 — España, Portugal, Países Bajos, Bélgica,
    //     Suiza, etc. caben ahora en el top 100 por área.
    //   * BLOCKLIST — algunas etiquetas se omiten por preferencia del
    //     usuario (sensibilidad política, redundancia, etc.). Se filtra
    //     por nombre EN (case-insensitive, en cualquier propiedad de
    //     traducción) para que la regla aplique en todos los idiomas.
    if (state.visualMode === "holographic"
        && Array.isArray(state.countryLabels)
        && state.countryLabels.length > 0) {
      const MAX_LABELS = 100;
      const lang = state.lang || "en";
      // v12.3: blocklist — usar nombre EN canónico de Natural Earth
      // (case-insensitive). Match parcial para tolerar variantes.
      const BLOCKLIST = new Set(["taiwan"]);
      const isBlocked = (item) => {
        const en = (item.names.en || "").toLowerCase();
        for (const b of BLOCKLIST) {
          if (en === b || en.includes(b)) return true;
        }
        return false;
      };
      const labelData = state.countryLabels
        .filter(c => c.rank < MAX_LABELS && !isBlocked(c))
        .map(c => ({
          value: c.coord,
          name: pickCountryName(c, lang),
        }));
      series.push({
        name: "country_labels",
        type: "scatter3D",
        coordinateSystem: "globe",
        silent: true,
        symbolSize: 0,        // punto invisible — solo queremos la etiqueta
        label: {
          show: true,
          formatter: "{b}",
          color: "#bae6fd",   // cyan-100 más claro que el borde para
                              // crear jerarquía visual
          fontSize: 10,
          fontWeight: 500,
          fontFamily: "-apple-system, 'Inter', 'Segoe UI', sans-serif",
          // Halo oscuro detrás del texto para legibilidad sobre el
          // globo iluminado:
          textBorderColor: "#001525",
          textBorderWidth: 3,
        },
        data: labelData,
      });
    }

    safeSetOption({
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
    safeSetOption({
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
    safeSetOption({
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

  // ─── Right-click favorito: FEATURE POSPUESTA ─────────────────────
  // Phase 13 introdujo "right-click sismo → toggle favorito" pero
  // tras 7 iteraciones (v1-v7) ninguna funcionó de forma fiable en
  // echarts-gl scatter3D. Los problemas encontrados:
  //   * convertToPixel para coord-sys 'globe' devuelve coords 3D
  //     mundo, no píxeles → hit-test manual rompe.
  //   * chart.on("contextmenu") no se forwardea para scatter3D.
  //   * chart.on("mouseup") con button===2 crashea echarts-gl al
  //     final de drag-rotaciones (getRoots null).
  //   * chart.on("mousedown") con button===2 tampoco daba
  //     params.data fiable.
  //   * rebuildChart() para arreglar init 0×0 destruía los listeners.
  //
  // Decisión: postponer la feature. El icono ★, los favoritos del
  // Profile dialog y FavoritesStore se mantienen (útiles para futura
  // re-implementación con UX alternativa — p.ej. botón "favoritar"
  // en el tooltip del click izquierdo, o desde el Profile dialog
  // mismo). Solo se quita el handler de evento del right-click.
  //
  // Sí mantenemos un preventDefault del menú contextual nativo del
  // browser dentro del contenedor del chart, porque sin él QtWebEngine
  // muestra "Reload / Inspect" al hacer right-click en el globo, lo
  // cual queda muy poco profesional.
  try {
    const dom = chart.getDom();
    if (dom) {
      dom.addEventListener("contextmenu", (e) => e.preventDefault());
    }
  } catch (_e) { /* registro defensivo */ }

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
    if (!isChartAlive(chart)) return 200;
    try {
      const opt = chart.getOption();
      return (opt.globe?.[0]?.viewControl?.distance) || 200;
    } catch (_) {
      return 200;
    }
  }

  function setCameraDistance(d) {
    safeSetOption({
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
    safeSetOption({
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
    safeSetOption({
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
    // v0.6 Phase 10: idioma actual para etiquetas de país. Acepta
    // "en" | "es" | "zh" | "fr". Cualquier otro valor → fallback a
    // "en" en pickCountryName.
    setLang(code) {
      if (typeof code !== "string") return;
      state.lang = code;
      // Si estamos en holographic, re-renderizar para que las
      // etiquetas cambien de idioma inmediatamente.
      if (state.visualMode === "holographic") {
        applyActiveLayer();
      }
    },
    currentLang() {
      return state.lang;
    },
    // v0.6 Phase 13: Python empuja la lista de IDs de sismos favoritos.
    // El JS re-renderiza para que esos puntos lleven una ★ encima
    // y un halo dorado más grueso.
    setFavoritedEventIds(jsonOrArray) {
      let ids;
      try {
        ids = (typeof jsonOrArray === "string")
          ? JSON.parse(jsonOrArray)
          : jsonOrArray;
      } catch (e) { ids = []; }
      state.favoritedEventIds = new Set(
        Array.isArray(ids) ? ids : []);
      applyActiveLayer();
    },
    currentFavoritedEventIds() {
      return Array.from(state.favoritedEventIds);
    },
    // Modo visual del globo. Acepta:
    //   * setVisualMode("day" | "night" | "holographic")
    //   * setVisualMode("holographic", "dark" | "light")   (v0.6 G)
    // Python lo deriva de Theme × LayerMode; el JS solo aplica.
    setVisualMode(mode, theme) {
      applyVisualMode(mode, theme);
    },
    currentVisualMode() {
      return state.visualMode;
    },
    currentVisualTheme() {
      return state.visualTheme;
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
