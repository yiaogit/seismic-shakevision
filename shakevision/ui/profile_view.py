"""
ProfileView — página personal del usuario (v0.5 阶段 L).

Consume tres fuentes:
  * ``UsageTracker``        — métricas locales (lanzamientos, tiempo,
                              clicks, audio…).
  * ``FavoritesStore``      — listas de estaciones y eventos favoritos.
  * ``GitHubAuthService``   — identidad: nombre, @login y avatar URL.

Layout (de arriba a abajo)
--------------------------
  ┌─────────────────────────────────────────────────────────────┐
  │ Identity Card                                               │
  │  [avatar 64×64]  Yiao            ★ Sign in / Logout         │
  │                  @yiaogit · Member since 2026-03-12         │
  ├─────────────────────────────────────────────────────────────┤
  │ Stats grid (3 × 2 tarjetas)                                 │
  │  [Launches]  [Time in app]  [Earthquakes viewed]            │
  │  [Stations]  [Audio listened]  [Reports generated]          │
  ├─────────────────────────────────────────────────────────────┤
  │ Favorites (2 columnas)                                      │
  │  Favorite stations              Favorite events             │
  │   • AM.R0E05 (Madrid)  ✕         • M5.4 Tokio  ✕            │
  │   • IU.ANMO (Albuquerque) ✕      • M6.2 Santiago ✕          │
  └─────────────────────────────────────────────────────────────┘

Refresh
-------
  * showEvent: re-leemos UsageTracker.stats() + GitHubAuthService.
  * FavoritesStore.changed_signal: re-render incremental de las listas.
  * LocaleService.language_changed_signal: re-traduce labels.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.services.activity_log import (
    ActivityLog,
    format_relative_time,
)
from shakevision.services.github_auth import GitHubAuthService
from shakevision.services.usage_tracker import UsageTracker
from shakevision.ui.icons import get_icon
from shakevision.ui.theme_manager import ThemeManager


logger = logging.getLogger(__name__)


# ============================================================
# Helpers de formateo (sin Qt — fáciles de testear)
# ============================================================
def format_duration_seconds(total_seconds: int) -> str:
    """Convierte segundos a "5h 23m" / "12m 4s" / "8s".

    Usamos español/inglés-friendly suffixes que no necesitan traducción
    por separado (h, m, s son universales). Si la UI quiere algo más
    elaborado puede ignorar este helper.
    """

    total = max(0, int(total_seconds))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        m, s = divmod(total, 60)
        return f"{m}m {s:02d}s"
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m:02d}m"


def format_iso_short(iso: str) -> str:
    """ISO 8601 → 'YYYY-MM-DD' (más legible en cards)."""

    if not iso:
        return "—"
    try:
        return iso[:10]
    except Exception:  # noqa: BLE001
        return iso


def format_member_since(first_launch_iso: str) -> str:
    """Devuelve "Member since 2026-03-12" o "—" si vacío."""

    return format_iso_short(first_launch_iso)


# ============================================================
# Stat card mini-widget
# ============================================================
class _StatCard(QFrame):
    """Tarjeta visual para una métrica: valor grande + label pequeña."""

    def __init__(self, value: str, label: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProfileStatCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # v0.6: sombra subtil estilo macOS sheet — solo se nota en
        # tema claro, en oscuro la dejamos para coherencia (el alpha
        # bajo la hace casi invisible sobre fondo oscuro).
        from shakevision.ui.elevation import elevation_1
        elevation_1(self)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(4)
        self._value_label = QLabel(value)
        f = QFont()
        f.setPointSize(20)
        f.setBold(True)
        self._value_label.setFont(f)
        self._value_label.setObjectName("ProfileStatValue")
        self._label_label = QLabel(label)
        self._label_label.setObjectName("ProfileStatLabel")
        self._label_label.setWordWrap(True)
        v.addWidget(self._value_label)
        v.addWidget(self._label_label)

    def update_value(self, value: str) -> None:
        self._value_label.setText(value)

    def update_label(self, label: str) -> None:
        self._label_label.setText(label)


# ============================================================
# ProfileView
# ============================================================
class ProfileView(QFrame):
    """Página de perfil personal."""

    # Pedimos al MainWindow que abra el diálogo de login GitHub.
    request_github_login = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProfileView")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(self._build_qss())

        # Avatar QNetworkAccessManager — para descargar GitHub avatars
        # de forma asíncrona sin bloquear UI. None hasta que haga falta.
        self._net_mgr: Optional[QNetworkAccessManager] = None

        root_scroll = QScrollArea(self)
        root_scroll.setWidgetResizable(True)
        root_scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root_scroll)

        content = QWidget()
        root_scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(18)

        v.addWidget(self._build_identity_card())
        v.addWidget(self._build_stats_section())
        v.addWidget(self._build_activity_section(), stretch=1)

        # Re-render al insertarse nueva actividad en cualquier parte
        # de la app (record_launch, record_report_generated, etc.).
        try:
            ActivityLog.changed_signal().connect(
                lambda _entry: self._refresh_activity())
        except Exception:  # noqa: BLE001
            pass
        # Re-traducir labels al cambiar idioma
        try:
            LocaleService.language_changed_signal().connect(
                lambda _l: self.refresh_all())
        except Exception:  # noqa: BLE001
            pass
        # v0.6 Phase 14-fix — re-aplicar QSS al cambiar tema. Sin esto el
        # diálogo (que es lazy + persistente) se queda con las constantes
        # COLOR_PANEL / COLOR_TEXT_* del tema con el que se construyó.
        # Resultado visible: cards blancos sobre fondo oscuro porque
        # COLOR_PANEL se "congeló" en light durante el primer abrir.
        try:
            ThemeManager.changed_signal().connect(
                lambda _t: self._refresh_themed_qss())
        except Exception:  # noqa: BLE001
            pass

        self.refresh_all()

    def _refresh_themed_qss(self) -> None:
        """Re-construye y aplica QSS con los COLOR_* actuales del módulo
        theme. Llamado por ``ThemeManager.changed_signal`` y por
        ``showEvent`` (belt-and-suspenders por si el diálogo se abrió
        antes de que el tema activo se estabilizara).
        """

        try:
            self.setStyleSheet(self._build_qss())
            # Forzar re-poll de polish para que QLabels hijos re-evalúen
            # la cascada de stylesheets.
            self.style().unpolish(self)
            self.style().polish(self)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Construcción de secciones
    # ------------------------------------------------------------------
    def _build_identity_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("ProfileIdentityCard")
        h = QHBoxLayout(card)
        h.setContentsMargins(20, 16, 20, 16)
        h.setSpacing(16)

        self._avatar_label = QLabel()
        self._avatar_label.setObjectName("ProfileAvatar")
        self._avatar_label.setFixedSize(72, 72)
        self._avatar_label.setAlignment(Qt.AlignCenter)
        self._render_placeholder_avatar()
        h.addWidget(self._avatar_label)

        info = QVBoxLayout()
        info.setSpacing(4)
        self._name_label = QLabel("…")
        nf = QFont()
        nf.setPointSize(16)
        nf.setBold(True)
        self._name_label.setFont(nf)
        self._name_label.setObjectName("ProfileName")
        self._handle_label = QLabel("")
        self._handle_label.setObjectName("ProfileHandle")
        self._member_label = QLabel("")
        self._member_label.setObjectName("ProfileMember")
        # v0.7.4: bio + ubicación + counts cuando hay sesión GitHub.
        # Si no hay login, estos labels quedan vacíos y collapsean.
        self._bio_label = QLabel("")
        self._bio_label.setObjectName("ProfileBio")
        self._bio_label.setWordWrap(True)
        self._location_label = QLabel("")
        self._location_label.setObjectName("ProfileLocation")
        self._counts_label = QLabel("")
        self._counts_label.setObjectName("ProfileCounts")
        info.addWidget(self._name_label)
        info.addWidget(self._handle_label)
        info.addWidget(self._member_label)
        info.addWidget(self._bio_label)
        info.addWidget(self._location_label)
        info.addWidget(self._counts_label)
        h.addLayout(info, stretch=1)

        # Botón principal (Sign in / Logout según estado)
        self._auth_button = QPushButton()
        self._auth_button.setObjectName("ProfileAuthButton")
        self._auth_button.clicked.connect(self._on_auth_button_clicked)
        h.addWidget(self._auth_button, alignment=Qt.AlignTop)

        return card

    def _build_stats_section(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("ProfileStatsWrap")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self._stats_title = QLabel()
        sf = QFont()
        sf.setPointSize(13)
        sf.setBold(True)
        self._stats_title.setFont(sf)
        self._stats_title.setObjectName("ProfileSectionTitle")
        v.addWidget(self._stats_title)

        grid = QGridLayout()
        grid.setSpacing(10)
        # 6 cards en 3×2
        self._card_launches      = _StatCard("0", "")
        self._card_session_time  = _StatCard("0s", "")
        self._card_quakes_viewed = _StatCard("0", "")
        self._card_stations      = _StatCard("0", "")
        self._card_audio_seconds = _StatCard("0s", "")
        self._card_reports       = _StatCard("0", "")
        grid.addWidget(self._card_launches,      0, 0)
        grid.addWidget(self._card_session_time,  0, 1)
        grid.addWidget(self._card_quakes_viewed, 0, 2)
        grid.addWidget(self._card_stations,      1, 0)
        grid.addWidget(self._card_audio_seconds, 1, 1)
        grid.addWidget(self._card_reports,       1, 2)
        v.addLayout(grid)
        return wrap

    def _build_activity_section(self) -> QWidget:
        """v0.7-A: línea de tiempo de actividad reciente.

        Reemplaza la sección anterior de "Favoritos" (que dependía del
        right-click hit-test del globo, postponed en task #215).
        Aquí mostramos las últimas 10 entradas de ``ActivityLog`` con
        un timestamp relativo a la izquierda y una descripción
        traducida a la derecha.
        """

        wrap = QFrame()
        wrap.setObjectName("ProfileActivityWrap")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self._activity_title = QLabel()
        ff = QFont()
        ff.setPointSize(13)
        ff.setBold(True)
        self._activity_title.setFont(ff)
        self._activity_title.setObjectName("ProfileSectionTitle")
        v.addWidget(self._activity_title)

        self._activity_hint = QLabel()
        self._activity_hint.setObjectName("ProfileActivityHint")
        self._activity_hint.setWordWrap(True)
        v.addWidget(self._activity_hint)

        self._activity_list = QListWidget()
        self._activity_list.setObjectName("ProfileActivityList")
        # Sin foco/selección — esto es solo lectura.
        self._activity_list.setSelectionMode(QListWidget.NoSelection)
        self._activity_list.setFocusPolicy(Qt.NoFocus)
        v.addWidget(self._activity_list, stretch=1)

        return wrap

    # ------------------------------------------------------------------
    # Refresco de datos
    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        """Reconsulta TODAS las fuentes y re-pinta. Idempotente."""

        self._refresh_identity()
        self._refresh_stats()
        self._refresh_activity()
        self._retranslate_static_labels()

    def _retranslate_static_labels(self) -> None:
        self._stats_title.setText(t("profile.stats.title"))
        if hasattr(self, "_activity_title"):
            self._activity_title.setText(t("profile.activity.title"))
        if hasattr(self, "_activity_hint"):
            self._activity_hint.setText(t("profile.activity.hint"))
        # Stat card labels
        self._card_launches.update_label(t("profile.stat.launches"))
        self._card_session_time.update_label(t("profile.stat.session_time"))
        self._card_quakes_viewed.update_label(
            t("profile.stat.quakes_viewed"))
        self._card_stations.update_label(t("profile.stat.stations_clicked"))
        self._card_audio_seconds.update_label(t("profile.stat.audio_listened"))
        self._card_reports.update_label(t("profile.stat.reports_generated"))

    def _refresh_identity(self) -> None:
        if GitHubAuthService.is_authenticated():
            user = GitHubAuthService.current_user()
            login = user.get("login", "?")
            name = user.get("name") or login
            avatar_url = user.get("avatar_url", "")
            self._name_label.setText(name)
            self._handle_label.setText(f"@{login}")
            self._auth_button.setText(t("profile.btn.logout"))
            if avatar_url:
                self._fetch_avatar(avatar_url)
            # v0.7.4 — extended GitHub info
            bio = (user.get("bio") or "").strip()
            self._bio_label.setText(bio)
            self._bio_label.setVisible(bool(bio))
            location = (user.get("location") or "").strip()
            company = (user.get("company") or "").strip()
            loc_parts = [p for p in (location, company) if p]
            self._location_label.setText(
                "📍 " + " · ".join(loc_parts) if loc_parts else "")
            self._location_label.setVisible(bool(loc_parts))
            repos = int(user.get("public_repos") or 0)
            followers = int(user.get("followers") or 0)
            following = int(user.get("following") or 0)
            self._counts_label.setText(
                t("profile.github.counts",
                  repos=repos, followers=followers, following=following))
            self._counts_label.setVisible(True)
        else:
            self._name_label.setText(t("profile.guest_name"))
            self._handle_label.setText(t("profile.guest_handle"))
            self._auth_button.setText(t("profile.btn.sign_in"))
            self._render_placeholder_avatar()
            # Collapsear los extras cuando no hay sesión
            self._bio_label.setText("")
            self._bio_label.setVisible(False)
            self._location_label.setText("")
            self._location_label.setVisible(False)
            self._counts_label.setText("")
            self._counts_label.setVisible(False)

        # Member since (independiente del login GitHub)
        stats = UsageTracker.stats()
        first_iso = stats.get("first_launch_iso", "")
        self._member_label.setText(
            t("profile.member_since",
              date=format_member_since(first_iso))
        )

    def _refresh_stats(self) -> None:
        s = UsageTracker.stats()
        self._card_launches.update_value(str(s["launch_count"]))
        self._card_session_time.update_value(
            format_duration_seconds(s["session_seconds"]))
        self._card_quakes_viewed.update_value(
            str(s["earthquakes_viewed_count"]))
        self._card_stations.update_value(
            str(s["stations_clicked_count"]))
        self._card_audio_seconds.update_value(
            format_duration_seconds(s["audio_played_seconds"]))
        self._card_reports.update_value(str(s["reports_generated_count"]))

    def _refresh_activity(self) -> None:
        """Repinta la línea de tiempo con los últimos 10 eventos."""

        if not hasattr(self, "_activity_list"):
            return
        self._activity_list.clear()
        entries = ActivityLog.list_recent(limit=10)
        if not entries:
            empty = QListWidgetItem(t("profile.activity.empty"))
            empty.setFlags(empty.flags() & ~Qt.ItemIsSelectable)
            self._activity_list.addItem(empty)
            return
        for entry in entries:
            label = self._format_activity(entry)
            self._activity_list.addItem(QListWidgetItem(label))

    @staticmethod
    def _format_activity(entry: dict) -> str:
        """Formatea una entrada de ActivityLog para QListWidgetItem.

        Pattern: ``[relative_time]  ·  <descripción i18n>``
        """

        ts = int(entry.get("ts", 0))
        kind = str(entry.get("kind", ""))
        params = entry.get("params", {}) or {}
        rel = format_relative_time(ts)
        # i18n key por kind. Si falta, mostramos el kind crudo.
        i18n_key = f"activity.{kind}"
        try:
            desc = t(i18n_key, **{str(k): str(v) for k, v in params.items()})
        except Exception:  # noqa: BLE001
            desc = kind
        # Si la traducción no existe, t() devuelve la propia key
        # → caer al kind crudo para no mostrar "activity.foo".
        if desc.startswith("activity."):
            desc = kind
        return f"{rel:>4}  ·  {desc}"

    # ------------------------------------------------------------------
    # Avatar (descarga asíncrona)
    # ------------------------------------------------------------------
    def _ensure_net_mgr(self) -> QNetworkAccessManager:
        if self._net_mgr is None:
            self._net_mgr = QNetworkAccessManager(self)
        return self._net_mgr

    def _fetch_avatar(self, url: str) -> None:
        try:
            from PySide6.QtCore import QUrl
            mgr = self._ensure_net_mgr()
            req = QNetworkRequest(QUrl(url))
            reply = mgr.get(req)
            reply.finished.connect(lambda: self._on_avatar_loaded(reply))
        except Exception as exc:  # noqa: BLE001
            logger.debug("ProfileView: avatar fetch fallo (%s)", exc)
            self._render_placeholder_avatar()

    def _on_avatar_loaded(self, reply) -> None:
        try:
            data = bytes(reply.readAll())
            if not data:
                return
            pm = QPixmap()
            if not pm.loadFromData(data):
                return
            scaled = pm.scaled(72, 72, Qt.KeepAspectRatioByExpanding,
                               Qt.SmoothTransformation)
            # v0.5 阶段 N: máscara circular para que el avatar se vea
            # como en GitHub / Slack / Discord. Sin esto se ve cuadrado
            # y resta calidad visual a la tarjeta de identidad.
            circular = self._make_circular_pixmap(scaled, 72)
            self._avatar_label.setPixmap(circular)
        finally:
            reply.deleteLater()

    @staticmethod
    def _make_circular_pixmap(src: QPixmap, size: int) -> QPixmap:
        """Recorta ``src`` a un círculo de ``size``×``size`` con AA suave.

        Usamos QPainterPath.addEllipse + setClipPath para evitar bordes
        pixelados. El antialiasing está activo por defecto en QPainter
        después de setRenderHint.
        """

        result = QPixmap(size, size)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        path = QPainterPath()
        path.addEllipse(0.0, 0.0, float(size), float(size))
        painter.setClipPath(path)
        # Centrar el pixmap original (puede ser más grande tras
        # KeepAspectRatioByExpanding)
        x = (size - src.width()) // 2
        y = (size - src.height()) // 2
        painter.drawPixmap(x, y, src)
        painter.end()
        return result

    def _render_placeholder_avatar(self) -> None:
        """Pone el icono "user" recoloreado según el tema dentro de un
        círculo accent suave — coherente visualmente con el avatar real."""

        try:
            theme = ThemeManager.current_theme()
        except Exception:  # noqa: BLE001
            theme = "dark"
        icon = get_icon("user", theme=theme, size=64)
        if icon.isNull():
            self._avatar_label.setText("?")
            return

        # Construir un pixmap circular de fondo + el icono encima.
        size = 72
        bg = QPixmap(size, size)
        bg.fill(Qt.transparent)
        painter = QPainter(bg)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Disco de fondo con accent suavísimo
        path = QPainterPath()
        path.addEllipse(0.0, 0.0, float(size), float(size))
        painter.fillPath(path, QBrush(Qt.GlobalColor.transparent))
        # Pintar el icono centrado a ~60% del círculo
        inner = 44
        offset = (size - inner) // 2
        painter.drawPixmap(offset, offset, icon.pixmap(inner, inner))
        painter.end()
        self._avatar_label.setPixmap(bg)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _on_auth_button_clicked(self) -> None:
        if GitHubAuthService.is_authenticated():
            GitHubAuthService.logout()
            self._refresh_identity()
            return
        # No logueado: pedir al MainWindow que abra el diálogo
        # (mantenemos el dialog desacoplado de esta página para que
        # las suscripciones a `logged_in` puedan vivir en MainWindow).
        self.request_github_login.emit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        # Stats pueden cambiar con cada interacción; al volver a la
        # página del perfil mejor re-leer todo.
        self.refresh_all()
        # v0.6 Phase 14-fix — re-aplicar QSS por si el tema cambió
        # mientras el diálogo estaba oculto.
        self._refresh_themed_qss()

    # ------------------------------------------------------------------
    # QSS
    # ------------------------------------------------------------------
    @staticmethod
    def _build_qss() -> str:
        """v0.6: QSS dinámico desde theme module — funciona en claro y
        oscuro. Antes usaba rgba hardcoded que solo se veía bien en
        modo oscuro y daba tarjetas casi invisibles en modo claro.
        """

        from shakevision.ui import theme as _t
        return f"""
        QFrame#ProfileView {{
            background-color: {_t.COLOR_BACKGROUND};
        }}
        QFrame#ProfileIdentityCard,
        QFrame#ProfileStatsWrap,
        QFrame#ProfileActivityWrap {{
            background-color: {_t.COLOR_PANEL};
            border: 1px solid {_t.COLOR_PANEL_BORDER};
            border-radius: 12px;
        }}
        QFrame#ProfileStatCard {{
            background-color: {_t.COLOR_PANEL_ELEVATED};
            border: 1px solid {_t.COLOR_PANEL_BORDER};
            border-radius: 10px;
        }}
        QFrame#ProfileIdentityCard QLabel,
        QFrame#ProfileStatsWrap QLabel,
        QFrame#ProfileActivityWrap QLabel,
        QFrame#ProfileStatCard QLabel,
        QLabel#ProfileActivityHint,
        QLabel#ProfileSectionTitle,
        QLabel#ProfileName,
        QLabel#ProfileHandle,
        QLabel#ProfileMember,
        QLabel#ProfileBio,
        QLabel#ProfileLocation,
        QLabel#ProfileCounts,
        QLabel#ProfileStatValue,
        QLabel#ProfileStatLabel {{
            background: transparent;
        }}
        QLabel#ProfileBio {{
            color: {_t.COLOR_TEXT_PRIMARY};
            font-size: 12px;
            padding: 4px 0 2px 0;
        }}
        QLabel#ProfileLocation,
        QLabel#ProfileCounts {{
            color: {_t.COLOR_TEXT_SECONDARY};
            font-size: 11px;
        }}
        QLabel#ProfileStatValue,
        QLabel#ProfileSectionTitle,
        QLabel#ProfileName {{
            color: {_t.COLOR_TEXT_PRIMARY};
        }}
        QLabel#ProfileStatLabel,
        QLabel#ProfileMember,
        QLabel#ProfileHandle,
        QLabel#ProfileActivityHint {{
            color: {_t.COLOR_TEXT_SECONDARY};
            font-size: 12px;
        }}
        QLabel#ProfileAvatar {{
            border-radius: 36px;
            background-color: {_t.COLOR_PANEL_ELEVATED};
        }}
        QPushButton#ProfileAuthButton {{
            background-color: {_t.COLOR_ACCENT};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 18px;
            font-weight: 600;
        }}
        QPushButton#ProfileAuthButton:hover {{
            background-color: {_t.COLOR_ACCENT_HOVER};
        }}
        QListWidget#ProfileActivityList {{
            background-color: transparent;
            border: none;
            color: {_t.COLOR_TEXT_PRIMARY};
            font-size: 12px;
        }}
        QListWidget#ProfileActivityList::item {{
            padding: 8px 10px;
            border-bottom: 1px solid {_t.COLOR_PANEL_DIVIDER};
        }}
        QListWidget#ProfileActivityList::item:last-child {{
            border-bottom: none;
        }}
        QScrollArea, QScrollArea > QWidget > QWidget {{
            background-color: {_t.COLOR_BACKGROUND};
            border: none;
        }}
        """
