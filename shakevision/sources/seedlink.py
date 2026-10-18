"""
Cliente SeedLink real basado en ObsPy.

⚠ Nota crítica sobre el ecosistema Raspberry Shake
-------------------------------------------------
``data.raspberryshake.org:18000`` **NO es un servidor SeedLink público**.
La empresa Raspberry Shake ofrece datos en tiempo real solo de tres
formas (verificado en sus foros oficiales):

  1. **Local / LAN** — el puerto 18000 vive en CADA dispositivo Shake,
     accesible en la red local mediante ``rs.local:18000`` o la IP del
     dispositivo. Esta es la única vía gratuita y verdaderamente en
     tiempo real, pero requiere que el usuario tenga un Shake propio.
  2. **CAPS público** ``data.raspberryshake.org:16022`` con retraso de
     ~30 minutos. Protocolo gempa CAPS, sin soporte en ObsPy.
  3. **Servicio comercial** — RTDC (Real-Time Data Center) facturado.
     Raspberry Shake empuja datos a un servidor SeedLink/CAPS que
     opera el cliente.

Por lo tanto este módulo soporta el **modo LAN** (caso 1). El usuario
debe especificar la dirección de su Shake. Si no tiene Shake propio,
hay un modo "Replay" en ``sources/file.py`` (futuro) que descarga
trazas históricas vía FDSN dataselect.

Referencia: https://community.raspberryshake.org/t/seedlink-server-ip-adress/3891
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from shakevision.i18n import t
from shakevision.sources.base import DataSource, SampleBatch


# Canales por defecto: vertical, norte, este (instrumento de banda corta)
DEFAULT_CHANNELS: tuple[str, str, str] = ("EHZ", "EHN", "EHE")

# Periodo del temporizador que empaqueta y emite SampleBatch (ms)
EMIT_INTERVAL_MS: int = 100

# Timeout del pre-check TCP. NO bajar de 5 s: aunque una conexión LAN sana
# responde en decenas de ms, los servidores SeedLink internacionales
# (p. ej. rtserve.iris.edu desde Asia) pueden tardar 3-5 s solo en el
# DNS+TCP. v0.7.7 lo bajó a 3 s "para fallar más rápido" y provocó timeouts
# espurios en conexiones reales pero lentas → revertido a 5 s.
TCP_PRECHECK_TIMEOUT_S: float = 5.0

# Timeout (s) del handshake SeedLink (socket + HELLO). ObsPy 1.5.1 construye
# ``SeedLinkConnection`` con ``timeout=None`` y su ``connect()`` llama a
# ``is_connected(self.timeout)``, que compara ``float < None`` → TypeError:
# "cannot connect to SeedLink server: '<' not supported between instances of
# 'float' and 'NoneType'". Con un timeout real y ``autoconnect=False``
# conectamos de forma explícita y esquivamos el bug.
SEEDLINK_HANDSHAKE_TIMEOUT_S: float = 30.0

#: Gracia (s) que esperamos a los canales que aún no han enviado nada antes
#: de emitir con hold (p. ej. estación de un solo canal vertical). Los
#: paquetes SeedLink de IRIS pueden traer ~13 s de datos y las componentes
#: llegan en paquetes separados; con una gracia corta (3 s) una horizontal
#: que aparecía tarde perdía su primer paquete completo (ya emitido como
#: hold). 10 s cubre el desfase típico sin retrasar demasiado el arranque.
CHANNEL_WAIT_GRACE_S: float = 10.0


def _create_seedlink_client(endpoint: str, on_data):
    """Crea y conecta un cliente SeedLink de ObsPy (workaround 1.5.1).

    No usar ``create_client()``: fuerza ``autoconnect=True`` con
    ``SeedLinkConnection.timeout=None`` y revienta con el TypeError de
    arriba en ObsPy 1.5.1. Aquí instanciamos con ``autoconnect=False``,
    fijamos un timeout y llamamos a ``connect()`` nosotros.
    """

    from obspy.clients.seedlink.easyseedlink import EasySeedLinkClient

    client = EasySeedLinkClient(endpoint, autoconnect=False)
    client.on_data = on_data
    try:
        client.conn.timeout = SEEDLINK_HANDSHAKE_TIMEOUT_S
    except Exception:  # pragma: no cover — versiones antiguas de ObsPy
        pass
    client.connect()
    return client


# ============================================================
# Worker que vive en su propio QThread
# ============================================================
class _SeedLinkWorker(QObject):
    """Cliente SeedLink que se ejecuta dentro de un ``QThread`` propio.

    No emite ``SampleBatch`` directamente: solo retransmite los traces
    crudos al hilo principal, donde la fuente los acumula y empaqueta.
    """

    # (canal_letra, start_ts, samples_float32, sample_rate_hz)
    trace_received = Signal(str, float, object, int)

    # Mensajes legibles para la barra de estado
    status = Signal(str)

    def __init__(
        self,
        host: str,
        port: int,
        network: str,
        station: str,
        location: str,
        channels: tuple[str, ...],
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._network = network
        self._station = station
        self._location = location
        self._channels = channels

        self._client = None  # type: ignore[assignment]
        self._stopping = False
        # Lock que protege accesos cruzados a ``self._client`` desde
        # los hilos worker (lo crea/usa) y UI (lo cierra desde stop()).
        # Sin esto, ObsPy hace SEGFAULT cuando dos hilos tocan el
        # socket subyacente a la vez.
        self._client_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Ciclo de vida (slots ejecutados en el hilo trabajador)
    # ------------------------------------------------------------------
    @Slot()
    def run(self) -> None:
        """Conecta y emite traces hasta que ``request_stop`` lo aborte.

        Pasos del flujo (cada uno emite ``status`` para que el usuario
        sepa exactamente dónde está; cualquier paso puede ser
        interrumpido por ``request_stop`` sin causar SEGFAULT):

          1. Importar ObsPy (perezoso).
          2. TCP pre-check (5 s) — falla rápido si el host está caído.
          3. Crear cliente SeedLink (HELLO handshake, sin timeout
             intencionado: algunos servidores tardan 30-60 s).
          4. Enviar SELECT por cada canal (típicamente instantáneo).
          5. ``client.run()`` — bucle bloqueante hasta cerrar socket.

        Después de cualquier punto de retorno comprobamos ``_stopping``
        antes de emitir mensajes de error para no "gritar" al usuario
        sobre un fallo que él mismo provocó al cancelar.
        """

        import time as _time

        # ──────────────────────────────────────────────────────────────
        # 1. Importar ObsPy
        # ──────────────────────────────────────────────────────────────
        try:
            from obspy.clients.seedlink import easyseedlink  # noqa: F401
        except Exception as exc:  # pragma: no cover
            self.status.emit(t("source.seedlink.obspy_missing", error=exc))
            return

        endpoint = f"{self._host}:{self._port}"

        # ──────────────────────────────────────────────────────────────
        # 2. TCP pre-check con timeout 5 s
        # ──────────────────────────────────────────────────────────────
        import socket as _socket

        if self._stopping:
            return
        self.status.emit(t("source.seedlink.dns_resolving", host=self._host))
        t0 = _time.monotonic()
        try:
            with _socket.create_connection(
                (self._host, self._port), timeout=TCP_PRECHECK_TIMEOUT_S
            ):
                pass
        except _socket.gaierror as exc:
            self.status.emit(
                t("source.seedlink.dns_failed", host=self._host, error=exc)
            )
            return
        except (_socket.timeout, TimeoutError):
            self.status.emit(
                t("source.seedlink.tcp_timeout",
                  seconds=int(TCP_PRECHECK_TIMEOUT_S), endpoint=endpoint)
            )
            return
        except OSError as exc:
            self.status.emit(
                t("source.seedlink.socket_unreachable",
                  endpoint=endpoint, error=exc)
            )
            return

        tcp_ms = (_time.monotonic() - t0) * 1000
        self.status.emit(t("source.seedlink.tcp_ok", ms=f"{tcp_ms:.0f}"))

        # ──────────────────────────────────────────────────────────────
        # 3. Crear cliente (HELLO + INFO). Usamos el helper con timeout
        #    explícito (workaround del bug de ObsPy 1.5.1). Almacenamos el
        #    cliente bajo el lock para que stop() pueda cerrarlo.
        # ──────────────────────────────────────────────────────────────
        if self._stopping:
            return
        self.status.emit(t("source.seedlink.handshake"))
        t1 = _time.monotonic()
        try:
            client = _create_seedlink_client(endpoint, self._on_trace)
        except Exception as exc:
            if not self._stopping:
                self.status.emit(
                    t("source.seedlink.handshake_failed", error=exc))
            return

        with self._client_lock:
            if self._stopping:
                # El usuario canceló mientras conectábamos. Cerrar el
                # cliente que acabamos de crear y salir.
                self._safe_shutdown_client(client)
                return
            self._client = client

        hello_s = _time.monotonic() - t1
        self.status.emit(
            t("source.seedlink.handshake_ok", seconds=f"{hello_s:.1f}"))

        # ──────────────────────────────────────────────────────────────
        # 4. SELECT con comodín por banda (una sola subscripción)
        # ──────────────────────────────────────────────────────────────
        # v0.7.7 fix: antes se enviaban 3 SELECT separadas (BHZ, BHN, BHE).
        # Algunos servidores solo atienden la primera → solo llegaba la
        # vertical y el hodograma se quedaba sin horizontales (caso IU.DAV).
        # Ahora una sola SELECT con comodín "{loc}{banda}?" (p. ej. "00BH?")
        # captura las TRES componentes de una vez — e incluye horizontales
        # nombradas BH1/BH2 (orientación arbitraria, común en GSN) además de
        # BHN/BHE. El mapeo 1→N, 2→E se hace en _on_trace.
        loc = (self._location or "").strip()
        if loc in ("", "*", "--"):
            loc = ""

        # Banda = código de canal sin la última letra de componente
        # ("BHZ" → "BH", "EHZ" → "EH"). Fallback a "BH" (broadband).
        band = self._channels[0][:-1] if self._channels else "BH"
        selector = f"{loc}{band}?"
        selectors = [selector]
        try:
            self.status.emit(
                t("source.seedlink.select",
                  index=1, total=1,
                  nslc=f"{self._network}.{self._station}",
                  selector=selector)
            )
            client.select_stream(self._network, self._station, selector)
        except Exception as exc:
            if not self._stopping:
                self.status.emit(t("source.seedlink.select_failed", error=exc))
            return

        if self._stopping:
            return
        self.status.emit(
            t("source.seedlink.subscribed", selectors=", ".join(selectors)))

        # ──────────────────────────────────────────────────────────────
        # 5. Loop bloqueante. Termina cuando:
        #    (a) stop() llama a socket.shutdown → run() recibe EOF
        #    (b) error de red → excepción
        # ──────────────────────────────────────────────────────────────
        try:
            client.run()
        except Exception as exc:
            if not self._stopping:
                self.status.emit(t("source.seedlink.conn_lost", error=exc))
        finally:
            # Limpiamos la referencia ANTES de emitir el último status
            # para que stop() no intente cerrar un cliente ya muerto.
            with self._client_lock:
                self._client = None
            if self._stopping:
                self.status.emit(t("source.seedlink.cancelled"))
            else:
                self.status.emit(t("source.seedlink.finished"))

    # ------------------------------------------------------------------
    # Cancelación segura — llamada desde el hilo principal
    # ------------------------------------------------------------------
    @staticmethod
    def _find_socket(obj):
        """Busca defensivamente el socket subyacente del cliente ObsPy.

        Diferentes versiones de ObsPy lo guardan en sitios distintos:
        ``client.slconn.socket``, ``client.conn.socket``, etc. Probamos
        varias rutas y devolvemos el primero que tenga ``shutdown``.
        """

        candidates = [
            ("slconn", "socket"),
            ("conn", "socket"),
            ("slconn",),
            ("conn",),
        ]
        for path in candidates:
            cur = obj
            for attr in path:
                cur = getattr(cur, attr, None)
                if cur is None:
                    break
            if cur is not None and hasattr(cur, "shutdown"):
                return cur
        return None

    def _safe_shutdown_client(self, client) -> None:
        """Cierra el cliente sin propagar excepciones.

        Dos pasos, ambos necesarios en ObsPy 1.5.1:

        1. ``conn.terminate()`` pone ``terminate_flag``: el bucle de
           ``collect()`` solo sale por ahí (recibir EOF lo deja durmiendo
           0.5 s en bucle, sin terminar nunca el QThread).
        2. ``socket.shutdown(SHUT_RDWR)`` despierta el ``recv()`` bloqueado.
           Usamos shutdown (no ``close()``) porque cerrar el socket desde
           otro hilo suele causar SEGFAULT en el backend C de ObsPy.

        Tras esto ``collect()`` devuelve SLTERMINATE, ``client.run()`` sale
        y el worker termina de forma ordenada.
        """

        import socket as _socket

        conn = getattr(client, "conn", client)
        try:
            terminate = getattr(conn, "terminate", None)
            if callable(terminate):
                terminate()
        except Exception:  # noqa: BLE001 — la cancelación nunca debe romper
            pass

        sock = self._find_socket(client)
        if sock is None:
            return
        try:
            sock.shutdown(_socket.SHUT_RDWR)
        except OSError:
            # Socket ya cerrado o no conectado: ignorar
            pass
        except Exception:  # noqa: BLE001
            pass

    @Slot()
    def request_stop(self) -> None:
        """Marca la cancelación y desbloquea el socket si existe.

        Es seguro llamarlo desde cualquier hilo y en cualquier momento
        del ciclo de vida (antes de conectar, durante el handshake, o
        ya streaming). NUNCA bloquea: solo emite la señal de shutdown
        y retorna. El hilo worker terminará naturalmente al detectar
        ``_stopping`` o al recibir EOF.
        """

        self._stopping = True
        with self._client_lock:
            client = self._client
        if client is None:
            return
        self._safe_shutdown_client(client)

    # Compatibilidad: alias del nombre antiguo
    stop = request_stop

    # ------------------------------------------------------------------
    # Callback invocado por ObsPy en el hilo trabajador
    # ------------------------------------------------------------------
    def _on_trace(self, trace) -> None:  # noqa: ANN001 (tipo dinámico de ObsPy)
        """Convierte el ``Trace`` recibido y lo reenvía al hilo principal."""

        # Última letra del canal → componente. v0.7.7: muchas estaciones
        # GSN nombran las horizontales BH1/BH2 (orientación arbitraria) en
        # vez de BHN/BHE; las tratamos como N/E para poder dibujar el
        # hodograma. 'EHZ'/'BHZ' → Z, 'BHN'/'BH1' → N, 'BHE'/'BH2' → E.
        last = str(trace.stats.channel)[-1].upper()
        channel_letter = {"Z": "Z", "N": "N", "E": "E",
                          "1": "N", "2": "E"}.get(last)
        if channel_letter is None:
            return

        # ``starttime`` es un objeto ``UTCDateTime``; ``.timestamp`` ya es Unix
        try:
            start_ts = float(trace.stats.starttime.timestamp)
        except Exception:
            start_ts = time.time()

        samples = np.asarray(trace.data, dtype=np.float32)
        sample_rate = int(round(float(trace.stats.sampling_rate)))

        self.trace_received.emit(channel_letter, start_ts, samples, sample_rate)


# ============================================================
# Fuente de datos pública
# ============================================================
class SeedLinkSource(DataSource):
    """Fuente de datos conectada a un servidor SeedLink real.

    Diseñada para conectar al puerto 18000 de un dispositivo Raspberry
    Shake en la red local del usuario. El host típico es ``rs.local``
    (mDNS) o la IP fija que el usuario haya asignado a su Shake.
    Conectarse a ``data.raspberryshake.org`` no funciona — ver el
    docstring del módulo para las razones.
    """

    # v0.7.7 fix: fuentes en proceso de cierre. Mantiene una referencia
    # FUERTE a cada fuente que se está deteniendo hasta que su hilo termina
    # de verdad. Sin esto, al desconectar (sobre todo DURANTE la conexión,
    # cuando el worker está bloqueado en el pre-check TCP), el controlador
    # suelta la fuente, el GC la destruye y un emit diferido del worker o el
    # propio teardown tocan un objeto C++ a medio morir → SEGFAULT (la app
    # se cierra al pulsar Detener).
    _closing: set = set()

    def __init__(
        self,
        host: str,
        port: int,
        network: str,
        station: str,
        location: str = "",
        channels: tuple[str, ...] = DEFAULT_CHANNELS,
        sample_rate_hz: int = 100,
        station_label: Optional[str] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        # Sanidad: avisar (no bloquear) si el usuario apunta al
        # endpoint público inexistente. Es el error más común.
        if host.endswith("raspberryshake.org") and port == 18000:
            import logging
            logging.getLogger(__name__).warning(
                "SeedLink: %s:%d no es un servidor público. "
                "Para datos en tiempo real conecta al puerto 18000 de "
                "TU PROPIO Raspberry Shake en la red local "
                "(ej: rs.local:18000 o 192.168.x.x:18000).",
                host, port,
            )

        self._sample_rate = int(sample_rate_hz)
        self._station_label = station_label or f"{network}.{station}"

        # Acumuladores por canal (recibidos en el hilo principal vía señal).
        # Cada canal es una secuencia CONTIGUA de muestras que empieza en
        # ``_ch_start``; los huecos se rellenan con hold para que el eje
        # temporal sea real. Ver _on_trace_received/_emit_pending.
        self._buf_lock = threading.Lock()
        self._chunks: dict[str, list[np.ndarray]] = {"Z": [], "N": [], "E": []}
        self._ch_start: dict[str, Optional[float]] = {
            "Z": None, "N": None, "E": None}
        self._ch_total: dict[str, int] = {"Z": 0, "N": 0, "E": 0}
        # Último valor real de cada canal, para rellenar huecos con "hold DC"
        # en vez de ceros.
        self._last_value: dict[str, float] = {"Z": 0.0, "N": 0.0, "E": 0.0}
        self._latest_ts: float = 0.0
        # Instante (epoch) hasta el que ya se emitió. Evita solapar ventanas
        # cuando los paquetes de cada canal llegan con retrasos distintos.
        self._emit_end: Optional[float] = None
        # Reloj de pared del primer trace: si las horizontales tardan en
        # aparecer (estación vertical-only), tras una gracia emitimos con
        # hold en vez de quedarnos esperando para siempre.
        self._first_data_wall: Optional[float] = None
        # Bandera: ¿ya hemos recibido el primer paquete tras conectar?
        # Sirve para emitir un solo "streaming" en cuanto llegue, en
        # lugar de spamear el statusbar con cada batch.
        self._got_first_packet: bool = False

        # Worker + hilo dedicado
        self._worker = _SeedLinkWorker(
            host=host,
            port=port,
            network=network,
            station=station,
            location=location,
            channels=channels,
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Cuando arranque el hilo, lanzar el bucle del cliente
        self._thread.started.connect(self._worker.run)

        # Recibir traces y mensajes de estado en el hilo principal
        self._worker.trace_received.connect(self._on_trace_received)
        self._worker.status.connect(self.status_changed)

        # Temporizador que empaqueta y emite SampleBatch periódicamente.
        # Se crea con ``self`` como parent para que viva en el hilo en el
        # que se construyó la fuente (el hilo de la UI).
        self._emit_timer = QTimer(self)
        self._emit_timer.setInterval(EMIT_INTERVAL_MS)
        self._emit_timer.timeout.connect(self._emit_pending)

    # ------------------------------------------------------------------
    # Metadatos
    # ------------------------------------------------------------------
    @property
    def station_label(self) -> str:
        return self._station_label

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Inicia el hilo SeedLink y el temporizador de emisión."""

        if self._running:
            return
        self._running = True
        self._thread.start()
        self._emit_timer.start()

    def stop(self, wait_ms: int = 0) -> None:
        """Detiene la fuente de forma ASÍNCRONA — sin congelar la UI.

        ``wait_ms``: 0 en desconexión normal (no bloquea). Al CERRAR la app
        se pasa un valor pequeño (p. ej. 3000) para esperar a que el hilo
        muera antes de salir del proceso — pero NUNCA se usa terminate().


        v0.7.7 fix (congelaba/crasheaba al desconectar): la versión anterior
        hacía ``thread.wait(8000)`` en el HILO DE LA UI (congelación de hasta
        8 s) y, si el hilo no moría, ``thread.terminate()`` — que puede
        CRASHEAR la app porque el worker puede estar dentro de ObsPy con el
        GIL tomado.

        Ahora:
          1. ``request_stop`` cierra el socket (``socket.shutdown``) → la
             llamada bloqueante de ObsPy (``client.run()``) recibe EOF y
             devuelve → el hilo termina solo, en segundo plano.
          2. Al emitir ``finished``, ``deleteLater`` libera worker e hilo.
             La UI no espera ni un milisegundo y nunca se fuerza terminate().
        """

        if not self._running:
            return
        self._running = False
        self._emit_timer.stop()

        # Desconectar TODAS las señales worker→source de inmediato. CLAVE:
        # al terminar ``run()`` el worker emite ``status`` ("cancelado" /
        # "finalizado"); si esa emisión diferida (cross-thread) llega cuando
        # la fuente ya se está destruyendo, choca contra un objeto C++ muerto
        # → SEGFAULT y la app se cierra al desconectar. Cortando ambas
        # señales aquí, ninguna emisión tardía toca a la fuente.
        for sig, slot in (
            (self._worker.trace_received, self._on_trace_received),
            (self._worker.status, self.status_changed),
        ):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

        # Cancelación cooperativa (no bloquea: solo cierra el socket).
        self._worker.request_stop()

        # Mantener la fuente VIVA hasta que el hilo termine de verdad (clave
        # para el caso de desconectar DURANTE la conexión, cuando el worker
        # sigue bloqueado en el pre-check unos segundos). worker e hilo se
        # liberan con el patrón estándar de Qt (finished → deleteLater).
        SeedLinkSource._closing.add(self)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.quit()
        if wait_ms > 0:
            # Solo al cerrar la app: espera acotada SIN terminate().
            self._thread.wait(wait_ms)

        # Vaciar acumuladores (la fuente puede recrearse más tarde).
        with self._buf_lock:
            for key in self._chunks:
                self._chunks[key] = []
                self._ch_start[key] = None
                self._ch_total[key] = 0
                self._last_value[key] = 0.0
            self._latest_ts = 0.0
            self._emit_end = None
            self._first_data_wall = None
        self._got_first_packet = False

    @Slot()
    def _on_thread_finished(self) -> None:
        """El hilo terminó de verdad (corre en el hilo principal: afinidad de
        la fuente). Ya no puede haber emits del worker → soltar la referencia
        fuerte para que el GC libere la fuente con seguridad."""

        SeedLinkSource._closing.discard(self)

    # ------------------------------------------------------------------
    # Slots de datos
    # ------------------------------------------------------------------
    @Slot(str, float, object, int)
    def _on_trace_received(
        self, channel: str, start_ts: float, samples: np.ndarray, sample_rate: int
    ) -> None:
        """Acumula un trace de UN canal, manteniendo su eje temporal real.

        Los paquetes SeedLink de Z/N/E llegan en instantes distintos y a
        veces con solapes o huecos. Aquí cada canal se guarda como una
        secuencia CONTIGUA: se recortan los solapes ya emitidos y los
        huecos internos se rellenan con hold. La alineación final entre
        canales la hace ``_emit_pending`` con ``_emit_end`` como referencia.
        """

        # Primer paquete tras conectar → notificar al usuario.
        # (No usamos status_changed aquí porque vive en el worker; el
        # hilo del SeedLinkSource reutiliza la señal vía passthrough.)
        if not self._got_first_packet:
            self._got_first_packet = True
            self._first_data_wall = time.monotonic()
            try:
                self.status_changed.emit("🟢 Streaming activo")
            except Exception:
                pass

        if samples.size == 0:
            return

        # Remuestrear a la tasa nominal del pipeline (config, típicamente
        # 100 Hz). Las estaciones broadband IRIS (BHZ/BHN/BHE) llegan a
        # 20/40 Hz; sin esto, el búfer (fijado a 100 Hz) interpreta mal el
        # eje temporal.
        if sample_rate != self._sample_rate:
            samples = self._resample(samples, sample_rate, self._sample_rate)
        samples = np.ascontiguousarray(samples, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return

        rate = float(self._sample_rate)
        with self._buf_lock:
            # Nunca re-emitir datos anteriores a la última ventana emitida:
            # si un canal llega tarde (p. ej. apareció tras la gracia), su
            # historia previa ya se rellenó con hold.
            if self._emit_end is not None and start_ts < self._emit_end:
                drop = int(round((self._emit_end - start_ts) * rate))
                if drop >= samples.size:
                    return
                samples = samples[drop:]
                start_ts = self._emit_end

            start = self._ch_start[channel]
            if start is None:
                self._ch_start[channel] = float(start_ts)
                self._ch_total[channel] = 0
                start = float(start_ts)

            cur_end = start + self._ch_total[channel] / rate
            if start_ts < cur_end:
                # Solape con lo ya acumulado (el servidor repite un tramo).
                drop = int(round((cur_end - start_ts) * rate))
                if drop >= samples.size:
                    return
                samples = samples[drop:]
                start_ts = cur_end
            elif start_ts > cur_end:
                # Hueco: rellenar con el último valor real (hold DC), no
                # con ceros (inyectaba picos verticales en el oscilograma).
                gap = int(round((start_ts - cur_end) * rate))
                if gap > 0:
                    self._chunks[channel].append(
                        np.full(gap, self._last_value[channel],
                                dtype=np.float32))
                    self._ch_total[channel] += gap

            self._chunks[channel].append(samples)
            self._ch_total[channel] += samples.size
            self._last_value[channel] = float(samples[-1])
            end_ts = start_ts + samples.size / rate
            if end_ts > self._latest_ts:
                self._latest_ts = end_ts

    @Slot()
    def _emit_pending(self) -> None:
        """Emite el tramo común ya disponible, alineado por tiempo real.

        Antes se concatenaba lo que hubiera de cada canal, se rellenaba al
        máximo y se escribía todo con un único timestamp. Con paquetes
        asíncronos (IRIS manda BH1/BH2/BHZ por separado) eso repetía tramos
        de tiempo en el búfer → oscilograma con picos y hodograma desfasado.
        Ahora se calcula el fin común (``min`` de los canales disponibles),
        se extrae la ventana ``[_emit_end, fin]`` de cada canal y solo se
        avanza hasta ahí. Los canales que no han llegado se rellenan con
        hold; si no aparecen tras ``CHANNEL_WAIT_GRACE_S`` se emite igual.
        """

        rate = float(self._sample_rate)
        with self._buf_lock:
            seen = [ch for ch in ("Z", "N", "E")
                    if self._ch_start[ch] is not None]
            if not seen:
                return
            grace_ok = (
                self._first_data_wall is not None
                and time.monotonic() - self._first_data_wall
                >= CHANNEL_WAIT_GRACE_S
            )
            if len(seen) < 3 and not grace_ok:
                # Esperar a las horizontales al conectar (evita empezar con
                # tramos que luego habría que rellenar/duplicar).
                return

            ends = {
                ch: self._ch_start[ch] + self._ch_total[ch] / rate
                for ch in seen
            }
            target_end = min(ends.values())
            if self._emit_end is None:
                # Alinear el comienzo al canal que empieza más tarde, para no
                # inventar historia antes de que existiera.
                self._emit_end = max(self._ch_start[ch] for ch in seen)
            n = int(round((target_end - self._emit_end) * rate))
            if n <= 0:
                return

            t0 = self._emit_end
            z = self._slice_and_trim_locked("Z", t0, n, rate)
            n_arr = self._slice_and_trim_locked("N", t0, n, rate)
            e = self._slice_and_trim_locked("E", t0, n, rate)
            self._emit_end = t0 + n / rate
            ts = self._emit_end

        self.data_ready.emit(SampleBatch(
            timestamp_unix=ts,
            sample_rate_hz=self._sample_rate,
            z=z,
            n=n_arr,
            e=e,
        ))

    def _slice_and_trim_locked(
        self, channel: str, t0: float, n: int, rate: float
    ) -> np.ndarray:
        """Extrae ``n`` muestras de ``channel`` para ``[t0, t0+n/rate)``.

        Debe llamarse con ``_buf_lock`` tomado. Rellena con hold lo que
        falte (canal aún sin datos, huecos antes/después) y descarta de la
        cola lo que ya queda por detrás del instante emitido.
        """

        start = self._ch_start[channel]
        total = self._ch_total[channel]
        if start is None or total == 0:
            return np.full(n, self._last_value[channel], dtype=np.float32)

        buf = np.concatenate(self._chunks[channel])
        total = buf.size
        offset = int(round((t0 - start) * rate))
        src_start = max(0, offset)
        src_end = min(total, offset + n)

        # Hold de partida: última muestra antes de la ventana (si la hay);
        # si no, el último valor real del canal.
        hold = self._last_value[channel]
        if 0 < src_start <= total:
            hold = float(buf[src_start - 1])
        out = np.full(n, hold, dtype=np.float32)

        written = 0
        if src_end > src_start:
            chunk = buf[src_start:src_end]
            dst = max(0, -offset)
            out[dst:dst + chunk.size] = chunk
            written = chunk.size
            hold = float(chunk[-1])

        # Si el tramo de datos no cubre toda la ventana, el resto es hold.
        dst_end = max(0, -offset) + written
        if dst_end < n:
            out[dst_end:] = hold

        # Consumir lo que ya queda por detrás de t0 + n.
        drop = max(0, min(total, offset + n))
        if drop > 0:
            rest = buf[drop:]
            self._chunks[channel] = [rest] if rest.size else []
            self._ch_total[channel] = rest.size
            self._ch_start[channel] = start + drop / rate
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        """Remuestrea ``samples`` de ``src_rate`` a ``dst_rate`` (interp lineal).

        Suficiente para visualización/detección; evita dependencias y es
        barato. Si las tasas coinciden o el bloque está vacío, no hace nada.
        """

        if src_rate == dst_rate or samples.size == 0:
            return samples
        n_out = max(1, int(round(samples.size * dst_rate / src_rate)))
        x_old = np.arange(samples.size, dtype=np.float64)
        x_new = np.linspace(0.0, samples.size - 1, n_out)
        return np.interp(x_new, x_old, samples).astype(np.float32)

    @staticmethod
    def _pad_left(arr: np.ndarray, length: int, fill: float = 0.0) -> np.ndarray:
        """Rellena al inicio con ``fill`` (por defecto 0) hasta ``length``."""

        if arr.size == length:
            return arr
        if arr.size > length:
            return arr[-length:]
        out = np.full(length, fill, dtype=np.float32)
        out[length - arr.size :] = arr
        return out
