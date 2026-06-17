# Changelog

All notable changes to **SeismicGuard** (formerly **ShakeVision OpenData Monitor**) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.8.0.0] — 2026-06-17

🌟 **Release mayor** — reorganización de la app en torno al flujo
*evento → revisión → colección personal* y una reescritura completa del
módulo de **Replay** como navegador de formas de onda profesional.

Lo más destacado:

* **Replay reescrito** como navegador estático (zoom/pan, eje UTC absoluto,
  selección de banda, deconvolución a VEL/DISP/ACC, rotación ZNE→ZRT,
  llegadas teóricas P/S con TauP, espectrograma con escala dB, PSD, y
  exportación PNG/CSV/QuakeML). Se eliminó el antiguo reproductor tipo vídeo.
* **Centro de eventos** de nivel superior (tabla de sismos + estaciones
  cercanas con Δ°/km/categoría) como único punto de entrada a la revisión.
* **"Mi colección" (我的)** — nueva pestaña que reúne favoritos (sismos y
  estaciones) y registros (grabaciones STA/LTA + catálogo QuakeML), con
  reapertura de revisiones guardadas y "Abrir carpeta" para exportar.
* **Análisis**: estabilización del hodograma + azimut de polarización, PSD,
  presets de filtro reaplicables sin volver a descargar.
* Numerosas correcciones de UX, i18n y específicas de macOS/Windows.

> Las versiones 0.7.7 (auditoría/i18n) nunca se publicaron por separado; su
> contenido se integra aquí.

### Changed
- **En vivo: conmutador para mostrar/ocultar el espectrograma.** La barra
  superior de la pestaña en vivo trae un botón **"Espectrograma"** (la onda
  siempre visible); al ocultarlo, la traza ocupa todo el alto. No se añadió PSD
  en vivo (el espectrograma ya cubre el monitoreo de frecuencia; el PSD es para
  selección/análisis en Replay) ni botón para ocultar el osciloscopio (es la
  vista central y las herramientas cuelgan de ella).
- **"Mi colección": el bloque "Catálogo guardado" (QuakeML) se oculta si está
  vacío** (igual que las grabaciones, opción C). Es una función de analista
  —acumular tus picados P/S revisados como QuakeML estándar exportable—; al
  usuario casual ya no le muestra una tabla vacía.
- **Replay: botones para mostrar/ocultar el espectrograma y el PSD.** Con tres
  gráficas apretadas, ahora la barra superior tiene conmutadores
  **"Espectrograma"** y **"PSD"** (la de ondas siempre visible): ocultar una da
  más alto a las demás; las tres mantienen una altura mínima cuando se muestran.
- **Nueva pestaña de nivel superior "Mi colección" (我的) — reemplaza la
  pestaña "Local" del Workbench.** Reúne en el nivel superior (Globo/Datos/
  Eventos/Mi colección) lo que es del usuario, en dos bloques: **Favoritos**
  (★ sismos → doble clic revisa; ★ estaciones → doble clic la usa) y
  **Registros** (grabaciones STA/LTA — *solo si hay alguna*, opción C; +
  catálogo QuakeML), cada tabla con su acción (quitar favorito / eliminar /
  abrir). El Workbench baja a 4 sub-pestañas (análisis puro). ``FavoriteEvent``
  guarda ahora lat/lon/depth para que un favorito se pueda revisar siempre.
- **UX (2.ª ronda).** (1) La pestaña **"Local" se re-escanea sola** al abrirla
  (las grabaciones nuevas aparecen sin pulsar Refrescar). (2) Se **desambigua
  "Pro"**: el control segmentado de la cabecera pasa a **"Vista estándar / Vista
  pro"** (solo cambia la apariencia del globo/paleta) con tooltips que aclaran
  que NO es el Workbench. (3) El catálogo de eventos muestra **estado de carga /
  "sin sismos"** en vez de una tabla vacía. (4) En Replay, al revisar un evento
  el texto de la estación indica que es la **estación del evento (independiente
  de la estación en vivo de la barra)**.
- **UX: se eliminó la pestaña "Eventos" del Workbench (deduplicación).** El
  **centro de eventos de nivel superior** (Globo/Datos/Eventos, con tabla +
  estaciones cercanas) es ahora el único punto de entrada a eventos; el
  Workbench baja a 5 sub-pestañas (En vivo/Diario 24h/Hodograma/Replay/Local) y
  queda enfocado en análisis. (``EventListPanel`` sigue usándose dentro del
  centro de eventos.)
- **UX: doble clic en un evento del centro = revisar con la estación más
  cercana.** Antes, en el centro de eventos, el doble clic no hacía nada (solo
  el clic simple listaba estaciones). Ahora: clic simple → lista de estaciones
  cercanas (elegir a mano); doble clic → atajo que revisa con la más cercana,
  igual que la lista del Workbench. (Ambas pestañas "Eventos" se mantienen.)
- **UX (menos ruido en el Workbench).** La **tarjeta de intensidad** (MMI en
  tiempo real) ahora se muestra SOLO en la sub-pestaña "En vivo" (se oculta en
  Replay/Eventos/Local/etc., donde quedaba obsoleta y robaba espacio). En
  Replay, los cuatro botones de exportación (PNG / CSV / QuakeML / catálogo) se
  agrupan en un único menú **"Exportar ▾"**.

### Added
- **"Mi colección": reabrir una revisión del catálogo guardado.** Doble clic en
  una fila de **"Catálogo guardado"** vuelve a abrir esa revisión en Replay:
  fija la estación, una ventana que cubre los picks guardados, descarga y
  **re-dibuja los picks P/S originales** encima (sin TauP — los picks guardados
  son la referencia). Antes el catálogo solo se podía ver/eliminar; ahora se
  puede recuperar y seguir trabajando. (``CatalogStore.get_event`` +
  ``ReplayPanel.load_catalog_event``.)
- **"Mi colección": botón "Abrir carpeta" en Grabaciones y Catálogo.** Abre la
  carpeta correspondiente (``~/SeismicGuard/recordings`` / la de ``catalog.xml``)
  en el explorador del sistema para exportar los ficheros (MiniSEED / QuakeML) a
  otro software (ObsPy, SeisComP, SAC…). Crea la carpeta si aún no existe.
- **Favoritos: entradas con botón (el click-derecho del globo no era fiable).**
  Ahora se puede marcar/desmarcar favorito desde: (a) el **centro de eventos**
  — botón ☆ para el sismo seleccionado y ☆ para la estación cercana
  seleccionada (incluye estaciones, que antes NO tenían forma de favoritearse);
  (b) los **diálogos de click-izquierdo del globo** — el de sismo ofrece
  Revisar / ☆ Favorito / Cancelar, y el de estación Añadir al Workbench / ☆
  Favorito / Cancelar. "Mi colección" se refresca al instante.
- **Datos locales: botones de Eliminar + mecanismo aclarado.** Cada sección
  ("Grabaciones disparadas" / "Catálogo guardado") tiene su botón **Eliminar**
  (borra el ``.mseed`` o quita el evento del QuakeML, con confirmación) y un texto
  que explica qué es cada una: grabaciones = waveforms crudos auto-guardados al
  disparar STA/LTA; catálogo = picks revisados guardados desde Replay.
  ``CatalogStore.remove_event``.
- **UX: revisión de eventos más fluida.** (1) Al entrar a un evento, la ventana
  temporal se **ajusta automáticamente para cubrir P→S** (TauP en segundo plano,
  pre-obteniendo coords de estación) en vez de 600 s fijos — un teleseísmo ya no
  se abre con una ventana sin señal. (2) El botón **Cargar se resalta** y el
  estado guía ("pulsa Cargar para traer la forma de onda") cuando hay un evento
  preparado, evitando quedarse ante una figura vacía. (3) En "estaciones
  cercanas" la distancia se muestra en **grados + km + tipo (local/regional/
  teleseísmo)** para elegir mejor la estación. Ver ``docs/ux-review.md``.
- **Pestaña "Local" del Workbench + catálogo QuakeML persistente.** Nueva
  pestaña que lista (a) las **grabaciones** MiniSEED del detector STA/LTA
  (doble clic → abrir en Replay como navegador estático) y (b) el **catálogo
  guardado** de fases revisadas. En Replay, un botón **"Guardar en catálogo"**
  añade las fases P/S marcadas a un QuakeML local persistente
  (``~/SeismicGuard/catalog.xml``, vía ``CatalogStore``). ``recorder`` gana
  ``list_recordings`` / ``parse_recording_name`` (puros, con tests).
- **Centro de eventos: ventana del feed (día/semana/mes) + refrescar + "última
  actualización".** Barra superior: selector de ventana (amplía el feed USGS
  vía ``worker.set_period`` — solo agranda, así Globo/Datos no se ven afectados),
  botón de refresco manual (``refresh_now``) y la hora de la última
  actualización del catálogo (cierra el hueco de "frescura" del feed: antes no
  se sabía cuán reciente era el dato).
- **Centro de eventos (pestaña de nivel superior, junto a Globo/Datos) +
  estaciones cercanas.** Tabla de catálogo USGS a la izquierda; al seleccionar
  un sismo, a la derecha aparecen las **estaciones más cercanas** (Δ en grados,
  calculado en local sin red). Doble clic en una estación → revisa el evento en
  Replay CON ESA estación (cercana ⇒ ventana razonable ⇒ P/S dentro del dato).
  La revisión se **desacopla del flujo en vivo**: fija la estación directamente
  en Replay (``set_event_review``) sin tocar el combo ni conectar SeedLink
  (descarga del archivo IRIS). El **nombre del evento** se muestra en un banner
  del Replay. La pestaña "Eventos" del Workbench queda como salto rápido (doble
  clic → estación más cercana). Ver ``docs/events-feature-plan.md``;
  ``measurements.great_circle_degrees`` con tests.
