"""
Configuración global de la aplicación.

Contiene los valores por defecto para:
  - Estaciones públicas de Raspberry Shake mostradas en el selector de la UI.
  - Parámetros del flujo de datos (frecuencia de muestreo, tamaño de búfer).
  - Parámetros iniciales de los filtros y del detector STA/LTA.

Todos estos valores son ajustables desde la interfaz; los definidos aquí
solo representan el estado inicial al arrancar la aplicación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# Estaciones de ejemplo
# ============================================================
# Lista inicial de estaciones públicas de Raspberry Shake (red AM).
# El usuario puede añadir o cambiar estaciones desde la interfaz.
# Formato: (etiqueta visible, red, estación, ubicación, canal_z)
@dataclass(frozen=True)
class StationPreset:
    """Preset de estación mostrado en el menú desplegable de la UI.

    ``seedlink_host`` y ``seedlink_port`` son opcionales. Si están a
    ``None``, MainWindow consulta ``seedlink_server_for(network)`` para
    encontrar un servidor por defecto basado en el código de red:
    redes profesionales (IU, US, II, IC…) se enrutan a IRIS, AM se
    enruta a ``rs.local`` (LAN). Definirlos explícitamente permite
    enviar un preset construido al vuelo desde el globo apuntando ya
    al servidor correcto.
    """

    label: str           # Etiqueta visible en la UI
    network: str         # Código de red (ej. "IU" para IRIS, "AM" para Shake)
    station: str         # Código de estación (ej. "ANMO", "R1234")
    location: str = ""   # Código de ubicación (normalmente vacío)
    channel: str = "EHZ" # Canal vertical por defecto
    seedlink_host: Optional[str] = None  # Override del servidor SeedLink
    seedlink_port: Optional[int] = None  # Override del puerto


# Conjunto inicial de presets. El usuario podrá añadir más en tiempo de
# ejecución; estos solo sirven como punto de partida.
DEFAULT_STATIONS: list[StationPreset] = [
    # v0.8.0: se eliminó la estación "Demo (datos simulados)" (XX.MOCK).
    # ⚠ Las estaciones AM remotas requieren acceso real-time vía LAN
    # al Raspberry Shake propio. Conectar al servidor público falla.
    # Estos presets sirven solo como ejemplo del formato N.S.L.C.; el usuario
    # añade estaciones IRIS reales desde el globo ("Monitorizar en vivo").
    StationPreset(label="Mi Shake LAN (rs.local)",  network="AM", station="LOCAL"),
]

# Servidor SeedLink. Por defecto apunta a la dirección mDNS estándar
# del Raspberry Shake en la red local del usuario. NO usar
# data.raspberryshake.org — ese host no expone SeedLink público.
# Documentación: https://manual.raspberryshake.org/traces.html
DEFAULT_SEEDLINK_HOST: str = "rs.local"
DEFAULT_SEEDLINK_PORT: int = 18000


# ============================================================
# Mapa de red SeedLink → servidor
# ============================================================
# IRIS opera un servidor SeedLink público en
# ``rtserve.iris.washington.edu:18000`` que transmite los datos en
# tiempo real de las redes troncales profesionales (IU, US, II, IC,
# GT…). Es la vía estándar para conectar a una estación USGS/IRIS
# desde el cliente de un usuario final.
#
# Para Raspberry Shake (red AM) no existe SeedLink público; la única
# vía gratuita es conectar al puerto 18000 del propio dispositivo en
# la red local. El usuario debe configurarlo manualmente.
IRIS_SEEDLINK_HOST: str = "rtserve.iris.washington.edu"
IRIS_SEEDLINK_PORT: int = 18000

# Redes troncales servidas por IRIS rtserve. La lista no es exhaustiva
# pero cubre las que aparecen en el globo (IU + US por defecto en el
# IRISClient + las grandes amigas internacionales).
_IRIS_NETWORKS: frozenset[str] = frozenset({
    "IU",   # Global Seismograph Network (USGS/IRIS)
    "US",   # United States National Seismic Network
    "II",   # IRIS/IDA Network
    "IC",   # New China Digital Seismograph Network
    "GT",   # Global Telemetered Network
    "CU",   # USGS Caribbean
    "G",    # GEOSCOPE
    "GE",   # GEOFON
    "C",    # Chile National Seismic Network
})

# Mapa explícito red → (host, puerto). El fallback para redes
# desconocidas también va a IRIS (suelen ser autorizadas).
SEEDLINK_SERVERS: dict[str, tuple[str, int]] = {
    net: (IRIS_SEEDLINK_HOST, IRIS_SEEDLINK_PORT) for net in _IRIS_NETWORKS
}
SEEDLINK_SERVERS["AM"] = (DEFAULT_SEEDLINK_HOST, DEFAULT_SEEDLINK_PORT)


def seedlink_server_for(network: str) -> tuple[str, int]:
    """Devuelve (host, port) por defecto para una red SeedLink.

    Si la red está en ``SEEDLINK_SERVERS`` se devuelve su par. Para
    redes profesionales no listadas, se cae a IRIS (suelen ser
    miembros del repositorio público FDSN). Para la red AM
    (Raspberry Shake) se devuelve ``rs.local`` aunque casi seguro
    fallará — el usuario debe sustituirlo por la IP de su Shake.
    """

    return SEEDLINK_SERVERS.get(network, (IRIS_SEEDLINK_HOST, IRIS_SEEDLINK_PORT))


# ============================================================
# Canales (componentes) por red — ¡CRÍTICO!
# ============================================================
# Cada red usa códigos de canal distintos según el tipo de instrumento.
# Pedir "EHZ" a un sismómetro de banda ancha (IRIS) provoca un
# "timeout silencioso": el servidor acepta el SELECT pero nunca envía
# datos porque el stream no existe.
#
#   EHZ/EHN/EHE  → short-period vertical/N/E    (Raspberry Shake AM)
#   BHZ/BHN/BHE  → broadband 40 Hz              (IRIS IU/US/II/IC)
#   HHZ/HHN/HHE  → high broadband 100 Hz        (algunos sitios IRIS)
#   LHZ/LHN/LHE  → long-period 1 Hz             (todos los sitios IRIS)
#
# Usamos BHZ para IRIS porque está disponible en todas las estaciones
# IU/US y la tasa de 40 Hz da margen para detectar ondas hasta ~20 Hz
# (sobrado para sismos regionales).
SEEDLINK_CHANNELS: dict[str, tuple[str, str, str]] = {
    "AM": ("EHZ", "EHN", "EHE"),                      # Raspberry Shake
    "IU": ("BHZ", "BHN", "BHE"),                      # IRIS / USGS Global
    "US": ("BHZ", "BHN", "BHE"),                      # USNSN
    "II": ("BHZ", "BHN", "BHE"),                      # IRIS/IDA
    "IC": ("BHZ", "BHN", "BHE"),                      # New China Digital
    "GT": ("BHZ", "BHN", "BHE"),                      # Global Telemetered
    "CU": ("BHZ", "BHN", "BHE"),                      # USGS Caribbean
    "G":  ("BHZ", "BHN", "BHE"),                      # GEOSCOPE
    "GE": ("BHZ", "BHN", "BHE"),                      # GEOFON
    "C":  ("BHZ", "BHN", "BHE"),                      # Chile NSN
}

# Códigos de location por red. SeedLink no acepta wildcards: hay que
# pasar el location concreto. Para la mayoría de IRIS IU/US el broadband
# vive en "00" (algunas tienen tasas mayores en "10"). AM (Shake) usa
# location vacío.
SEEDLINK_LOCATIONS: dict[str, str] = {
    "AM": "",        # Shake: sin location
    "IU": "00",      # IRIS broadband estándar
    "US": "00",
    "II": "00",
    "IC": "00",
    "GT": "00",
    "CU": "00",
    "G":  "00",
    "GE": "",        # GEOFON varía; vacío deja que el servidor decida
    "C":  "00",
}


def seedlink_channels_for(network: str) -> tuple[str, str, str]:
    """Devuelve el trío (Z, N, E) de códigos de canal para una red.

    Para redes desconocidas asumimos broadband estándar (BHZ/BHN/BHE),
    que es lo que cualquier red profesional FDSN suele exponer.
    """

    return SEEDLINK_CHANNELS.get(network, ("BHZ", "BHN", "BHE"))


def seedlink_location_for(network: str) -> str:
    """Devuelve el código de location SeedLink por defecto de una red."""

    return SEEDLINK_LOCATIONS.get(network, "00")


# ============================================================
# Parámetros del flujo de datos
# ============================================================
@dataclass
class StreamConfig:
    """Configuración del flujo de muestras en tiempo real."""

    sample_rate_hz: int = 100               # Frecuencia de muestreo nominal de Raspberry Shake
    buffer_seconds: int = 300               # Longitud del búfer circular (5 minutos)
    display_window_seconds: float = 30.0    # Ventana visible en el panel de forma de onda
    refresh_fps: int = 30                   # Frecuencia de refresco de la UI


# ============================================================
# Parámetros del filtro Butterworth
# ============================================================
@dataclass
class FilterConfig:
    """Parámetros iniciales del filtro pasa banda Butterworth."""

    enabled: bool = True
    lowcut_hz: float = 0.5      # Frecuencia inferior de corte
    highcut_hz: float = 10.0    # Frecuencia superior de corte
    order: int = 4              # Orden del filtro
    detrend: bool = True        # Restar la media antes de filtrar


# ============================================================
# Parámetros del detector STA/LTA
# ============================================================
@dataclass
class TriggerConfig:
    """Parámetros iniciales del detector STA/LTA clásico."""

    enabled: bool = True
    sta_seconds: float = 1.0    # Ventana corta (Short Term Average)
    lta_seconds: float = 10.0   # Ventana larga (Long Term Average)
    threshold_on: float = 3.5   # Umbral de activación
    threshold_off: float = 1.5  # Umbral de desactivación
    pre_event_seconds: float = 60.0   # Segundos previos a guardar
    post_event_seconds: float = 240.0 # Segundos posteriores a guardar


# ============================================================
# Configuración global agregada
# ============================================================
@dataclass
class AppConfig:
    """Contenedor de toda la configuración por defecto de la aplicación."""

    stations: list[StationPreset] = field(default_factory=lambda: list(DEFAULT_STATIONS))
    seedlink_host: str = DEFAULT_SEEDLINK_HOST
    seedlink_port: int = DEFAULT_SEEDLINK_PORT
    stream: StreamConfig = field(default_factory=StreamConfig)
    filt: FilterConfig = field(default_factory=FilterConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)


# Instancia global utilizada por la UI mientras no exista persistencia
# en disco (se añadirá en una fase posterior).
DEFAULT_APP_CONFIG: AppConfig = AppConfig()
