"""
Asistente de incorporación (Onboarding wizard) — v0.5 阶段 H.

Se muestra **una sola vez** tras el splash + Localízame en el primer
arranque. Permite que el usuario configure rápidamente lo esencial
sin tener que ir a Ajustes:

  1. Bienvenida         — logo + tagline + nota de privacidad
  2. Idioma             — radio buttons en/es/zh/fr
  3. Zona horaria       — combo box (predeseleccionado el detectado)
  4. Tema               — auto / claro / oscuro (3 tarjetas radio)
  5. Modo de capa       — estándar / profesional (introduce el concepto)
  6. Listo              — resumen + botón "Empezar"

Diseño
------
* QDialog modal sin marco (frameless), centrado.
* QStackedWidget interno con un widget por paso.
* Footer común: «Atrás» / «Saltar» / «Siguiente» (Finalizar en el último).
* Esc → Saltar (equivale a aplicar valores por defecto y cerrar).
* Confirmar valor → aplicar inmediatamente al singleton correspondiente
  (LocaleService, TimezoneService, ThemeManager, LayerModeManager).
  Esto da feedback en vivo: cambiar el idioma re-traduce el propio
  wizard antes de avanzar.

Persistencia
------------
``QSettings("SeismicGuard"/"Onboarding"/"wizard/completed")`` = True
tras finalizar O saltar. ``has_been_completed()`` consulta la bandera.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.ui.icons import logo_pixmap
from shakevision.ui.signal_safety import subscribe


logger = logging.getLogger(__name__)


# ============================================================
# Persistencia
# ============================================================
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Onboarding"
_QSETTINGS_KEY_DONE: str = "wizard/completed"


def has_been_completed() -> bool:
    try:
        from PySide6.QtCore import QSettings
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        return bool(s.value(_QSETTINGS_KEY_DONE, False, type=bool))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Onboarding: leer QSettings falló (%s)", exc)
        return False


def mark_completed() -> None:
    try:
        from PySide6.QtCore import QSettings
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        s.setValue(_QSETTINGS_KEY_DONE, True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Onboarding: persistir falló (%s)", exc)


def _reset_for_tests() -> None:
    try:
        from PySide6.QtCore import QSettings
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        s.remove(_QSETTINGS_KEY_DONE)
    except Exception:  # noqa: BLE001
        pass


# ============================================================
# Constantes visuales
# ============================================================
WIZARD_WIDTH: int = 640
WIZARD_HEIGHT: int = 480

# Mapeo i18n del nombre de cada paso (para la "pildora" del footer).
STEP_KEYS: tuple[str, ...] = (
    "onboarding.step.welcome",
    "onboarding.step.language",
    "onboarding.step.timezone",
    "onboarding.step.theme",
    "onboarding.step.layer",
    "onboarding.step.done",
)


# ============================================================
# Wizard principal
# ============================================================
class OnboardingWizard(QDialog):
    """Asistente de incorporación de 6 pasos.

    Emite ``finished_setup`` al cerrarse, independientemente de si
    el usuario completó todos los pasos o pulsó "Saltar". El caller
    puede comprobar ``was_skipped`` para distinguir los casos.
    """

    finished_setup = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setObjectName("OnboardingWizard")
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setFixedSize(WIZARD_WIDTH, WIZARD_HEIGHT)
        self.setStyleSheet(self._build_qss())

        # Bandera para que el caller sepa cómo terminó.
        self.was_skipped: bool = False

        # ── Layout: header + stacked pages + footer ──
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        # Header: nombre del paso + indicador "Paso 2/6"
        self._step_label = QLabel("…")
        self._step_label.setObjectName("WizardStepLabel")
        self._counter_label = QLabel("")
        self._counter_label.setObjectName("WizardCounter")
        self._counter_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header = QHBoxLayout()
        header.addWidget(self._step_label, 1)
        header.addWidget(self._counter_label, 0)
        root.addLayout(header)

        # Stacked pages
        self._stack = QStackedWidget(self)
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._stack, 1)

        # v0.7.6 fix (defensivo): suscribirse al ``theme_changed`` ANTES
        # de construir las páginas. Si alguna página dispara
        # accidentalmente un set_mode durante init (p.ej. al hacer
        # setChecked en un radio button enganchado a toggled), el wizard
        # captura la señal y reaplica su propio QSS. Antes del fix esta
        # conexión vivía DESPUÉS de las páginas y se perdía la primera
        # emisión, dejando el wizard con QSS de un tema y MainWindow
        # con QSS del otro.
        # v0.7.7 (B1): subscribe() — disconnect en destroyed + guarda.
        from shakevision.ui.theme_manager import ThemeManager
        subscribe(self, ThemeManager.changed_signal(),
                  lambda _t: self.setStyleSheet(self._build_qss()))

        # ── Construcción de las 6 páginas ──
        self._stack.addWidget(self._build_welcome_page())
        self._stack.addWidget(self._build_language_page())
        self._stack.addWidget(self._build_timezone_page())
        self._stack.addWidget(self._build_theme_page())
        self._stack.addWidget(self._build_layer_page())
        self._stack.addWidget(self._build_done_page())

        # Footer: Back · Skip ··· Next/Finish
        self._btn_back = QPushButton()
        self._btn_back.setObjectName("WizardSecondaryButton")
        self._btn_back.clicked.connect(self._on_back)
        self._btn_skip = QPushButton()
        self._btn_skip.setObjectName("WizardSecondaryButton")
        self._btn_skip.clicked.connect(self._on_skip)
        self._btn_next = QPushButton()
        self._btn_next.setObjectName("WizardPrimaryButton")
        self._btn_next.clicked.connect(self._on_next)
        footer = QHBoxLayout()
        footer.addWidget(self._btn_back)
        footer.addWidget(self._btn_skip)
        footer.addStretch(1)
        footer.addWidget(self._btn_next)
        root.addLayout(footer)

        # Aplicar i18n inicial + suscribirse a cambios (el wizard mismo
        # cambia idioma en vivo, así que necesita escuchar su propia
        # señal).
        self._retranslate()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

        # v0.7.6 fix: reaplicar QSS al final del __init__ por si la
        # construcción de las páginas disparó algún cambio de tema que
        # quedó pendiente — así garantizamos que el wizard refleja la
        # paleta ACTUAL antes de mostrarse al usuario, incluso si entre
        # setStyleSheet inicial (línea ~136) y este punto algo movió
        # los globals COLOR_*. (La suscripción a ``theme_changed`` ya
        # se hizo más arriba, antes de construir las páginas.)
        try:
            self.setStyleSheet(self._build_qss())
        except Exception:  # noqa: BLE001
            pass

        self._update_buttons_for_index(0)

        self._center_on_screen()

    # ------------------------------------------------------------------
    # Páginas (constructores)
    # ------------------------------------------------------------------
    def _build_welcome_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Logo grande centrado
        logo_label = QLabel()
        pm = logo_pixmap(theme="dark", width=320)
        if pm is not None and not pm.isNull():
            logo_label.setPixmap(pm)
        else:
            logo_label.setText("SeismicGuard")
            f = QFont("Inter Variable", 22, QFont.Weight.DemiBold)
            f.setStyleHint(QFont.StyleHint.SansSerif)
            logo_label.setFont(f)
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addSpacing(8)
        layout.addWidget(logo_label)

        self._welcome_tagline = QLabel()
        self._welcome_tagline.setObjectName("WizardBody")
        self._welcome_tagline.setAlignment(Qt.AlignCenter)
        self._welcome_tagline.setWordWrap(True)
        layout.addWidget(self._welcome_tagline)

        self._welcome_privacy = QLabel()
        self._welcome_privacy.setObjectName("WizardCaption")
        self._welcome_privacy.setAlignment(Qt.AlignCenter)
        self._welcome_privacy.setWordWrap(True)
        layout.addWidget(self._welcome_privacy)

        layout.addStretch(1)
        return page

    def _build_language_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._lang_heading = QLabel()
        self._lang_heading.setObjectName("WizardSectionTitle")
        layout.addWidget(self._lang_heading)
        self._lang_help = QLabel()
        self._lang_help.setObjectName("WizardBody")
        self._lang_help.setWordWrap(True)
        layout.addWidget(self._lang_help)

        # 4 radio buttons, uno por idioma. Aplican al instante para
        # ver el wizard re-traducirse en vivo.
        self._lang_group = QButtonGroup(self)
        self._lang_buttons: dict[str, QRadioButton] = {}
        for code in LocaleService.available_languages():
            btn = QRadioButton(LocaleService.label_for(code))
            btn.setObjectName("WizardRadio")
            btn.setProperty("lang", code)
            btn.toggled.connect(self._on_language_chosen)
            self._lang_group.addButton(btn)
            layout.addWidget(btn)
            self._lang_buttons[code] = btn
        # Pre-seleccionar el idioma actual
        cur = LocaleService.current_language()
        if cur in self._lang_buttons:
            self._lang_buttons[cur].setChecked(True)
        layout.addStretch(1)
        return page

    def _build_timezone_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._tz_heading = QLabel()
        self._tz_heading.setObjectName("WizardSectionTitle")
        layout.addWidget(self._tz_heading)
        self._tz_help = QLabel()
        self._tz_help.setObjectName("WizardBody")
        self._tz_help.setWordWrap(True)
        layout.addWidget(self._tz_help)

        # ComboBox con todas las IANA + el actual marcado.
        from shakevision.services.timezone_service import (
            TimezoneService,
            available_timezones,
        )
        self._tz_combo = QComboBox()
        self._tz_combo.setObjectName("WizardCombo")
        self._tz_combo.setEditable(True)   # permite type-to-search
        for tz in available_timezones():
            self._tz_combo.addItem(tz)
        current = TimezoneService.current_iana()
        idx = self._tz_combo.findText(current)
        if idx >= 0:
            self._tz_combo.setCurrentIndex(idx)
        self._tz_combo.currentTextChanged.connect(self._on_timezone_chosen)
        layout.addWidget(self._tz_combo)
        layout.addStretch(1)
        return page

    def _build_theme_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._theme_heading = QLabel()
        self._theme_heading.setObjectName("WizardSectionTitle")
        layout.addWidget(self._theme_heading)
        self._theme_help = QLabel()
        self._theme_help.setObjectName("WizardBody")
        self._theme_help.setWordWrap(True)
        layout.addWidget(self._theme_help)

        self._theme_group = QButtonGroup(self)
        self._theme_buttons: dict[str, QRadioButton] = {}
        # v0.7.4: solo light / dark (auto eliminado del wizard).
        # v0.7.6: auto también eliminado de ThemeManager — mode() y
        # current_theme() ya devuelven siempre uno de los dos.
        for mode in ("light", "dark"):
            btn = QRadioButton()
            btn.setObjectName("WizardRadio")
            btn.setProperty("theme_mode", mode)
            btn.toggled.connect(self._on_theme_chosen)
            self._theme_group.addButton(btn)
            layout.addWidget(btn)
            self._theme_buttons[mode] = btn
        # Pre-seleccionar el TEMA EFECTIVO actual.
        #
        # v0.7.6 fix: dos bugs antiguos arreglados aquí:
        #
        # 1) Antes leíamos ``ThemeManager.mode()`` que devuelve
        #    "auto"/"light"/"dark". Como "auto" no existe como botón
        #    (lo quitamos en v0.7.4), caía al fallback "dark".
        #    Resultado: si el usuario abría la app en franja diurna
        #    con mode=auto y efectivo=light, este código forzaba un
        #    cambio a "dark" — pero el listener de re-paint del
        #    wizard se conectaba DESPUÉS de construir las páginas, así
        #    que el wizard se quedaba con el QSS light original
        #    mientras MainWindow se reaplicaba a dark. Resultado
        #    visible: ventana principal oscura + wizard claro.
        #    Solución: leer ``current_theme()`` (que siempre devuelve
        #    "light" o "dark", nunca "auto") y marcar ese radio.
        #
        # 2) ``setChecked(True)`` emite ``toggled`` → dispara
        #    ``_on_theme_chosen`` → llama ``ThemeManager.set_mode(...)``.
        #    Aunque el modo no cambie de valor, en casos límite puede
        #    re-disparar repaints. Usamos ``blockSignals`` para que el
        #    estado inicial NO se considere "el usuario eligió tema" —
        #    es solo reflejar el estado actual del singleton.
        try:
            from shakevision.ui.theme_manager import ThemeManager
            cur = ThemeManager.current_theme()
            if cur not in self._theme_buttons:
                cur = "dark"
            btn = self._theme_buttons[cur]
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
        except Exception:  # noqa: BLE001
            btn = self._theme_buttons["dark"]
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
        layout.addStretch(1)
        return page

    def _build_layer_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._layer_heading = QLabel()
        self._layer_heading.setObjectName("WizardSectionTitle")
        layout.addWidget(self._layer_heading)
        self._layer_help = QLabel()
        self._layer_help.setObjectName("WizardBody")
        self._layer_help.setWordWrap(True)
        layout.addWidget(self._layer_help)

        self._layer_group = QButtonGroup(self)
        self._layer_buttons: dict[str, QRadioButton] = {}
        for mode in ("standard", "professional"):
            btn = QRadioButton()
            btn.setObjectName("WizardRadio")
            btn.setProperty("layer_mode", mode)
            btn.toggled.connect(self._on_layer_chosen)
            self._layer_group.addButton(btn)
            layout.addWidget(btn)
            self._layer_buttons[mode] = btn
        try:
            from shakevision.ui.layer_mode_manager import LayerModeManager
            cur = LayerModeManager.current_mode()
            if cur in self._layer_buttons:
                self._layer_buttons[cur].setChecked(True)
        except Exception:  # noqa: BLE001
            self._layer_buttons["standard"].setChecked(True)
        layout.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self._done_check = QLabel("✓")
        self._done_check.setObjectName("WizardDoneCheck")
        self._done_check.setAlignment(Qt.AlignCenter)
        layout.addSpacing(12)
        layout.addWidget(self._done_check)

        self._done_heading = QLabel()
        self._done_heading.setObjectName("WizardSectionTitle")
        self._done_heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._done_heading)

        self._done_body = QLabel()
        self._done_body.setObjectName("WizardBody")
        self._done_body.setAlignment(Qt.AlignCenter)
        self._done_body.setWordWrap(True)
        layout.addWidget(self._done_body)

        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Reactivos: aplicar selección al instante
    # ------------------------------------------------------------------
    def _on_language_chosen(self, checked: bool) -> None:
        if not checked:
            return
        btn = self.sender()
        if btn is None:
            return
        code = btn.property("lang")
        if isinstance(code, str):
            LocaleService.set_language(code)
            # _retranslate ya está enganchado al signal — no llamarlo aquí

    def _on_timezone_chosen(self, text: str) -> None:
        from shakevision.services.timezone_service import TimezoneService
        if text and text.strip():
            TimezoneService.set_timezone(text.strip())

    def _on_theme_chosen(self, checked: bool) -> None:
        if not checked:
            return
        btn = self.sender()
        if btn is None:
            return
        mode = btn.property("theme_mode")
        if isinstance(mode, str):
            try:
                from shakevision.ui.theme_manager import ThemeManager
                ThemeManager.set_mode(mode)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                logger.debug("Onboarding: theme apply falló (%s)", exc)

    def _on_layer_chosen(self, checked: bool) -> None:
        if not checked:
            return
        btn = self.sender()
        if btn is None:
            return
        mode = btn.property("layer_mode")
        if isinstance(mode, str):
            try:
                from shakevision.ui.layer_mode_manager import LayerModeManager
                LayerModeManager.set_mode(mode)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                logger.debug("Onboarding: layer apply falló (%s)", exc)

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------
    def _on_back(self) -> None:
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._update_buttons_for_index(idx - 1)

    def _on_skip(self) -> None:
        self.was_skipped = True
        self._finish()

    def _on_next(self) -> None:
        idx = self._stack.currentIndex()
        if idx >= self._stack.count() - 1:
            self._finish()
            return
        self._stack.setCurrentIndex(idx + 1)
        self._update_buttons_for_index(idx + 1)

    def _finish(self) -> None:
        mark_completed()
        self.finished_setup.emit()
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self._on_skip()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_next()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Re-traducción + estado de botones
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        # Header
        idx = self._stack.currentIndex() if hasattr(self, "_stack") else 0
        self._step_label.setText(t(STEP_KEYS[idx]))
        self._counter_label.setText(
            t("onboarding.counter", current=idx + 1, total=len(STEP_KEYS))
        )

        # Footer
        self._btn_back.setText(t("onboarding.btn.back"))
        self._btn_skip.setText(t("onboarding.btn.skip"))
        # El botón "siguiente" se llama "Empezar" en la última página
        if idx >= len(STEP_KEYS) - 1:
            self._btn_next.setText(t("onboarding.btn.finish"))
        else:
            self._btn_next.setText(t("onboarding.btn.next"))

        # Welcome
        if hasattr(self, "_welcome_tagline"):
            self._welcome_tagline.setText(t("onboarding.welcome.tagline"))
            self._welcome_privacy.setText(t("onboarding.welcome.privacy"))
        # Language
        if hasattr(self, "_lang_heading"):
            self._lang_heading.setText(t("onboarding.language.heading"))
            self._lang_help.setText(t("onboarding.language.help"))
        # Timezone
        if hasattr(self, "_tz_heading"):
            self._tz_heading.setText(t("onboarding.timezone.heading"))
            self._tz_help.setText(t("onboarding.timezone.help"))
        # Theme
        if hasattr(self, "_theme_heading"):
            self._theme_heading.setText(t("onboarding.theme.heading"))
            self._theme_help.setText(t("onboarding.theme.help"))
            # v0.7.4: "auto" eliminado del wizard.
            # v0.7.6: "auto" también eliminado del ThemeManager entero.
            self._theme_buttons["light"].setText(t("onboarding.theme.light"))
            self._theme_buttons["dark"].setText(t("onboarding.theme.dark"))
        # Layer
        if hasattr(self, "_layer_heading"):
            self._layer_heading.setText(t("onboarding.layer.heading"))
            self._layer_help.setText(t("onboarding.layer.help"))
            self._layer_buttons["standard"].setText(
                t("onboarding.layer.standard"))
            self._layer_buttons["professional"].setText(
                t("onboarding.layer.professional"))
        # Done
        if hasattr(self, "_done_heading"):
            self._done_heading.setText(t("onboarding.done.heading"))
            self._done_body.setText(t("onboarding.done.body"))

    def _update_buttons_for_index(self, idx: int) -> None:
        self._btn_back.setEnabled(idx > 0)
        # Skip visible en todas las páginas salvo la última (allí
        # "Empezar" es la acción evidente).
        is_last = (idx >= self._stack.count() - 1)
        self._btn_skip.setVisible(not is_last)
        # Texto del botón principal cambia en la última página
        if is_last:
            self._btn_next.setText(t("onboarding.btn.finish"))
        else:
            self._btn_next.setText(t("onboarding.btn.next"))
        # Header counter
        self._step_label.setText(t(STEP_KEYS[idx]))
        self._counter_label.setText(
            t("onboarding.counter", current=idx + 1, total=len(STEP_KEYS))
        )

        # v0.7.4: removida la auto-popup del QComboBox de timezone que
        # se añadió en v0.6 Phase 14. Causaba un bug en macOS donde el
        # popup salía solo al entrar a la página y luego el QComboBox
        # quedaba en un estado donde clicks posteriores NO volvían a
        # abrirlo. El usuario ya ve el placeholder con la zona detectada
        # y un focus visible es suficiente affordance.
        if idx == 2 and hasattr(self, "_tz_combo"):
            self._tz_combo.setFocus()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _center_on_screen(self) -> None:
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        x = geom.x() + (geom.width() - self.width()) // 2
        y = geom.y() + (geom.height() - self.height()) // 2
        self.move(x, y)

    def _build_qss(self) -> str:
        """v0.7.4: QSS dinámico que respeta el tema activo (light/dark).

        La versión anterior hardcoded paleta dark (`#0d1226`, `#fafafa`)
        — al cambiar a tema claro, el fondo seguía siendo navy oscuro
        pero los labels se renderizaban en colores que daban contraste
        nulo (texto blanco sobre fondo blanco después de algunos
        repaints). Ahora leemos COLOR_* del módulo theme en cada
        invocación, igual que SettingsDialog y ProfileDialog.
        """

        from shakevision.ui import theme as _t
        # Borde sutil: igual que macOS sheet — 1 px del color de border
        # del panel actual (oscuro en dark, gris claro en light).
        return f"""
        QDialog#OnboardingWizard {{
            background-color: {_t.COLOR_BACKGROUND};
            border: 1px solid {_t.COLOR_PANEL_BORDER};
            border-radius: 16px;
        }}
        QFrame, QWidget#OnboardingWizard QStackedWidget {{
            background-color: transparent;
        }}
        QLabel#WizardStepLabel {{
            color: {_t.COLOR_TEXT_PRIMARY};
            font-family: 'Inter Variable', sans-serif;
            font-size: 16px;
            font-weight: 600;
        }}
        QLabel#WizardCounter {{
            color: {_t.COLOR_TEXT_MUTED};
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
        }}
        QLabel#WizardSectionTitle {{
            color: {_t.COLOR_TEXT_PRIMARY};
            font-family: 'Inter Variable', sans-serif;
            font-size: 18px;
            font-weight: 600;
        }}
        QLabel#WizardBody {{
            color: {_t.COLOR_TEXT_SECONDARY};
            font-family: 'Inter Variable', sans-serif;
            font-size: 13px;
            line-height: 1.4;
        }}
        QLabel#WizardCaption {{
            color: {_t.COLOR_TEXT_MUTED};
            font-family: 'Inter Variable', sans-serif;
            font-size: 11px;
        }}
        QRadioButton#WizardRadio {{
            color: {_t.COLOR_TEXT_PRIMARY};
            background: transparent;
            font-family: 'Inter Variable', sans-serif;
            font-size: 13px;
            padding: 6px 4px;
            spacing: 10px;
        }}
        QComboBox#WizardCombo {{
            background: {_t.COLOR_PANEL};
            border: 1px solid {_t.COLOR_PANEL_BORDER};
            color: {_t.COLOR_TEXT_PRIMARY};
            padding: 6px 26px 6px 10px;   /* right padding for arrow */
            border-radius: 6px;
            min-height: 28px;
        }}
        /* v0.7.4 patch #4: explicit drop-down + arrow region so
           Windows doesn't silently hide the click target when the
           wizard's local QSS overrides the global combo styling.
           subcontrol-origin: padding + position: right keeps the
           arrow inside the right padding zone we reserved above. */
        QComboBox#WizardCombo::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border: 0;
            background: transparent;
        }}
        QComboBox#WizardCombo::down-arrow {{
            image: none;       /* drop the (possibly missing) PNG */
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {_t.COLOR_TEXT_SECONDARY};
            margin-right: 8px;
            margin-top: 14px;
        }}
        QComboBox#WizardCombo QAbstractItemView {{
            background: {_t.COLOR_PANEL};
            color: {_t.COLOR_TEXT_PRIMARY};
            border: 1px solid {_t.COLOR_PANEL_BORDER};
            selection-background-color: {_t.COLOR_ACCENT};
            selection-color: white;
            outline: 0;
        }}
        QPushButton#WizardPrimaryButton {{
            background: {_t.COLOR_ACCENT};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 18px;
            font-weight: 600;
            font-family: 'Inter Variable', sans-serif;
            font-size: 13px;
            min-width: 100px;
        }}
        QPushButton#WizardPrimaryButton:hover {{ background: {_t.COLOR_ACCENT_HOVER}; }}
        QPushButton#WizardSecondaryButton {{
            background: transparent;
            color: {_t.COLOR_TEXT_SECONDARY};
            border: 1px solid {_t.COLOR_PANEL_BORDER};
            border-radius: 8px;
            padding: 8px 14px;
            font-family: 'Inter Variable', sans-serif;
            font-size: 12px;
            min-width: 80px;
        }}
        QPushButton#WizardSecondaryButton:hover {{
            color: {_t.COLOR_TEXT_PRIMARY};
            border-color: {_t.COLOR_ACCENT};
        }}
        QPushButton#WizardSecondaryButton:disabled {{
            color: {_t.COLOR_TEXT_MUTED};
            border-color: {_t.COLOR_PANEL_DIVIDER};
        }}
        QLabel#WizardDoneCheck {{
            color: {_t.COLOR_OK};
            font-size: 64px;
            font-weight: 600;
        }}
        """