- **Espectrograma: barra de color (dB) con contraste ajustable.** Leyenda de
  potencia a la derecha del mapa; arrastrarla mueve los niveles (contraste) en
  vivo. (``set_db_range`` sincroniza la barra; defensivo si la versión de
  pyqtgraph no trae ``ColorBarItem``.) El eje de frecuencia logarítmico queda
  pendiente — ``ImageItem`` necesitaría re-binning en log.
- **Modo kiosko (monitorización a pantalla completa).** ``F11`` alterna, ``Esc``
  sale: oculta la cabecera y la barra de pestañas para una vista limpia del
  globo/datos (estilo SWARM).
- **Workbench: pestaña "Eventos" — catálogo de sismos (USGS) navegable.**
  Tabla ordenable (hora / magnitud / profundidad / lugar) con el feed USGS;
  doble clic en un evento lo abre en Replay (misma ruta dirigida por evento que
  el clic en el globo, pero más práctica para elegir uno concreto — patrón EEV
  de SeisAn / lista de scolv). 3.er bloque del roadmap. (La exportación de las
  fases revisadas ya existe vía QuakeML por evento; un catálogo local
  persistente queda pendiente.)
- **Replay: panel de PSD (espectro de potencia del tramo seleccionado).**
  Tercer panel bajo el oscilograma y el espectrograma: al mover la caja amarilla
  se calcula la PSD de Welch del tramo (canal Z) y se dibuja potencia (dB) vs
  frecuencia, con una línea en la frecuencia dominante. Completa el 2.º bloque
  del roadmap (frecuencia + polarización). Función pura
  ``measurements.welch_psd`` con tests; ``WaveformPanel`` emite ``region_changed``
  y expone ``selected_segment``.
- **Hodograma: lectura de polarización (azimut + rectilinearidad).** Eigen-
  análisis 2-D de la covarianza E/N: muestra el azimut del eje principal
  (0–180°) y la rectilinearidad (0 ruido/circular → 1 lineal, típico de P).
  Estimación de dirección de una sola estación. (Inicio del 2.º bloque del
  roadmap.) Función pura ``measurements.polarization_azimuth`` con tests.

### Fixed
- **La suite de tests podía leer/BORRAR los datos reales del usuario.**
  ``QSettings(org, app)`` no respeta ``setPath``/``setDefaultFormat`` (en macOS
  lee el *plist* nativo real), así que el aislamiento por ``setPath`` no servía:
  un favorito real se colaba en `test_favorites_store` y, peor, los
  ``_reset_for_tests()`` → ``clear_all()`` borraban favoritos/uso/presets reales
  en el teardown. Ahora un ``tests/conftest.py`` parchea la fábrica
  ``_settings`` de cada almacén (favoritos, uso, GitHub, presets Shake) hacia un
  ``.ini`` en ``tmp_path`` por test; ``shake_presets`` y ``settings_backup`` se
  enrutan por ese mismo *seam*. La suite ya no toca el almacén nativo.
- **Empaquetado macOS: el .dmg ahora incluye pyobjc.** El job `build-macos`
  instalaba solo `.[dev]`, así que el binario publicado nunca tenía pyobjc y caía
  a los fallbacks solo-Qt (sin barra de título translúcida y, ahora, sin el
  arreglo del botón verde = zoom). Ahora instala `.[dev,macos]` y el spec declara
  `objc`/`AppKit`/`Foundation` como hidden imports (se cargan de forma perezosa
  y solo en darwin, invisibles al análisis estático).
- **macOS: maximizar y cerrar el Workbench dejaba una ventana NEGRA unos
  segundos.** El botón verde abría un *Space* a pantalla completa nativo; como
  la ventana se oculta (no se destruye) para conservar su estado, al cerrarla el
  Space quedaba en negro durante la animación de salida. Doble arreglo: (1) con
  pyobjc, el Workbench pasa a ``FullScreenAuxiliary`` → el botón verde hace
  *zoom* en el mismo Space en vez de abrir uno nuevo (también encaja mejor con el
  diseño multiventana/multimonitor); (2) sin pyobjc, ``closeEvent`` sale de
  pantalla completa y **aplaza el ``hide``** hasta que termina la animación, en
  vez de ocultar a mitad de transición.
- **Replay: elegir otro evento/tiempo no sobrescribía la traza anterior.** Ahora
  al seleccionar otro evento (o grabación) se limpia primero la traza/caché y se
  parte de cero (banner + "pulsa Cargar").
