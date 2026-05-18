"""
Reproductor de audio basado en QAudioSink.

Encapsula el ciclo de vida del backend de audio nativo de Qt para
poder reproducir un buffer ``int16 PCM mono`` con una sola llamada
desde el resto de la UI. Maneja:

  * arranque y parada limpios;
  * inexistencia de dispositivo de salida (entornos sin sonido / CI);
  * señales Qt para que la UI pueda activar/desactivar el botón de
    reproducción mientras dura el clip.

Usamos QtMultimedia (incluido en PySide6) para no añadir dependencias
externas. El precio: la API es algo verbosa, pero cabe en ~120 líneas.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices


class AudioPlayer(QObject):
    """Reproductor mono int16 PCM con señales de inicio y fin.

    Máquina de estados interna
    --------------------------
    Qt notifica cambios de estado del sink vía ``stateChanged``, pero
    el orden es engañoso: en macOS el sink emite ``IdleState`` ANTES
    de aceptar el primer byte, lo que el código antiguo interpretaba
    como "ya terminó" → quedaba colgado en "Reproduciendo".

    Solución: ``_has_been_active`` bloquea el evento de fin hasta que
    el sink haya pasado al menos una vez por ``ActiveState``. Así
    sabemos que datos REALES se reprodujeron antes de aceptar el
    ``IdleState`` como "fin natural".
    """

    playback_started = Signal()
    playback_finished = Signal()
    playback_failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._sink: Optional[QAudioSink] = None
        self._buffer: Optional[QBuffer] = None
        self._is_playing: bool = False
        # Bandera de la máquina de estados (ver docstring de clase).
        # Se resetea en cada ``play()`` y se eleva en cuanto Qt
        # notifica ``ActiveState`` por primera vez.
        self._has_been_active: bool = False

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    @property
    def is_playing(self) -> bool:
        return self._is_playing

    # ------------------------------------------------------------------
    # Reproducción
    # ------------------------------------------------------------------
    def play(self, samples: np.ndarray, audio_rate_hz: int) -> bool:
        """Reproduce el buffer indicado y devuelve ``True`` si arrancó.

        Si ya hay otro clip sonando, lo detiene y arranca el nuevo.
        Devuelve ``False`` y emite ``playback_failed`` en caso de error
        (sin dispositivo, formato no soportado, buffer vacío, etc.).
        """

        if samples.size == 0:
            # ``audio.error.*`` son claves i18n; MainWindow las traduce.
            self.playback_failed.emit("audio.error.no_samples")
            return False

        # Detener cualquier reproducción previa
        self.stop()

        # Comprobar que haya un dispositivo de salida disponible
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self.playback_failed.emit("audio.error.no_device")
            return False

        # Configurar el formato (mono int16 a la frecuencia indicada)
        fmt = QAudioFormat()
        fmt.setSampleRate(int(audio_rate_hz))
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)

        if not device.isFormatSupported(fmt):
            self.playback_failed.emit("audio.error.format_unsupported")
            return False

        # Empaquetar las muestras como QByteArray dentro de un QBuffer.
        # Asegurar contigüidad y dtype antes de tocar bytes() para evitar
        # cualquier sorpresa con vistas no contiguas.
        pcm = np.ascontiguousarray(samples, dtype=np.int16)
        data = QByteArray(pcm.tobytes())

        self._buffer = QBuffer(self)
        self._buffer.setData(data)
        if not self._buffer.open(QIODevice.ReadOnly):
            self.playback_failed.emit("audio.error.buffer_open")
            return False

        # ─── ORDEN CRÍTICO ───
        # Debemos marcar _is_playing ANTES de start(), porque en macOS
        # el sink puede emitir IdleState SÍNCRONAMENTE dentro de start(),
        # y _on_state_changed lo necesita para no descartar el evento.
        self._is_playing = True
        self._has_been_active = False  # reset de la máquina de estados
        self.playback_started.emit()

        self._sink = QAudioSink(device, fmt, self)
        self._sink.stateChanged.connect(self._on_state_changed)
        self._sink.start(self._buffer)
        return True

    def stop(self) -> None:
        """Para la reproducción si la hay (idempotente y reentrante seguro).

        Orden importante para no crashear:
          1. Desconectar stateChanged ANTES de stop() para que la
             llamada a stop() no nos dispare _on_state_changed
             recursivamente (sería re-entrada con _sink None a medias).
          2. Llamar a sink.stop() (puede ser async en macOS).
          3. Posponer deleteLater 100 ms para dejar tiempo al backend
             de Qt a soltar el sink antes de que destruyamos su QObject.
        """

        sink = self._sink
        buf = self._buffer

        # Limpiar referencias INMEDIATAMENTE para que llamadas
        # re-entrantes (otra señal) vean estado limpio.
        self._sink = None
        self._buffer = None
        was_playing = self._is_playing
        self._is_playing = False
        self._has_been_active = False

        if sink is not None:
            # PASO 1: desconectar antes de stop() para evitar re-entrada
            try:
                sink.stateChanged.disconnect(self._on_state_changed)
            except (RuntimeError, TypeError):
                pass
            # PASO 2: detener
            try:
                sink.stop()
            except Exception:  # noqa: BLE001
                pass
            # PASO 3: deleteLater diferido (deja que Qt suelte el backend)
            QTimer.singleShot(100, sink.deleteLater)

        if buf is not None:
            try:
                buf.close()
            except Exception:  # noqa: BLE001
                pass
            QTimer.singleShot(100, buf.deleteLater)

        # Emitir el "fin" solo si efectivamente estábamos reproduciendo
        # (idempotencia: dos stop() seguidos no emiten dos veces).
        if was_playing:
            self.playback_finished.emit()

    # ------------------------------------------------------------------
    # Slots internos
    # ------------------------------------------------------------------
    def _on_state_changed(self, state) -> None:  # noqa: ANN001 (Enum dinámico)
        """Máquina de estados: detecta el final REAL del clip.

        Transiciones esperadas en una reproducción normal:
            (Stopped) → Active → Idle    ← fin natural
            (Stopped) → Active → Stopped ← stop() externo

        En macOS también se observa:
            (Stopped) → Idle → Active → Idle   (Idle inicial sin datos)
            (Stopped) → Active → Suspended → Idle (suspensión transitoria)

        Por eso esperamos a haber visto ``ActiveState`` al menos una
        vez antes de aceptar ``IdleState`` como fin del clip.
        """

        from PySide6.QtMultimedia import QAudio

        if state == QAudio.ActiveState:
            # Marca: a partir de aquí, un Idle siguiente sí es "fin".
            self._has_been_active = True
            return

        if state == QAudio.StoppedState:
            # stop() externo o error: tratar como fin si estábamos
            # reproduciendo. No tocamos referencias (la propia stop()
            # se encarga de la limpieza).
            if self._is_playing:
                self._is_playing = False
                self.playback_finished.emit()
            return

        if state == QAudio.IdleState:
            # Solo cuenta como "fin natural" si ya pasamos por Active
            # (es decir, llegamos a reproducir datos reales). En caso
            # contrario es el "Idle inicial" sin datos, que ignoramos.
            if self._is_playing and self._has_been_active:
                self._is_playing = False
                self.playback_finished.emit()
                # Limpieza diferida — NO usamos stop() para evitar
                # re-entrada en este slot vía señales del sink.
                if self._sink is not None:
                    try:
                        self._sink.stateChanged.disconnect(
                            self._on_state_changed
                        )
                    except (RuntimeError, TypeError):
                        pass
                    QTimer.singleShot(100, self._sink.deleteLater)
                    self._sink = None
                if self._buffer is not None:
                    try:
                        self._buffer.close()
                    except Exception:  # noqa: BLE001
                        pass
                    QTimer.singleShot(100, self._buffer.deleteLater)
                    self._buffer = None
