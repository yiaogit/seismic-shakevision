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

from shakevision.sources.base import DataSource, SampleBatch


# Canales por defecto: vertical, norte, este (instrumento de banda corta)
DEFAULT_CHANNELS: tuple[str, str, str] = ("EHZ", "EHN", "EHE")

# Periodo del temporizador que empaqueta y emite SampleBatch (ms)
EMIT_INTERVAL_MS: int = 100


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
            from obspy.clients.seedlink.easyseedlink import create_client
        except Exception as exc:  # pragma: no cover
            self.status.emit(f"❌ ObsPy no disponible: {exc}")
            return

        endpoint = f"{self._host}:{self._port}"

        # ──────────────────────────────────────────────────────────────
        # 2. TCP pre-check con timeout 5 s
        # ──────────────────────────────────────────────────────────────
        import socket as _socket

        if self._stopping:
            return
        self.status.emit(f"🔍 Resolviendo DNS «{self._host}»…")
        t0 = _time.monotonic()
        try:
            with _socket.create_connection(
                (self._host, self._port), timeout=5.0
            ):
                pass
        except _socket.gaierror as exc:
            self.status.emit(
                f"❌ DNS falló para «{self._host}»: {exc}. "
                "Verifica el nombre del host o tu conexión."
            )
            return
        except (_socket.timeout, TimeoutError):
            self.status.emit(
                f"❌ TCP timeout (5 s) hacia {endpoint}. "
                "Probable firewall/VPN bloqueando :{self._port}."
            )
            return
        except OSError as exc:
            self.status.emit(f"❌ Socket inalcanzable {endpoint}: {exc}")
            return

        tcp_ms = (_time.monotonic() - t0) * 1000
        self.status.emit(
            f"🌐 TCP OK ({tcp_ms:.0f} ms). Iniciando handshake SeedLink…"
        )

        # ──────────────────────────────────────────────────────────────
        # 3. Crear cliente (HELLO + INFO). Sin timeout: dejamos que
        #    el servidor responda a su ritmo, pero almacenamos el
        #    cliente bajo el lock para que stop() pueda cerrarlo.
        # ──────────────────────────────────────────────────────────────
        if self._stopping:
            return
        self.status.emit(
            "🤝 Handshake con servidor SeedLink (puede tardar 10-60 s "
            "si el servidor está congestionado)…"
        )
        t1 = _time.monotonic()
        try:
            client = create_client(endpoint, on_data=self._on_trace)
        except Exception as exc:
            if not self._stopping:
                self.status.emit(f"❌ Handshake falló: {exc}")
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
            f"✅ Handshake OK ({hello_s:.1f} s). Enviando SELECT…"
        )

        # ──────────────────────────────────────────────────────────────
        # 4. SELECT por cada canal
        # ──────────────────────────────────────────────────────────────
        loc = (self._location or "").strip()
        if loc in ("", "*", "--"):
            loc = ""

        selectors: list[str] = []
        try:
            for i, channel in enumerate(self._channels, start=1):
                if self._stopping:
                    return
                selector = f"{loc}{channel}" if loc else channel
                selectors.append(selector)
                self.status.emit(
                    f"📡 SELECT {i}/{len(self._channels)}: "
                    f"{self._network}.{self._station} → {selector}"
                )
                client.select_stream(self._network, self._station, selector)
        except Exception as exc:
            if not self._stopping:
                self.status.emit(f"❌ SELECT falló: {exc}")
            return

        if self._stopping:
            return
        self.status.emit(
            f"⏳ Suscrito a [{', '.join(selectors)}]. "
            "Esperando primer paquete…"
        )

        # ──────────────────────────────────────────────────────────────
        # 5. Loop bloqueante. Termina cuando:
        #    (a) stop() llama a socket.shutdown → run() recibe EOF
        #    (b) error de red → excepción
        # ──────────────────────────────────────────────────────────────
        try:
            client.run()
        except Exception as exc:
            if not self._stopping:
                self.status.emit(f"❌ Conexión perdida: {exc}")
        finally:
            # Limpiamos la referencia ANTES de emitir el último status
            # para que stop() no intente cerrar un cliente ya muerto.
            with self._client_lock:
                self._client = None
            if self._stopping:
                self.status.emit("⏹ Conexión cancelada por el usuario.")
            else:
                self.status.emit("Cliente SeedLink finalizado.")

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
        """Cierra el socket del cliente sin propagar excepciones.

        Usamos ``socket.shutdown(SHUT_RDWR)`` en vez de ``close()``:
        shutdown notifica al kernel que ambos lados terminaron, lo que
        hace que ObsPy reciba EOF en su recv() y salga del bucle
        ordenadamente. ``close()`` desde un hilo distinto al que abrió
        el socket suele causar SEGFAULT en el C-backend.
        """

        import socket as _socket

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

        # Última letra del canal: 'EHZ' -> 'Z', etc.
        channel_letter = str(trace.stats.channel)[-1].upper()
        if channel_letter not in ("Z", "N", "E"):
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

        # Acumuladores por canal (recibidos en el hilo principal vía señal)
        self._buf_lock = threading.Lock()
        self._chunks: dict[str, list[np.ndarray]] = {"Z": [], "N": [], "E": []}
        self._latest_ts: float = 0.0
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

    def stop(self) -> None:
        """Detiene el temporizador, cancela la conexión y espera al hilo.

        El cierre es de tres pasos progresivos para garantizar que el
        hilo trabajador SIEMPRE muere, incluso si está bloqueado en un
        recv() de ObsPy sin timeout:

          1. ``request_stop`` — set flag + ``socket.shutdown(SHUT_RDWR)``.
             Si el worker está en recv(), recibirá EOF y saldrá.
          2. ``thread.wait(8000)`` — 8 segundos de gracia.
          3. Si sigue vivo: ``thread.terminate()`` (nuclear pero
             seguro porque el worker no comparte estado con la UI más
             que vía señales).

        El último paso es importante: si ObsPy se queda bloqueado en
        algún lugar interno que ignora el shutdown del socket, la UI
        no debe colgarse esperando.
        """

        if not self._running:
            return
        self._running = False
        self._emit_timer.stop()

        # 1) Cancelación cooperativa (no bloquea)
        self._worker.request_stop()

        # 2) Esperar a que el hilo termine ordenadamente
        self._thread.quit()
        if not self._thread.wait(8000):
            # 3) El hilo no respondió en 8 s. Probable bug en ObsPy o
            # socket bloqueado en una llamada que ignora shutdown.
            # ``terminate()`` aborta el hilo a nivel del SO sin
            # liberar recursos Python (riesgoso pero NO causa SEGFAULT
            # en el hilo principal porque cierra al hijo limpiamente).
            import logging
            logging.getLogger(__name__).warning(
                "SeedLink: hilo worker no terminó en 8 s, forzando terminate()"
            )
            self._thread.terminate()
            self._thread.wait(2000)

        # Vaciar acumuladores por si se reinicia la fuente más tarde
        with self._buf_lock:
            for key in self._chunks:
                self._chunks[key] = []
            self._latest_ts = 0.0
        self._got_first_packet = False

    # ------------------------------------------------------------------
    # Slots de datos
    # ------------------------------------------------------------------
    @Slot(str, float, object, int)
    def _on_trace_received(
        self, channel: str, start_ts: float, samples: np.ndarray, sample_rate: int
    ) -> None:
        """Acumula un trace recibido en la cola del canal correspondiente."""

        # Primer paquete tras conectar → notificar al usuario.
        # (No usamos status_changed aquí porque vive en el worker; el
        # hilo del SeedLinkSource reutiliza la señal vía passthrough.)
        if not self._got_first_packet:
            self._got_first_packet = True
            try:
                self.status_changed.emit("🟢 Streaming activo")
            except Exception:
                pass

        # Si la frecuencia de muestreo del trace difiere de la nominal,
        # no intentamos remuestrear: aceptamos el bloque tal cual; el
        # ratio es típicamente exactamente 100 Hz en Raspberry Shake.
        with self._buf_lock:
            self._chunks.setdefault(channel, []).append(samples)
            # Marca de tiempo del extremo del trace (start + duración)
            duration = samples.size / max(1, sample_rate)
            end_ts = start_ts + duration
            if end_ts > self._latest_ts:
                self._latest_ts = end_ts

    @Slot()
    def _emit_pending(self) -> None:
        """Empaqueta lo acumulado por canal y lo emite como un único batch."""

        with self._buf_lock:
            chunks = {
                ch: (
                    np.concatenate(self._chunks[ch])
                    if self._chunks.get(ch)
                    else np.zeros(0, dtype=np.float32)
                )
                for ch in ("Z", "N", "E")
            }
            for key in self._chunks:
                self._chunks[key] = []
            latest_ts = self._latest_ts

        # Si no llegó nada en este intervalo, no emit (la UI no se mueve)
        max_len = max(c.size for c in chunks.values())
        if max_len == 0:
            return

        # Alinear longitudes rellenando con ceros AL INICIO de los
        # canales más cortos. Eso preserva el extremo derecho (más
        # reciente) en el oscilograma.
        z = self._pad_left(chunks["Z"], max_len)
        n = self._pad_left(chunks["N"], max_len)
        e = self._pad_left(chunks["E"], max_len)

        batch = SampleBatch(
            timestamp_unix=latest_ts if latest_ts > 0 else time.time(),
            sample_rate_hz=self._sample_rate,
            z=z,
            n=n,
            e=e,
        )
        self.data_ready.emit(batch)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _pad_left(arr: np.ndarray, length: int) -> np.ndarray:
        """Rellena con ceros al inicio hasta alcanzar ``length``."""

        if arr.size == length:
            return arr
        if arr.size > length:
            return arr[-length:]
        out = np.zeros(length, dtype=np.float32)
        out[length - arr.size :] = arr
        return out