- **"Limpiar caché" no borraba las grabaciones del detector.** Vivían en
  ``~/SeismicGuard/`` (no en ~/.cache), así que ``clear_cache`` no las tocaba
  pese a decir lo contrario. Ahora ``clear_all`` borra también
  ``recordings/*.mseed`` y ``catalog.xml`` (``clear_recordings``); docstring
  corregida.
- **Estaciones cercanas duplicadas.** El catálogo IRIS puede repetir una misma
  estación (varias épocas); ahora se deduplica por (red, código).
- **La pestaña "Eventos" no se traducía** (se quedaba en "Events"): faltaba en el
  re-traducido de las pestañas; ahora se actualiza con el idioma.
- **Las pestañas "Datos" y "Eventos" compartían icono.** Eventos estrena su
  propio icono (lista) — ``assets/icons/events.png``.
- **Revisión de evento lenta / "no muestra".** La descarga va contra IRIS
  dataselect (red, hasta 60 s); ahora la ventana auto se acota a 30 min (descargas
  más pequeñas) y hay feedback "localizando estación / calculando ventana…" para
  que no parezca colgado; si falla, el estado vuelve a "pulsa Cargar".
- **Centro de eventos: gran hueco vacío arriba.** El splitter de las tablas no
  tenía ``stretch`` y quedaba a su tamaño mínimo; ahora ocupa todo el alto.
- **Estaciones cercanas recomendaban Raspberry Shake (no reproducibles).** La
  revisión descarga de IRIS dataselect, que NO sirve la red AM (Shake). Ahora la
  lista de "estaciones cercanas" (y el auto-más-cercana del doble clic) se filtra
  a redes profesionales reproducibles (provider ``usgs``: IU/US…).
- **Espectrograma / PSD aplastados bajo el splitter.** Sin altura mínima, el
  splitter los reducía a una franja donde no se leían los ticks de frecuencia.
  Ahora tienen ``minimumHeight`` (140 px) — siguen siendo redimensionables.
- **Llegadas teóricas P/S "flotando" lejos del dato (eventos lejanos).** En un
  teleseísmo P/S llegan mucho después del origen y caían fuera de la ventana de
  600 s, apareciendo como líneas sueltas a la derecha (y estiraban la vista).
  Ahora: (1) los marcadores se añaden con ``ignoreBounds`` (no estiran el eje);
  (2) solo se dibujan las fases DENTRO de la ventana cargada; (3) si quedan
  fuera, un aviso indica la distancia epicentral Δ y a cuántos segundos del
  inicio llega la primera ("aumenta la duración"). El estado de "P/S
  superpuestas" ahora incluye **Δ (distancia epicentral)** para distinguir
  local de teleseísmo de un vistazo.
- **Barra lateral: las cabeceras de las secciones colapsables salían
  recortadas al expandir varias.** El contenido se ponía directo sobre el
  panel sin scroll, así que al exceder la altura de la ventana Qt comprimía
  los widgets y cortaba los títulos (STA/LTA, Sonido). Ahora todo el contenido
  vive en un ``QScrollArea`` (ancho fijo 300, sin scroll horizontal): si no
  cabe, aparece barra vertical y no se recorta nada.
- **Replay: la selección (y el zoom) saltaban al inicio al cambiar
  filtro/rotación/salida.** Cada re-render llamaba a ``load_static`` que
  reseteaba la región al 5–15 % y ajustaba a toda la traza. Ahora, si la
  ventana temporal es la MISMA (mismo dato, solo re-filtrado/rotado/deconv),
  se CONSERVAN el zoom y la región del usuario; solo una descarga nueva los
  reinicia. El sincronizado de las 3 cajas se blinda con try/finally para no
  dejar la bandera ``_syncing_region`` atascada.
- **La caja amarilla de selección no mostraba datos al arrastrarla.** Regresión
  al ponerla en las 3 trazas: el slot conectado a ``sigRegionChanged`` recibía
  el ``region`` como argumento y sobrescribía el canal por defecto del lambda →
  ``KeyError`` y la lectura no se actualizaba. Se absorbe el argumento
  (``lambda *_a, src_ch=ch: …``); ahora arrastrar cualquiera de las 3 cajas
  sincroniza las otras y refresca pico/RMS/frecuencia/S-P.
- **Hodograma inestable / "respiración" del zoom.** Tres causas, todas de
  refresco/render: (1) se repintaba a cada tick (~30 FPS) → ahora ~12 FPS
  (puerta temporal); (2) el auto-rango era un EMA simétrico que hacía zoom
  in/out constante → ahora **peak-hold** (crece al máximo, decae ≈3%/frame);
  (3) la ventana se contaba con la frecuencia de construcción → ahora con el
  ``dt`` real de la instantánea (1.5 s son 1.5 s a cualquier frecuencia).
- **Osciloscopio: el cursor en cruz ahora se engancha al dato y muestra
  tiempo + amplitud.** Antes no había snap ni lectura. El crosshair se
  sincroniza en las 3 trazas (misma X), se ENGANCHA a la muestra más cercana,
  y una lectura (cabecera) muestra la hora UTC + la amplitud de esa traza en la
  unidad vigente (counts / m/s / m / m/s²). Patrón SWARM/Snuffler.
- **La caja de selección amarilla solo afectaba a BHZ.** La región vivía solo
  en la traza Z; ahora hay una en CADA traza (Z/N/E), sincronizadas, así la
  selección se ve y arrastra en las tres.
- **Presets de banda del filtro: texto recortado en la barra lateral.** Las
  etiquetas largas ("体波1–10"…) se cortaban; ahora son cortas (体波/面波/区域/
  关闭) con el rango en Hz en el tooltip.

### Added
- **Replay: salida en unidades físicas por deconvolución completa
  (Velocidad / Desplazamiento / Aceleración).** Nuevo selector de salida
  (Counts / m/s / m / m/s²): para ≠Counts se quita la respuesta instrumental
  de TODO el Stream con ObsPy (``remove_response``, que empareja por canal —
  funciona con BH1/BH2), en segundo plano y cacheado por salida. El eje y el
  readout muestran la unidad correcta con prefijo métrico. Sustituye, en
  Replay, la aproximación escalar por sensibilidad (su botón "m/s" se oculta;
  ``WaveformPanel`` gana ``set_amp_unit_override`` + ``ResponseService``
  ``inventory_for``). Degrada con gracia a Counts si falta metadata/red.
- **Filtro: presets de banda (un clic) + re-filtrado de Replay sin
  re-descargar.** La sección de filtro de la barra lateral gana botones de
  banda sísmica típica — **Cuerpo 1–10 Hz**, **Superficiales 0.02–0.1 Hz**,
  **Regional 2–8 Hz**, **Off** — que fijan los cortes y reemiten. Además, al
  cambiar el filtro, la traza histórica YA cargada en Replay se **re-filtra al
  vuelo** (Replay guarda ahora los arrays CRUDOS y filtra en cada render), sin
  volver a descargar; el CSV exporta lo que se ve (filtrado/rotado).
- **Replay: rotación ZNE→ZRT (radial/transversal).** Botón conmutador que,
  cuando se entró desde un sismo del globo, rota las horizontales N/E a
  Radial/Transversal usando el **back-azimuth** (calculado de las coordenadas
  del evento + las de la estación vía StationXML). Separa P-SV (R) de SH (T)
  para un picking de S más limpio y análisis de ondas superficiales. Función
  de rotación pura ``measurements.rotate_ne_rt`` (con tests; convención ObsPy).
  El botón solo se habilita cuando hay back-azimuth disponible.
- **Etiquetas de canal según la banda real.** El eje izquierdo de las trazas
  ya no es "EH" fijo: refleja la banda real (``BHZ/BHN/BHE``, etc.) tanto en
  vivo como en Replay, y pasa a ``…Z/…R/…T`` al rotar. ``WaveformPanel`` gana
  ``set_channel_labels``.

### Changed
- **Reproducción histórica reescrita de "reproductor de vídeo" a NAVEGADOR
  ESTÁTICO** (paradigma SWARM / Snuffler / ObsPyck; ver
  `docs/replay-redesign.md`). Antes descargaba una ventana y la "reproducía" a
  N× con barra de progreso; ahora:
  - **Toda la traza se dibuja de una vez** y se navega con **zoom/pan** del
    ratón; eje X = **hora UTC absoluta**. Se **eliminaron** reproducir / pausar
    / detener / velocidad / barra de progreso.
  - Las herramientas de análisis (región / cursor / picks P-S / unidades /
    medidas) están **siempre activas** (ya no hace falta "congelar"); ⟲ ajusta
    a toda la traza.
  - **Selector de banda** (BH/HH/LH/EH/SH) junto a la estación de solo lectura.
  - **Entrada dirigida por evento**: clic en un sismo del globo → abre Replay
    con la estación seleccionada y la ventana alrededor del origen.
  - **Llegadas teóricas P/S (TauP, iasp91)** superpuestas tras la descarga
    cuando se entra desde un evento (usa coords de StationXML; defensivo).
  - **Exportar** PNG (imagen) / CSV (tiempo UTC + Z/N/E) / **QuakeML** (picks).
  - El `WaveformPanel` gana un `static_mode`; `ReplaySource` deja de usarse en
    la UI (se conserva el módulo y sus tests). Limpieza de claves i18n del
    reproductor.
- **Reproducción histórica: la estación ya NO se teclea, sigue a la
  selección.** Los 4 campos de texto editables (Red / Estación / Ubicación /
  Canal) se sustituyen por una etiqueta N.S.L.C. de SOLO LECTURA que refleja
  automáticamente la estación elegida en la barra lateral (p. ej. la barra
  mostraba ``IU.GUMO`` pero Replay descargaba ``IU.ANMO`` por defecto: ese
  desajuste desaparece). El canal vertical del preset (``BHZ``) se expande a
  banda completa (``BH?``) para traer las 3 componentes. ``ProWindow`` conecta
  ``ControlPanel.station_changed`` → ``ReplayPanel.set_station`` e inicializa
  con la estación actual. Se añadió el preset de duración **1 h** y se corrigió
  el recorte de "10 min"/"30 min" en la fila de presets. Se eliminaron 7 claves
  i18n muertas (``replay.field.{network,location,channel}`` y los 4
  ``replay.tooltip.*``); locales alineados (460 claves cada uno).
- **Añadir una estación con un stream activo ya NO cambia la conexión.**
  El diálogo de añadir prometía "se añade a la lista, pulsa Conectar para
  empezar", pero el código auto-seleccionaba la estación nueva en el combo,
  lo que (estando conectado) disparaba una reconexión inmediata y cortaba el
  stream en curso. Ahora, si hay una fuente activa, añadir una estación solo
  la agrega a la lista sin tocar la selección: el stream actual sigue intacto
  y el usuario se cambia a la nueva estación manualmente cuando quiera. Sin
  conexión activa, sigue auto-seleccionándose para que el próximo Conectar la
  use. (El ``WorkbenchController`` mantiene sincronizado el estado vía
  ``ControlPanel.set_source_active``.)

### Fixed
- **Replay: solo se veía la vertical (EHZ), sin las horizontales (N/E).**
  ``_stream_to_channels`` mapeaba el componente por la ÚLTIMA letra del canal
  y solo aceptaba Z/N/E. Las estaciones GSN/IU de banda ancha nombran las
  horizontales como **BH1/BH2** (no BHN/BHE), así que se descartaban y solo
  quedaba Z. Ahora se mapea ``1→N`` y ``2→E`` (igual que en SeedLink en vivo),
  recuperando las tres componentes en la revisión histórica.
- **Añadir una estación nueva mientras otra estaba en uso crasheaba la app.**
  Al añadir una estación (p. ej. desde el globo), el combo la seleccionaba
  automáticamente, lo que disparaba ``station_changed`` → reconexión
  (detener fuente vieja + arrancar la nueva). Esa reconexión destruía y
  recreaba un ``QThread``/socket de forma REENTRANTE dentro de la pila de
  señales del combo y, en el caso del globo, dentro del callback del puente
  QWebChannel + un ``QMessageBox`` modal — contexto en el que recrear hilos
  provoca un cierre inesperado. Ahora la reconexión por cambio de estación se
  DIFIERE a la siguiente iteración del bucle de eventos (``QTimer.singleShot``
  + coalescing al último preset pedido), ejecutándose sobre una pila limpia.
  Se cancela si el usuario pulsa Detener o cierra la app antes de que dispare.
- **Desconectar congelaba la UI y a veces crasheaba la app.** ``stop()`` de
  ``SeedLinkSource`` hacía ``thread.wait(8000)`` en el HILO DE LA UI (hasta
  8 s de congelación) y, si el hilo no moría, ``thread.terminate()`` — que
  puede CRASHEAR la app (el worker podía estar dentro de ObsPy con el GIL).
  Ahora el cierre es ASÍNCRONO: el ``socket.shutdown`` hace que ObsPy
  devuelva y el hilo termina solo en segundo plano; worker e hilo se liberan
  con el patrón estándar ``finished → deleteLater``. La UI no espera y NUNCA
  se usa terminate(). Además, para evitar un crash al pulsar Detener DURANTE
  la conexión (el worker sigue bloqueado en el pre-check unos segundos), la
  fuente se mantiene viva en un registro fuerte (``_closing``) hasta que su
  hilo termina de verdad — así ni el GC ni un emit diferido tocan un objeto a
  medio destruir. Se cortan TODAS las señales worker→source al detener.
- **Globo: el botón de rotación "no hacía nada" estando en zoom + tirones/
  crash.** En estado ZOOMED-IN, pulsar rotar solo guardaba la preferencia
  (parecía no responder); ahora, si el usuario quiere rotar, sale del zoom y
  empieza a girar. Además se ignoran los clics de rotación mientras hay una
  animación de cámara en curso, evitando encadenar setOption sobre ECharts-GL
  (causa de tirones / crash al pulsar durante el zoom).
- **SeedLink: oscilograma "a barras" y hodograma a saltos con estaciones
  IRIS broadband.** Dos causas, ambas por asumir el pipeline una Raspberry
  Shake (100 Hz, 3 componentes síncronas): (1) las componentes BHZ/BHN/BHE
  llegan en paquetes ASÍNCRONOS, y el empaquetado rellenaba con ceros las
  que no tenían datos en cada intervalo → picos a 0. Ahora se rellena con el
  ÚLTIMO valor real del canal ("hold DC"). (2) Los canales broadband son de
  20/40 Hz, pero se trataban como 100 Hz → eje temporal comprimido. Ahora la
  fuente remuestrea cada bloque a la tasa nominal del pipeline (`np.interp`).
  Helpers con tests (`tests/test_seedlink_resample.py`).
- **SeedLink: solo llegaba la componente vertical en estaciones de 3
  componentes (p. ej. IU.DAV).** (1) Se enviaban 3 SELECT separadas
  (BHZ/BHN/BHE) y algunos servidores solo atienden la primera → sin
  horizontales. Ahora se usa UNA SELECT con comodín de banda (`{loc}{banda}?`,
  p. ej. `00BH?`). (2) Muchas estaciones GSN nombran las horizontales
  BH1/BH2 en vez de BHN/BHE; `_on_trace` ahora mapea `1→N` y `2→E`. Juntos
  hacen que el hodograma reciba las horizontales de cualquier GSN/IRIS.
- **Workbench: el Hodograma se quedaba congelado en el origen con
  estaciones vertical-only.** Si la estación no tiene canales horizontales
  (N/E) — p. ej. un Raspberry Shake RS1D — la fuente rellena N/E con ceros,
  así que el "balín" se quedaba quieto en el centro sin explicación (aunque
  hubiera un terremoto real en el canal Z). Ahora, cuando no hay energía
  horizontal, el Hodograma muestra un aviso central ("sin canales
  horizontales (N/E) — necesita una estación de 3 componentes") en lugar de
  una trayectoria estática.
- **Workbench: el Hodograma (gráfico de partícula) no se mostraba.** Las
  curvas/cabeza del plot se creaban dentro de `_retranslate()`, que solo se
  llama al cambiar de idioma → tras construir el panel los atributos no
  existían y `update_from_snapshot` fallaba en silencio (no dibujaba nada
  hasta el primer cambio de idioma, que además duplicaba 60 curvas). Ahora
  los items se crean una vez en `__init__` (`_build_plot_items`) y
  `_retranslate` solo actualiza los textos.
- **Globo: la rotación se reanudaba al pulsar otros botones tras pausarla.**
  `applyVisualMode()` (disparado por el toggle de tema o Standard/Pro)
  reconstruía el globo con `autoRotate:true` hardcoded, pisando la pausa
  del usuario. Ahora respeta `userPausedRotation` / `zoomedIn`.
- **Dashboard «Línea temporal»: las fechas seguían en chino al cambiar
  idioma.** `formatLocalDateTime` usaba `Intl.DateTimeFormat(undefined,…)`,
  que resuelve al locale del SISTEMA, no al de la app. Ahora usa el código
  de idioma del payload (`lang`). Además el dashboard gana `setI18n()` y
  `DashboardPanel.push_i18n()` (suscrito a `language_changed`) para
  re-traducir y re-pintar al instante, sin esperar al próximo refresco
  (antes solo el globo tenía este camino).
- **(B2) El LED de estado de conexión no cambiaba de color al alternar
  tema.** `app_header._STATE_COLORS` cacheaba los `COLOR_*` al importar el
  módulo, violando la regla de "leer colores en runtime" (CLAUDE.md §4).
  Ahora el color se resuelve vía `theme as _t` en cada `set_connection_
  state()`, y `_refresh_themed_assets()` re-pinta el LED al cambiar tema.
- **(B1) Crash latente "Internal C++ object already deleted".** ~30
  suscripciones de widgets a señales de singletons de larga vida
  (`LocaleService` / `ThemeManager` / `LayerModeManager` / `FavoritesStore`
  / `ShakePresetStore` / `ActivityLog`) se conectaban sin desconectarse al
  destruir el widget — el mismo patrón que rompió 12 tests tras v0.7.6,
  presente en 21 widgets más allá del `LoadingOverlay` ya arreglado.

### Added
- **Replay: análisis sobre datos históricos.** El tab Replay ya reusaba el
  mismo `WaveformPanel`, así que congelar / cursor / región (pico/RMS/f₀) /
  pickers P-S funcionan también sobre el evento descargado — que es el caso
  de uso REAL del análisis (revisar un sismo pasado). Se añadió el cableado
  de **m/s** (obtiene el StationXML de la estación del formulario de Replay,
  en hilo de fondo) y se ocultan las herramientas del detector en vivo (cft,
  ⚡), que no aplican a datos históricos. `WaveformPanel` gana el parámetro
  `show_detector_tools`.
- **Workbench: modo análisis de un solo canal + unidades físicas, en una
  barra de herramientas sobre el oscilograma** (reestructuración UI patrón
  SWARM/Snuffler — las acciones viven junto a la traza, no en el panel
  lateral; ver docs/workbench-assessment y docs/seismic-software-survey).
  Barra: **Congelar · m/s · P · S · limpiar · reset zoom**.
  - **Congelar** — detiene el scroll para inspeccionar el búfer; **cursor en
    cruz** (tiempo/amplitud) y **región arrastrable** que mide en vivo
    **pico / RMS / frecuencia dominante** (`processing/measurements.py`).
  - **P / S** — pickers de fase arrastrables; el readout calcula
    **S-P → distancia → ML aproximada**.
  - **m/s** — quita la respuesta instrumental (velocidad del suelo). La
    sensibilidad se obtiene del StationXML del servicio FDSN de IRIS
    (`services/response.py`) en un hilo de fondo y se cachea; degrada a
    counts si no hay red/metadata.
  - Un único readout monoespaciado concentra cursor, región y picks.
  - Núcleos puros con tests: `tests/test_measurements.py` (7),
    `tests/test_response.py` (3).
  - La sección "Análisis" del panel lateral se eliminó (sus controles
    pasaron a la barra del oscilograma).
  - **Detector STA/LTA como entrada al análisis** (v0.7.7): la barra muestra
    el **cft en vivo** (rojo si ≥ umbral) para ajustar el umbral sin
    adivinar, y un botón **⚡ auto-análisis** que **congela la traza y marca
    el evento** en cuanto el cft supera el umbral (señal fuerte en pantalla)
    — responde al instante, no espera el "instante de disparo" exacto (que
    podía tardar hasta el próximo evento → parecía que ⚡ "no hacía nada").
    Convierte la detección en un evento listo para analizar. No intrusivo:
    apagado por defecto. Los rotores de umbral/STA/LTA del panel lateral
    siguen siendo la entrada de ajuste de este cft.
  - Fix latente: ``set_frozen`` iteraba los picks como líneas sueltas tras
    pasar a listas de 3 (multi-componente) — habría fallado al congelar con
    picks puestos.
  - **Análisis multi-componente**: los pickers P/S se dibujan ahora en las
    TRES trazas (Z/N/E) sincronizadas — S se sitúa mirando las horizontales,
    como en la práctica real; la medida de región reporta el pico del canal
    más energético (no solo Z); la ML usa el pico de las HORIZONTALES (def.
    clásica). Los pickers van por encima de la región para poder arrastrarse.
- **Workbench: panel de control reestructurado (secciones colapsables).**
  Conexión/estación quedan siempre visibles; **filtro / detector / sonido**
  son ahora secciones plegables (cabecera clicable con chevron), de modo que
  el panel deja de crecer sin límite al añadir funciones. **Sonido va plegado
  por defecto** (degradado: es una función de divulgación, no de análisis).
- **Workbench: visualización del progreso de conexión.** El ControlPanel
  muestra ahora un spinner + una línea de estado en vivo que refleja cada
  fase de la conexión SeedLink (DNS → TCP → handshake → SELECT → esperando
  paquete → recibiendo datos). El spinner gira mientras conecta, se detiene
  al llegar el primer paquete y se queda fijo en los errores. Antes estos
  mensajes solo iban a la barra de estado de la ventana principal,
  invisible desde el banco de trabajo.
- **i18n de los mensajes de estado SeedLink** (`source.seedlink.*` +
  `source.status.streaming`): ~16 mensajes que estaban hardcoded en español
  ahora se traducen a los 4 idiomas (449 claves/locale, alineadas y con
  placeholders idénticos).
- **`shakevision/ui/signal_safety.py`** — helper `subscribe(owner, signal,
  slot)` que generaliza el patrón de v0.7.6.1: envuelve el slot en
  `try/except RuntimeError`, adapta la aridad (como Qt: descarta args
  sobrantes) y desconecta automáticamente en `owner.destroyed`. Migrados
  los 21 widgets afectados (`app_header`, `control_panel`, `main_window`,
  `globe_view`, `dashboard_view`, `intensity_card`, los 4 paneles
  pyqtgraph, los diálogos `add_shake`/`github_login`/`profile`/`settings`,
  `onboarding_wizard`, `profile_view`, `pro_window`, `replay_panel`).
  `pg_theming` se deja como está (conexión de proceso, por diseño).
- `tests/test_signal_safety.py` — 5 tests (sin `QApplication`) que cubren
  introspección de aridad, truncado de args, guardia de `RuntimeError` y
  auto-desconexión en `destroyed`.

### Removed
- **(T1) 17 claves i18n muertas** sin llamadas (en Python, en el JS web ni
  en la suite de tests), supervivientes del prune de v0.7.6.1:
  `common.{ok,yes,no,close}`,
  `settings.status.{applied,language_changed,timezone_changed}`,
  `intensity.label.{mmi,pgv}`, `controls.sound.listen_playing`, varias
  `web.globe.controls.*` / `web.*.error.*`. Eliminadas de los 4 locales
  (450 → 433 claves cada uno; siguen alineados).
  NOTA: `common.cancel` y `profile.tab_title` **se conservaron** — aunque
  la app no los llama, la suite de tests (`test_i18n`, `test_profile_view`,
  `test_visual_polish_n`) los exige como contrato del locale.

### Changed
- **Workbench: velocidad de conexión.** ObsPy se pre-importa en un hilo
  daemon la primera vez que se abre el banco de trabajo, así la PRIMERA
  conexión SeedLink no paga el coste de importación (~1-2 s). (El timeout
  del pre-check TCP se mantiene en 5 s — un intento intermedio de bajarlo a
  3 s causaba timeouts espurios en servidores internacionales lentos.)
- **(B3)** Los 6 `except Exception: pass` de métricas/conexión en
  `main_window.py` ahora registran con `logger.debug(..., exc_info=True)`
  en vez de tragarse el error en silencio.
- `CLAUDE.md` §2: corregida la afirmación de que no quedaban claves i18n
  muertas tras v0.7.6.1 (ver T1).

### Internal
- Informe de auditoría completo en `docs/audit-0.7.7.md` (bugs, i18n,
  estructura) con severidad y orden de ejecución sugerido.
- **(S1) Extraído `WorkbenchController`** (`shakevision/ui/
  workbench_controller.py`, ~600 líneas): toda la canalización Workbench
  en tiempo real (fuente, búfer, DSP, detector STA/LTA, grabación,
  sonificación, espectrograma, timers de refresco/helicorder y la
  animación de alerta) salió del god-object `main_window.py`. El
  controlador es un `QObject` que **conduce** la `ProWindow` (su vista) y
  se comunica con el shell **solo por señales** (`status_message`,
  `latency_text`, `station_changed`, `connection_status_changed`), sin
  referenciar widgets del shell. Comportamiento preservado 1:1 (el estado
  de conexión, antes leído del texto del label, ahora es un flag interno).
  `main_window.py`: **1663 → 1105 líneas** (−558). Plan y diseño en
  `docs/refactor-plan.md`. ⚠️ Verificar con `pytest -q` (suite GUI) en
  máquina con Qt antes de publicar.
- `tests/test_workbench_controller.py` reescrito a tests de integración
  (config real + vista stub); se saltan limpiamente sin backend Qt.
- **(O3)** Unificado el `logger` de módulo en `main_window.py` (se quitan 2
  `import logging` + `logging.getLogger(__name__)` inline).
- **(O1)** De-duplicada la exportación de reporte: `_on_export_report`
  (HTML) y `_on_export_report_pdf` comparten ahora 4 helpers privados
  (`_station_label`, `_ensure_report_generator`, `_ask_report_save_path`,
  `_record_report_metric`). Comportamiento idéntico.
- **(O2)** Extraída la lógica de "periodos" (mapeo periodo→segundos +
  filtrado por ventana temporal) a `shakevision/utils/periods.py`
  (funciones puras, sin Qt), con `tests/test_periods.py` (6 tests).
- **Andamio** `shakevision/ui/workbench_controller.py` (`QObject` puro con
  la interfaz objetivo: señales `status_message` / `latency_changed` /
  `station_changed` / `connection_state` + `__init__(config, view)`) y
  `tests/test_workbench_controller.py` (4 tests, sin `QApplication`). Listo
  para recibir los métodos en 0.8.0.

---

## [0.7.6.1] — 2026-05-21

🩹 **Patch release** wrapping up the post-v0.7.6 fixes — loading overlay
i18n cleanup across the four data-source clients, onboarding wizard
initial-theme synchronization, the removal of the legacy `auto` theme
mode, and the CI hotfix for the dataselect test regex + LoadingOverlay
dead-widget guard.

### Removed
- **`auto` theme mode** — see v0.7.6 entry below. No user-visible
  regression: existing `auto` preferences migrate to `dark` on first
  launch under v0.7.6.1.

### Fixed
- **Onboarding wizard initial theme out of sync with MainWindow** —
  see v0.7.6 entry below for details.
- **Mixed-language error dialog (USGS / IRIS / ShakeNet / dataselect)**
  — see v0.7.6 entry below for details.

### Changed
- Version bumped 0.7.6 → 0.7.6.1 across `pyproject.toml`,
  `shakevision/__init__.py`, `packaging/shakevision.spec`,
  `packaging/windows/version_info.txt`.

### Internal
- `tests/test_dataselect.py::test_500_raises_dataselect_error` regex
  switched from Spanish literal `'contactar'` to language-agnostic
  `'dataselect'` so the i18n error message matches under any locale.
- `LoadingOverlay`: bound-method slot + `destroyed`-signal disconnect
  + defensive `try/except RuntimeError`, eliminating the
  "Internal C++ object already deleted" cascade that broke 12
  `test_report` tests in CI after v0.7.6.

---

## [0.7.6] — 2026-05-20

🍎 **Hotfix: macOS .dmg SSL CERTIFICATE_VERIFY_FAILED + loading overlay
i18n cleanup + ThemeManager simplification.**

### Removed
- **`auto` theme mode** — the `ThemeManager` previously had three modes
  (`auto`, `light`, `dark`), where `auto` flipped between light and
  dark based on the system clock (6:00–18:00 = light, otherwise dark).
  Removed in v0.7.6 because (a) it ignored the OS color-scheme
  preference (so it could disagree with macOS dark mode); (b) it was
  the root cause of the "MainWindow dark, onboarding wizard light"
  inconsistency reported on first-launch flows; (c) it added a global
  QTimer just to poll the hour. Users with `mode="auto"` saved in
  QSettings auto-migrate to `dark` on next launch (see
  `_load_persisted_mode`). The header theme button now cycles
  light↔dark only.

### Fixed
- **Onboarding wizard initial theme out of sync with MainWindow** —
  opening the app during daytime hours (auto+morning) would render
  MainWindow light, then the wizard would briefly appear light, then
  the theme page's "auto→dark" fallback would re-emit `theme_changed`,
  the app stylesheet would re-apply as dark, but the wizard's local
  stylesheet listener was connected *after* page construction and
  missed the first emit — leaving MainWindow dark while wizard stayed
  light. Three-layer fix in `onboarding_wizard.py`:
    * Pre-select the radio using `ThemeManager.current_theme()` (always
      `light`/`dark`) instead of `mode()` (could be `auto`).
    * `blockSignals(True)` around the init-time `setChecked` so the
      `toggled`-driven `set_mode` side effect never runs during
      construction.
    * Move `ThemeManager.changed_signal().connect()` to BEFORE page
      construction, plus a final defensive `setStyleSheet()` at the
      end of `__init__`.
- **Mixed-language error dialog** — when a network call to USGS / IRIS
  / ShakeNet / IRIS dataselect failed, the loading overlay rendered a
  Frankenstein of three languages on a single screen: an English
  title from the caller's i18n key, the Spanish button text
  `"Reintentar"` (hardcoded in `LoadingOverlay`), and the Spanish
  exception message `"no se pudo contactar a ..."` (hardcoded in the
  four service clients) — regardless of the user's selected language.
  Two root causes:
    * `shakevision/ui/loading_overlay.py` had three Spanish
      hardcodings (`"Cargando…"` x2 + `"Reintentar"` button) that
      bypassed the i18n layer entirely. Replaced with `t(...)` calls
      and wired the widget to `LocaleService.language_changed_signal`
      so live language switches in Ajustes refresh the button text.
    * `shakevision/services/{usgs,iris,shakenet,dataselect}.py` each
      raised their `*Error` exceptions with f-string Spanish literals.
      Replaced all four with `t("error.<service>.contact", error=...)`
      keys.
  Added eight new i18n keys (`overlay.loading`, `overlay.btn_retry`,
  `overlay.retrying`, `overlay.retrying_subtitle`,
  `error.{iris,usgs,shakenet,dataselect}.contact`) translated across
  all four locales (EN / ES / FR / ZH).
- **All HTTPS calls failed in macOS .dmg builds** — USGS feed, IRIS
  stations, ShakeNet, GitHub OAuth, IP geolocation, FDSN dataselect
  ALL died on launch with:
  ```
  ssl.SSLCertVerificationError:
  [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
  self-signed certificate in certificate chain (_ssl.c:1006)
  ```
  Root cause: stock macOS Python doesn't read the system keychain for
  HTTPS CA validation (unlike Linux which has `/etc/ssl/certs/` and
  Windows which falls back to wincrypt). PyInstaller `--windowed`
  bundles ship without any CA chain, so every `urlopen()` to https://
  hit the empty trust store and rejected legitimate certs as
  "self-signed". Windows .exe + Linux AppImage builds were unaffected
  for the platform reasons above.
- Three-part fix:
    * `shakevision/__main__.py` — at startup (immediately after
      `faulthandler` setup, before any service imports), point
      Python's default HTTPS context at `certifi.where()` and set
      `$SSL_CERT_FILE` / `$REQUESTS_CA_BUNDLE` env vars. Runtime
      patch covers stdlib `urllib`, `requests`, `urllib3`, `httpx`.
    * `pyproject.toml` — added explicit `certifi>=2023.7.22`
      dependency. Previously transitive via obspy/requests, now
      explicit so the PyInstaller spec can rely on it being present.
    * `packaging/shakevision.spec` — added
      `datas += collect_data_files("certifi")` so the CA bundle PEM
      file actually ships inside the .app bundle. Also added
      `"certifi"` to `hiddenimports` so PyInstaller's static analysis
      doesn't miss it (we import it from `__main__.py` at runtime).

### Changed
- Version bumped 0.7.5 → 0.7.6 across `pyproject.toml`,
  `shakevision/__init__.py`, `packaging/shakevision.spec`,
  `packaging/windows/version_info.txt`.

---

## [0.7.5] — 2026-05-19

🔌 **One-click GitHub sign-in + Workbench rename polish + Onboarding /
Settings dropdown fixes.** Follow-up patch release that wraps up the
loose ends from v0.7.4: the residual "Pro" copy after the Workbench
rename, the clipped Localizame screen on Windows, missing Reset-tab
labels, and the timezone dropdown losing its arrow indicator under
the heavy QSS override. Plus, the GitHub Connect button is finally
fully functional out of the box.

### Fixed
- **GitHub Connect button was a dead click** — pressing
  `Connect with GitHub` from the Profile dialog could appear to do
  nothing. Root cause: when `start_device_flow()` raised
  `NotConfiguredError` or a network error, the dialog called
  `setText` on `_wait_status`, which lives on the **WAITING** page —
  but the user was still on the **INTRO** page, so the error was
  written to a hidden label. Added a visible `_intro_status` error
  label on the INTRO page and routed all start-time errors there.
- **GitHub login required two clicks to reach the browser** —
  previously the flow was *Connect → see code → click "Open GitHub"
  → browser opens*. Now `QDesktopServices.openUrl(verification_uri)`
  fires automatically right after `start_device_flow()` succeeds, so
  the user lands on `github.com/login/device` in a single click. The
  "Open GitHub" button on the WAITING page is kept as a fallback for
  headless environments where the open fails.
- **Timezone combo arrow vanished on Windows (Onboarding + Settings)**
  — Qt's `QComboBox` heavy QSS override caused the `::down-arrow`
  indicator image to fail to resolve on Windows, leaving the combo
  with zero visual affordance to open its popup. Replaced the image
  with a border-triangle trick (`border-top: 6px solid; border-left/
  right: 5px solid transparent`) in both `onboarding_wizard.py`
  (`#WizardCombo`) and global `theme.py` (all `QComboBox`). No
  external asset needed, works on all three platforms.
- **Settings → Reset tab labels were blank** — the
  `_retranslate_shakes_tab` cascade (which also paints the Reset
  widgets after the v0.7.4 redesign) was invoked once at the end of
  `_build_my_shakes_tab`, BEFORE `_build_reset_tab` ran. So
  `hasattr(self, "_reset_heading")` was always False at that point
  and the Reset texts were never applied. Added a second explicit
  `_retranslate_shakes_tab()` call after `_build_reset_tab()` so the
  Reset widgets exist when text is set.
- **Localizame screen clipped on Windows** — at SCREEN 560 × 400 the
  layout had the heading sitting at y = 384–404 right at the bottom
  edge, and the detected-zone line at y = 410–436 was completely cut
  off. Bumped canvas to 600 × 480 and reduced halo radius 180 → 150,
  giving 26 px of bottom margin. macOS/Linux were less affected only
  because of subtle DPI scaling differences.
- **Residual "Pro" copy after the Workbench rename** — 5 i18n keys
  still surfaced the old "Pro" branding to users
  (`menu.view.show_pro` → "Show Pro", `header.action.pro_tooltip`,
  `settings.my_shakes.help`, `status.station_added` toast,
  `dialog.usgs.body` prompt). Rewrote all five across all four
  locales — now reads "Workbench" / "工作台" / "Banco" / "atelier".
  Grep on the value side of every locale now returns zero standalone
  "Pro" hits.

### Added
- **`DEFAULT_CLIENT_ID` baked into `github_auth.py`** — registered
  the public OAuth App "SeismicGuard-shakevision"
  (`Ov23liBIJOgeeGVfFW9B`) with Device Flow enabled and shipped its
  Client ID in code. End users no longer need to register their own
  OAuth App or set `$SEISMICGUARD_GITHUB_CLIENT_ID` — the Connect
  button works out of the box. Priority chain remains
  `env > QSettings > DEFAULT_CLIENT_ID > ""` so power users can
  still override.
- **`QLabel#DialogError` QSS** — subtle red inline-error styling
  (`color: alert; font-size: label`) for any future dialog that
  wants inline feedback instead of opening another modal.
- **GitHub login dialog: "Don't have a client ID?" hint** — links
  out to `https://github.com/settings/applications/new` so power
  users who *do* want their own OAuth App have a one-click path to
  register one. Localised in all four languages.
- **Client ID field always visible** — previously the field was
  hidden once a `client_id` was configured, leaving users with no
  way to update or replace a stale one. Now it's always shown,
  pre-populated with the current value.

### Changed
- Version bumped 0.7.4 → 0.7.5 in `pyproject.toml`,
  `shakevision/__init__.py`, and `packaging/shakevision.spec`.
- `packaging/windows/version_info.txt` modernised — was still at
  `0.3.0` from the original Windows-build commit and still branded
  "ShakeVision Contributors / ShakeVision OpenData Monitor". Now
  reads `0.7.5.0` with the SeismicGuard branding, so Windows' file
  properties dialog matches the actual product.
- i18n: 1 new key × 4 locales (`github.login.client_id_help`) —
  total **444 keys × 4 locales**, parity preserved.

---

## [0.7.4] — 2026-05-19

🪟 **Windows polish + Onboarding UX + Profile extensions** — batch
fix for 7 user-reported issues on the Windows .exe build.

### Fixed
- **Onboarding timezone combo bug (#2)** — entering the timezone page
  programmatically opened the `QComboBox` popup, but in macOS it left
  the combo in a state where subsequent clicks would NOT reopen the
  popup. Removed the auto-popup; the page enters with focus on the
  combo and the placeholder shows the detected zone, which is enough
  affordance.
- **Onboarding light theme unreadable (#3)** — the wizard's QSS was
  hardcoded to a dark navy palette. Switching to light theme left
  text invisible. QSS now reads from `shakevision.ui.theme.COLOR_*`
  and subscribes to `ThemeManager.changed_signal` for live updates.
- **Onboarding theme step had non-functional "Auto" option (#4)** —
  the `auto` radio was a no-op in practice (`ThemeManager` only honors
  light/dark). Removed; users now choose light or dark only.
- **Windows dialog generic icons (#6)** — `Settings`, `Profile`,
  `Workbench` and other secondary windows showed Windows' default
  Python icon next to them in the taskbar. Added a single
  `app.setWindowIcon(QIcon(branding/app_icon.png))` after
  QApplication construction — propagates to all top-level windows on
  Windows. macOS/Linux were unaffected and remain so (no-op there).

### Added
- **Settings → Reset tab redesigned (#5)** — replaced the lone red
  button with a warning card: ⚠ icon + heading + body + a 6-item grid
  showing what will be cleared (Preferences, Favorites, LAN Shakes,
  Usage stats, Activity log, Disk cache), and a footer showing the
  current disk cache size in MB. The destructive button sits outside
  the card for visual separation.
- **Profile dialog now shows extended GitHub info (#7)** — after
  login, the identity card surfaces bio + location/company + counts
  (`📦 N repos · 👥 N followers · → N following`). All sourced from
  the public `/user` API endpoint with `read:user` scope (no
  additional permissions). `GitHubAuthService.fetch_user_profile`
  extended to return bio, company, blog, location, created_at,
  public_repos, followers, following, public_gists.

### Known issues (documented, not code-fixable)
- **Windows timezone/region detection accuracy (#1)** — Windows groups
  Madrid + Paris + Brussels + Copenhagen into one "Romance Standard
  Time" registry entry; `tzlocal` maps it to the IANA canonical
  `Europe/Paris`, so a Madrid user sees Paris. Similarly IP-based
  geolocation routes through ISP POPs (a Valencia user is detected
  as Madrid). Both are OS / network limitations, not bugs in our
  code. The Settings dialog already lets the user override manually;
  added clearer hint text encouraging verification.

### Changed
- Version bumped 0.7.3 → 0.7.4 in `pyproject.toml`,
  `shakevision/__init__.py`, and `packaging/shakevision.spec`.
- i18n: 8 new keys × 4 locales (settings.reset.cache_size, 6 reset
  item labels, profile.github.counts) — total 443 keys × 4 locales.

---

## [0.7.3] — 2026-05-19

🌍 **Hotfix: Windows globe textures + country borders missing.**

### Fixed
- **Windows .exe globe was unusable**: night mode rendered as a plain
  blue sphere, day mode fell back to the night texture, professional
  mode had no country borders and no labels. macOS dev runs were fine
  because the developer had run `download_globe_assets.py` locally
  long ago — that script's outputs (Blue Marble `earth-day.jpg`,
  Natural Earth `world.json`) live in `shakevision/web/globe/lib/`
  which is `.gitignore`d, so CI never had them.
- `scripts/install_libs.sh` only downloaded ECharts, `earth-night.jpg`
  and `earth-topology.png`. It missed:
    * **`earth-day.jpg`** — NASA Blue Marble. Used as the day base
      texture AND as the night-mode base (with `earth-night.jpg`
      overlaid as an emission layer, NASA Worldview style).
    * **`world.json`** — Natural Earth 1:110M GeoJSON. Drives country
      borders + country labels in the holographic professional mode.
- `install_libs.sh` now chains into
  `scripts/download_globe_assets.py` after the JS libs, so CI grabs
  all three texture/border assets from NASA/Natural Earth mirrors
  with automatic fallback and size/header validation. If `python3`
  isn't on PATH (very unlikely in CI), it falls back to the old
  single-mirror `earth-night.jpg` download so the build doesn't break.

### Changed
- Version bumped 0.7.2 → 0.7.3 in `pyproject.toml`,
  `shakevision/__init__.py`, and `packaging/shakevision.spec`.

---

## [0.7.2] — 2026-05-18

🪟 **Hotfix: Windows .exe crash on launch.**

### Fixed
- **PyInstaller `--windowed` startup crash on Windows** (regression
  reported in v0.7.1):
  ```
  Traceback (most recent call last):
    File "__main__.py", line 27, in <module>
  RuntimeError: sys.stderr is None
  ```
  When PyInstaller builds a GUI app without a console window
  (`--windowed` / `--noconsole`), Python's `sys.stdout` and
  `sys.stderr` are both `None`. Two places relied on them and crashed
  before the splash could appear:
    * `__main__.py` — `faulthandler.enable()` (no args) tries to dump
      to `sys.stderr`.
    * `utils/logging.py:setup_logging()` — `StreamHandler(stream=
      sys.stdout)` raises on the first log line.
- Fix in `__main__.py`: if `sys.stderr is None`, route faulthandler
  output to `%TEMP%/seismicguard_faulthandler.log` instead. File
  handle kept alive on `sys` to survive GC.
- Fix in `utils/logging.py`: new `_make_stream_handler()` chooses
  `sys.stdout` → `sys.stderr` → `FileHandler(%TEMP%/seismicguard.log)`
  → `NullHandler` as a robust cascade. The log file path is consistent
  across runs so users can find it for bug reports.

### Changed
- Version bumped 0.7.1 → 0.7.2 in `pyproject.toml`,
  `shakevision/__init__.py`, and `packaging/shakevision.spec`.

---

## [0.7.1] — 2026-05-18

🎨 **New app icon** — cracked-earth SeismicGuard mark on deep navy.

### Added
- New app icon (`packaging/macos/icon.icns`, `packaging/windows/icon.ico`,
  `packaging/linux/icon.png`) with deep-navy rounded-square background,
  yellow cracked-earth glyph, and "SeismicGuard" wordmark below.
- `shakevision/assets/branding/app_icon.png` + `app_icon_512.png` bundled
  for in-app use (About dialog, splash fallback, etc.).
- ICO is multi-resolution (16/32/48/64/128/256); ICNS contains the
  standard macOS variant set; Linux PNG is 1024×1024 for AppImage and
  `.desktop` entries.

### Changed
- `packaging/shakevision.spec` BUNDLE bumped from `0.3.0` → `0.7.1`
  (CFBundleShortVersionString + CFBundleVersion also updated from the
  stale `0.1.1` placeholder).
- Version bumped 0.7.0 → 0.7.1 in `pyproject.toml` and
  `shakevision/__init__.py`.

---

## [0.7.0] — 2026-05-18

🎨 **Major redesign release** — rebrand, theming, internationalisation,
onboarding, profile, location services, PDF polish.

### Rebrand
- Renamed app from **ShakeVision** to **SeismicGuard** everywhere
  user-visible (window title, splash, About, status messages, reports).
  Python package stays `shakevision` for backwards-compat with installs.

### Theming
- New `ThemeManager` + `LayerModeManager` singletons (themes
  independent of pro/standard layer modes).
- macOS-Sonoma / ChromeOS Material-3 palette overhaul: system-blue
  accent `#0a84ff`, iOS-style hairlines, pill buttons, capsule tabs,
  custom tooltips, drop shadows.
- Light theme reworked from scratch: dashboard cards, workbench
  panels, intensity card, profile dialog all use dynamic CSS variables.
- `ui/animations.py` + `ui/elevation.py` + `ui/pg_theming.py` helpers
  for hover/press micro-animations, Material elevation shadows, and
  theme-aware pyqtgraph plots.
- AppHeader logo with real-time theme awareness (PNG swap on switch).
- Globe view always uses dark background regardless of Qt theme.

### Internationalisation
- Full i18n infrastructure (`LocaleService`, `t()` helper).
- 435 keys × 4 locales (English, Spanish, Chinese, French) at 100 %
  parity, covering UI, status messages, web views (globe + dashboard
  ECharts), report templates.

### Onboarding
- Splash screen with progress bar.
- `Localízame` welcome transition with halo animation, system
  timezone detection (no network).
- 6-step onboarding wizard (welcome / language / timezone / theme /
  layer mode / done) with live re-translation as the user picks
  language.
- Auto-popup timezone dropdown for macOS QComboBox.

### Profile dialog (📊)
- AppHeader 👤 entry point opens a modal `ProfileDialog` with:
  - Identity card with GitHub avatar (OAuth Device Flow, no secret).
  - 6 usage stat cards (launches, time in app, earthquakes viewed,
    stations clicked, audio played, reports generated).
  - **Recent activity timeline** (last 50 events with relative time,
    stored locally in QSettings via `ActivityLog`).
- `UsageTracker` records aggregates; `ActivityLog` records events.

### Region & time (Settings → General)
- Timezone dropdown with all IANA zones + "Detect from system" button.
- **Auto-detect location** button: one-click IP-based geolocation via
  ip-api.com (no key, HTTP, 5 s timeout). Address can be detected
  automatically or typed manually. Privacy-first — never called in
  background.

### Globe (3D Earth)
- Three visual modes:
  - **Day**: NASA Blue Marble texture, realistic shading.
  - **Night**: Blue Marble darkened + Black Marble city lights as
    emission layer (industry-standard NASA Worldview approach;
    final iteration of 4 attempts).
  - **Holographic**: country borders + multi-language labels
    (≤ 100 countries, Taiwan blocklisted), reactive to language.
- Auto-recovery from WebGL context loss with ResizeObserver +
  `safeSetOption` wrapper.
- `download_globe_assets.py` script with mirror fallback for optional
  texture files.

### Reports & PDF export
- `report.html` template fully internationalised.
- **PDF export overflow fixed**: `@page A4 + 18 mm margins`, table
  columns now wrap (`table-layout: fixed; word-break: break-word`),
  KPI grid switches from 4 → 2 columns in print, header repeated on
  each page, white print background.
- QWebEngineView sized 794 × 1123 px (A4 96 dpi) to minimise
  Chromium scaling glitches.

### Settings
- Reset tab replaces the old Backup tab: one-click "Clear cache and
  restart" wipes all `QSettings` (10 apps) + `~/.cache/shakevision/`
  with a hard confirmation dialog → `QApplication.quit()`. Next
  launch re-runs the onboarding wizard.

### Removed / postponed
- Right-click favourite-earthquake from the globe (7 implementation
  iterations couldn't make echarts-gl's `scatter3D` raycaster
  cooperate reliably; the underlying `FavoritesStore` and Profile
  dialog plumbing remains for a future button-based UX).

### Fixed
- Profile dialog dark-mode rendering: cards were white over dark
  background because QSS read theme colours at construction time
  only — now re-applied on `ThemeManager.changed_signal`.
- Black rectangles inside Profile cards: explicit
  `background: transparent` on all child QLabels.
- All click feedback (station click, add-to-workstation) broken by a
  short-lived `rebuildChart()` call in `ResizeObserver` — reverted to
  `chart.resize()` only.
- Recoverable WebGL `getRoots` errors no longer surface in the
  user-facing error overlay (whitelist + `safeSetOption`).

### Added (services)
- `services/activity_log.py` — 14-kind enum + 50-entry ring buffer.
- `services/location_service.py` — async IP geolocation.
- `services/clear_cache.py` — orchestrated QSettings + disk-cache wipe.
- `services/github_auth.py` — GitHub Device Flow.

---

## [0.3.0] — 2025-05-18

🛰 **Custom LAN Raspberry Shake support.**

### Added
- **AddShakeDialog** (`ui/add_shake_dialog.py`) — modal para registrar
  un Raspberry Shake propio en la red local: campo IP/hostname,
  código de estación, puerto y etiqueta. Botón "Test connection"
  hace pre-check TCP de 5 s en hilo aparte y pinta resultado verde/
  rojo, sin bloquear la UI.
- **ShakePresetStore** (`services/shake_presets.py`) — singleton
  persistente que guarda los Shakes LAN del usuario en QSettings
  (`shakes/lan_presets`, JSON). API simple (`all/add/delete/rename/
  find_by_host`) + señal `presets_changed` para que cualquier vista
  se refresque sin polling.
- **Entrada "➕ Add LAN Shake…" en el desplegable** de estaciones
  del ControlPanel. Al seleccionarla se abre AddShakeDialog y, si
  acepta, el preset queda añadido + persistido + auto-seleccionado.
- **Nueva pestaña "My Shakes"** en el diálogo Settings con CRUD
  completo (Add / Rename / Delete + doble-click para editar). Lista
  vacía muestra un placeholder amigable.
- 60+ claves i18n nuevas (EN / ES / ZH / FR) para todo el flujo de
  Shake LAN, incluyendo mensajes de error TCP/DNS específicos.
- Tests: `test_shake_presets.py` (CRUD + round-trip QSettings + 9
  casos), `test_add_shake_dialog.py` (validación campo a campo).

### Changed
- ControlPanel ahora se suscribe a `ShakePresetStore.changed_signal()`
  para reflejar cambios externos (otra ventana, Settings) en vivo.

---

## [0.2.0] — 2025-05-18

⏯ **Historical replay from IRIS dataselect.**

### Added
- **DataselectClient** (`services/dataselect.py`) — cliente síncrono
  del servicio FDSN dataselect/1 de IRIS para descargar MiniSEED de
  cualquier intervalo histórico. Cacheado en disco (TTL 30 días por
  ser datos inmutables), soporta `force_refresh`, distingue 204/404
  como `NoDataAvailable` (caso esperado, no error). Sin Qt → 100%
  testeable.
- **ReplaySource** (`sources/replay.py`) — implementa `DataSource`
  reproduciendo un `obspy.Stream` con velocidades 0.5× / 1× / 2× /
  5× / 10× / 30× / 60×. Reloj puro (`_ReplayClock`) separable y
  testeable. API: `start / stop / pause / resume / seek / set_speed`.
  Emite `progress(cursor_s, duration_s)` para barras de progreso y
  `finished` al terminar.
- **Pro tab "⏯ Replay"** (`ui/replay_panel.py`) — formulario con
  N.S.L.C. + datetime UTC + duración + selector de velocidad +
  botones Download / Play / Pause / Stop + barra de progreso
  arrastrable. Buffer/processor/spectrum independientes del Live
  tab → ambos pueden estar activos simultáneamente. Descarga en
  hilo separado con loading overlay; errores friendly (sin datos,
  IRIS caído, timeout).
- 18 claves i18n nuevas (EN / ES / ZH / FR) para todo el flujo de
  replay.
- Tests: `test_dataselect.py` (mock urllib: URL FDSN bien formada,
  caching, 204/404 → NoDataAvailable, fallback a caché obsoleta),
  `test_replay.py` (núcleo `_ReplayClock` + ReplaySource con
  obspy.Stream sintético).

### Changed
- `shakevision.sources.__init__` exporta `ReplaySource` además de
  los anteriores.

---

## [0.1.1] — 2025-05-18

📦 **Binary installers release.**

### Added
- **Pre-built binaries for Windows, macOS (Apple Silicon) and Linux.**
  - Windows: `.zip` (portable, descomprime y ejecuta `ShakeVision.exe`)
  - macOS arm64: `.dmg` con `.app` notarizable (arrastra a /Applications).
    Intel Mac no se distribuye en binario — los usuarios M1+ ya son
    mayoría desde 2020; los de Intel pueden ejecutar desde fuente.
  - Linux: `.AppImage` autoejecutable (`chmod +x` y doble-click)
- Pipeline de empaquetado reproducible (`packaging/build.py` + `shakevision.spec`)
  basado en PyInstaller **onedir** (rápido al arrancar, AV-friendly).
- Workflow `release.yml` que se dispara con cualquier tag `vX.Y.Z`,
  construye los tres binarios en paralelo y publica la GitHub Release
  con notas extraídas automáticamente de este CHANGELOG y tabla de
  SHA-256 checksums.

### Fixed
- **Windows**: `tzdata` añadido como dependencia condicional
  (`sys_platform == 'win32'`) — sin él `zoneinfo` rechazaba incluso
  `ZoneInfo("UTC")` por falta de base IANA en el SO.
- **Windows · auto-detección de zona horaria**: nueva dependencia
  `tzlocal` que traduce el nombre del registro de Windows ("China
  Standard Time", "Pacific Standard Time"…) al estándar IANA
  ("Asia/Shanghai", "America/Los_Angeles"). Antes la app caía a UTC
  en arranques limpios de Windows; ahora detecta correctamente la
  zona del SO.
- **Windows · SmartScreen "Unrecognized app"**: añadido
  `VS_VERSIONINFO` (CompanyName, ProductName, FileDescription,
  versión…) al `.exe`. No elimina el warning (eso requiere firma EV,
  en la roadmap v1.0), pero reduce la fricción y mejora la
  legitimidad percibida del binario.
- **Globe · auto-recuperación de WebGL en Windows**: tras
  minimizar/restaurar la ventana o reiniciar el proceso GPU de
  Chromium, ECharts dejaba de pintarse con `Cannot read properties
  of null (reading 'getRoots')`. Ahora el JS detecta el
  `webglcontextlost`, reconstruye el chart y reaplica el estado.
  Triple defensa: evento WebGL + wrapper `safeSetOption` + heartbeat
  cada 10 s.
- **timezone_service**: tercer nivel de fallback a `datetime.timezone.utc`
  para que `format_local` / `to_iso_local` nunca lancen excepción
  aunque la base IANA esté rota o desinstalada.
- **FileCache.age_seconds()**: clamp a `≥ 0` para tolerar el desfase
  de nanosegundos entre `time.time()` y `st_mtime` de NTFS en Windows.

### CI / tests
- Alineados 14 tests obsoletos con el comportamiento actual del código
  (i18n por defecto en EN, swap del motor 3D a ECharts-GL, redesign
  del dashboard, sosfiltfilt edge ringing, etc.).
- Ruff sin errores en toda la base.

---

## [0.1.0] — 2025-05-15

🎉 **First public release.**

### Added

#### 🌍 3D Globe (default view)
- ECharts-GL real-time 3D Earth with night-side texture and atmosphere
- ~1500 Raspberry Shake stations (deep green) + ~400 USGS / IRIS stations (mint-green halo)
- Live earthquake markers from USGS GeoJSON feed, color-coded by magnitude (5 buckets: Micro / Light / Moderate / Strong / Major)
- Period selector: 1 h / 24 h / 7 d / 30 d
- Camera controls: zoom in/out, auto-rotate pause, reset view, click-to-zoom country-scale
- Click a USGS station → confirmation dialog → adds to Pro workbench (FIFO max 8 dynamic stations)
- Click a Raspberry Shake station → info-only popup (public SeedLink not available for AM network)

#### 📊 Data Dashboard
- 7 linked ECharts: Top 10 countries (M ≥ 3.0 filter), magnitude/depth histograms, timeline (adaptive density bubbles for >24 h windows), PAGER radar with **region dropdown filter**, period-adaptive distribution buckets, depth × magnitude scatter
- Global period selector (1 h / 6 h / 24 h / 7 d / 30 d) drives ALL charts
- Timezone-aware timestamps via `Intl.DateTimeFormat`
- Station summary KPI (Shake/USGS counts)
- Loading + error overlays with retry

#### 🔬 Pro Workbench (floating window)
- Opened via 🔬 Pro button in AppHeader (or `Ctrl+P` / `Cmd+P`)
- Independent `QMainWindow` — geometry persisted via QSettings
- Sub-tabs: 📡 Live (waveform + spectrogram) / 📜 24h Diary (helicorder) / 🌀 Hodogram (N-E particle motion)
- Control panel: station selector with dynamic add, Butterworth bandpass filter, STA/LTA trigger, sonification slider
- MMI intensity card translating PGV → live intensity badge (12 MMI levels, color-coded)
- Event recorder: STA/LTA trigger → MiniSEED auto-save with pre/post-event window

#### 📡 SeedLink connectivity
- Smart network-to-server routing: IU/US/II/IC → `rtserve.iris.washington.edu:18000`; AM → `rs.local:18000`
- 5-second TCP pre-check with explicit timeout (DNS / firewall / unreachable diagnosis)
- 8-stage progress reporting: DNS → TCP → handshake → SELECTs → first packet → streaming
- Network-aware channels (BHZ/BHN/BHE for IRIS broadband; EHZ/EHN/EHE for Shake)
- **Cancel-at-any-time**: socket shutdown + thread terminate fallback, never crashes the UI

#### 🌐 Internationalization
- Full 4-language support: English (default) / Español / 简体中文 / Français
- **260 translation keys** covering: menus, dialogs, status messages, chart axes/legends/tooltips, MMI levels with descriptions, HTML reports
- Per-locale JSON files, hot-swappable without restart
- Static HTML labels marked with `data-i18n` + JS auto-replacement
- Pythonic `t(key, **vars)` API with `{var}` format string interpolation
- Persistent via QSettings

#### 🕒 Timezone-aware
- Auto-detect system timezone (POSIX `/etc/localtime` symlink → `TZ` env var → `datetime.astimezone()`)
- Manual override via Settings dialog (~600 IANA timezones)
- ALL timestamps display in user's chosen TZ across dashboard, globe, reports, status bar
- No network/IP lookups — privacy-first

#### 📄 Reports
- One-click HTML report export with embedded SVG sparkline and CSS
- PDF export via `QWebEngineView.printToPdf` (no extra dependencies)
- Full i18n: section titles, KPI cards, table headers, event list — all translated

#### 🔊 Sonification
- "Listen to last 60 s" of seismic data, accelerated 1×–60×
- QAudioSink playback with proper state machine (handles macOS Idle/Active timing quirks)
- Stop button safely interrupts mid-playback

#### ⚙ Settings
- Language picker (4 languages with auto-glonyms)
- Timezone editable combo box + "Detect from system" button
- Custom location free-text field (optional, appears on reports)

### Infrastructure
- GitHub Actions CI: Ubuntu / macOS / Windows × Python 3.10 / 3.11 / 3.12 matrix
- Ruff linting + pytest test suite (30+ test modules)
- One-shot resource downloaders: `scripts/install_libs.sh` (ECharts/ECharts-GL ~4 MB) + `scripts/install_fonts.sh` (Inter + JetBrains Mono ~6 MB)

### Known limitations
- Only source distribution in v0.1.0; binary installers (`.exe` / `.dmg` / `.AppImage`) coming in v0.1.1
- Raspberry Shake public SeedLink server does NOT exist — only LAN connection to own device works for AM network
- Globe click "snap to point" centering not yet supported (ECharts-GL `beta` mapping needs per-version calibration); zoom-only works
- Historical replay deferred to v0.2.0

---

## Releases

- **0.3.0** — 2025-05-18 — Custom LAN Raspberry Shake support
- **0.2.0** — 2025-05-18 — Historical replay from IRIS dataselect
- **0.1.1** — 2025-05-18 — Binary installers (Win / mac / Linux)
- **0.1.0** — 2025-05-15 — First public release

See [GitHub Releases](https://github.com/yiaogit/seismic-shakevision/releases) for downloadable artifacts.
