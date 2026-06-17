"""
Catálogo local persistente de eventos revisados (QuakeML).

Acumula las fases (P/S) que el usuario marca en Replay en un único fichero
``~/SeismicGuard/catalog.xml`` (formato QuakeML, estándar — lo leen ObsPy,
SeisComP, etc.). Complementa la exportación por evento: aquí se VA SUMANDO.

Todo defensivo: si ObsPy no está disponible o falla la E/S, los métodos
devuelven ``False`` / lista vacía sin romper la UI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH: Path = Path.home() / "SeismicGuard" / "catalog.xml"


class CatalogStore:
    """Lee/escribe un catálogo QuakeML local, acumulando eventos."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path or DEFAULT_CATALOG_PATH)

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    def add_event(
        self, net: str, sta: str, loc: str, band: str, picks: dict,
        origin: Optional[dict] = None, description: str = "",
    ) -> bool:
        """Añade un evento (con sus picks) al catálogo y lo guarda.

        ``picks``: ``{fase: tiempo_unix}``. ``origin``: dict con
        ``lat/lon/depth_km/origin_ts`` o ``None``.
        """

        try:
            from obspy import UTCDateTime, read_events
            from obspy.core.event import (
                Catalog, Comment, Event, Origin, Pick, WaveformStreamID,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("CatalogStore: ObsPy no disponible (%s)", exc)
            return False

        cat = None
        if self._path.exists():
            try:
                cat = read_events(str(self._path))
            except Exception:  # noqa: BLE001
                cat = None
        if cat is None:
            cat = Catalog()

        ev = Event()
        if description:
            ev.comments.append(Comment(text=description))
        if origin:
            try:
                ev.origins.append(Origin(
                    time=UTCDateTime(origin["origin_ts"]),
                    latitude=origin["lat"], longitude=origin["lon"],
                    depth=float(origin.get("depth_km", 0.0)) * 1000.0))
            except Exception:  # noqa: BLE001
                pass
        loc_code = "" if loc in ("--", "*") else (loc or "")
        b = (band or "BH")[:2].upper()
        for phase, ts in picks.items():
            cha = f"{b}Z" if phase == "P" else f"{b}N"
            ev.picks.append(Pick(
                time=UTCDateTime(float(ts)), phase_hint=phase,
                waveform_id=WaveformStreamID(
                    network_code=net, station_code=sta,
                    location_code=loc_code, channel_code=cha)))
        cat.append(ev)

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            cat.write(str(self._path), format="QUAKEML")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("CatalogStore: no se pudo escribir (%s)", exc)
            return False

    def list_events(self) -> list:
        """Lista ``[{time, station, n_picks, desc}]`` (recientes primero)."""

        try:
            from obspy import read_events
        except Exception:  # noqa: BLE001
            return []
        if not self._path.exists():
            return []
        try:
            cat = read_events(str(self._path))
        except Exception:  # noqa: BLE001
            return []
        out: list = []
        for idx, ev in enumerate(cat):
            if ev.origins:
                t0 = float(ev.origins[0].time.timestamp)
            elif ev.picks:
                t0 = float(ev.picks[0].time.timestamp)
            else:
                t0 = 0.0
            wid = ev.picks[0].waveform_id if ev.picks else None
            sta = (f"{wid.network_code}.{wid.station_code}"
                   if wid is not None else "—")
            desc = ev.comments[0].text if ev.comments else ""
            out.append({"time": t0, "station": sta, "n_picks": len(ev.picks),
                        "desc": desc, "idx": idx})    # idx = posición original
        out.sort(key=lambda d: d["time"], reverse=True)
        return out

    def get_event(self, idx: int) -> Optional[dict]:
        """Devuelve el detalle completo del evento ``idx`` para reabrirlo.

        ``{net, sta, loc, band, picks:{fase:ts}, origin|None, desc}`` o ``None``
        si no existe / ObsPy no está. ``idx`` es la posición ORIGINAL en el
        fichero (la que entrega ``list_events`` en la clave ``idx``).
        """

        try:
            from obspy import read_events
        except Exception:  # noqa: BLE001
            return None
        if not self._path.exists():
            return None
        try:
            cat = read_events(str(self._path))
        except Exception:  # noqa: BLE001
            return None
        if not (0 <= idx < len(cat.events)):
            return None
        ev = cat.events[idx]
        if not ev.picks:
            return None
        wid = ev.picks[0].waveform_id
        cha = (wid.channel_code or "BHZ")
        band = cha[:2].upper() if len(cha) >= 2 else "BH"
        picks: dict = {}
        for p in ev.picks:
            phase = (p.phase_hint or "").upper() or "P"
            picks[phase] = float(p.time.timestamp)
        origin = None
        if ev.origins:
            o = ev.origins[0]
            try:
                origin = {
                    "lat": float(o.latitude), "lon": float(o.longitude),
                    "depth_km": float(o.depth or 0.0) / 1000.0,
                    "origin_ts": float(o.time.timestamp),
                }
            except Exception:  # noqa: BLE001
                origin = None
        return {
            "net": wid.network_code or "", "sta": wid.station_code or "",
            "loc": wid.location_code or "", "band": band,
            "picks": picks, "origin": origin,
            "desc": ev.comments[0].text if ev.comments else "",
        }

    def remove_event(self, idx: int) -> bool:
        """Elimina el evento en la posición ``idx`` (la de ``list_events``)."""

        try:
            from obspy import read_events
        except Exception:  # noqa: BLE001
            return False
        if not self._path.exists():
            return False
        try:
            cat = read_events(str(self._path))
            if not (0 <= idx < len(cat.events)):
                return False
            del cat.events[idx]
            cat.write(str(self._path), format="QUAKEML")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("CatalogStore: no se pudo eliminar (%s)", exc)
            return False
