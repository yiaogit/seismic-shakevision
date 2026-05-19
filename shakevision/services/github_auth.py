"""
``GitHubAuthService`` — autenticación GitHub vía Device Flow (v0.5 阶段 K).

¿Por qué Device Flow?
---------------------
Es el flujo OAuth pensado para **aplicaciones de escritorio sin
servidor backend** — exactamente nuestro caso. El usuario obtiene
un código corto en la app, lo introduce en
https://github.com/login/device, y SeismicGuard recibe el token
directamente sin necesidad de un redirect URI ni de un secreto
de cliente (los "secret" del Web Application Flow no servirían
en una app open source: cualquiera podría extraerlos del binario).

Pipeline del Device Flow
------------------------
1. ``POST https://github.com/login/device/code`` con
   ``client_id=<público>`` y ``scope=read:user user:email`` →
   devuelve ``device_code`` (privado), ``user_code`` (mostrado al
   usuario, p.ej. "WDJB-MJHT"), ``verification_uri``, ``interval``
   y ``expires_in``.
2. La UI muestra ``user_code`` en grande + botón "Abrir GitHub" que
   abre ``verification_uri`` con ``QDesktopServices.openUrl``.
3. La app hace **polling** cada ``interval`` segundos a
   ``POST https://github.com/login/oauth/access_token`` con
   ``device_code``. Errores ``authorization_pending`` se ignoran;
   ``slow_down`` aumenta el intervalo; ``expired_token`` aborta;
   éxito devuelve ``access_token``.
4. Llamada final a ``GET https://api.github.com/user`` para obtener
   ``login``, ``avatar_url``, ``name``, ``email`` (si scope lo permite).

Configuración del client_id
---------------------------
El ``client_id`` es PÚBLICO (Device Flow no usa secret). Lo cargamos:

1. ``$SEISMICGUARD_GITHUB_CLIENT_ID`` — variable de entorno (CI/dev).
2. ``QSettings "SeismicGuard"/"GitHub"/"github/client_id"`` —
   permite que el mantenedor lo configure desde Ajustes sin recompilar.

Si ninguno está definido, ``is_configured()`` devuelve False y la UI
muestra un mensaje "GitHub login no configurado" en lugar del flujo.
Esto es indispensable para que SeismicGuard funcione en distribuciones
de terceros / forks que aún no han registrado su propia OAuth App.

Privacidad
----------
* **Cero red por defecto.** Si el usuario no entra al diálogo de
  login, jamás hacemos un solo request a GitHub.
* El ``access_token`` se persiste en ``QSettings``. Esto NO es
  cifrado — un atacante con acceso al perfil del usuario podría
  leerlo. Para v0.6 está pendiente migrar a ``keyring`` (sistema de
  llaveros nativo); por ahora documentamos la limitación al usuario.
* El usuario puede cerrar sesión en cualquier momento con
  ``logout()`` que borra token y caché de perfil.

API
---
    info = GitHubAuthService.start_device_flow()           # POST /device/code
    # mostrar info.user_code al usuario + abrir verification_uri
    token = GitHubAuthService.poll_for_token(info)         # bloquea hasta auth
    user = GitHubAuthService.fetch_user_profile(token)     # GET /user
    GitHubAuthService.save_token(token)
    GitHubAuthService.save_profile(user)
    # …más tarde:
    if GitHubAuthService.is_authenticated():
        u = GitHubAuthService.current_user()    # dict cacheado
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional


logger = logging.getLogger(__name__)


# ============================================================
# Endpoints + scopes
# ============================================================
DEVICE_CODE_URL: str = "https://github.com/login/device/code"
ACCESS_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
USER_API_URL: str = "https://api.github.com/user"

DEFAULT_SCOPE: str = "read:user user:email"

# v0.7.4 patch — client_id por defecto baked-in.
#
# Este es el Client ID PÚBLICO de la OAuth App "SeismicGuard-shakevision"
# registrada por el maintainer (yiaogit) con Device Flow habilitado.
# NO es un secreto — los Client IDs OAuth son públicos por diseño;
# lo que NO se puede compartir es el Client Secret (que Device Flow
# no usa, justamente por esto).
#
# Si más adelante el maintainer cambia/regenera la OAuth App, solo
# hay que actualizar esta constante y recompilar — los usuarios pueden
# además sobrescribirla con la env var SEISMICGUARD_GITHUB_CLIENT_ID
# o desde Ajustes (QSettings "github/client_id").
DEFAULT_CLIENT_ID: str = "Ov23liBIJOgeeGVfFW9B"

# Polling: respetamos el ``interval`` que devuelva GitHub. Si no llega,
# usamos 5 s por defecto. ``slow_down`` añade 5 s al actual.
DEFAULT_POLL_INTERVAL_S: int = 5
SLOW_DOWN_INCREMENT_S: int = 5
MAX_POLL_INTERVAL_S: int = 60


# ============================================================
# QSettings
# ============================================================
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "GitHub"
KEY_CLIENT_ID:  str = "github/client_id"
KEY_TOKEN:      str = "github/access_token"
KEY_PROFILE:    str = "github/profile_json"


# ============================================================
# Errores específicos
# ============================================================
class GitHubAuthError(Exception):
    """Cualquier fallo en el Device Flow (red, slow_down, expired…)."""


class NotConfiguredError(GitHubAuthError):
    """No hay client_id configurado — UI debe mostrar mensaje específico."""


class AuthorizationDeniedError(GitHubAuthError):
    """El usuario denegó la autorización en github.com."""


class AuthorizationExpiredError(GitHubAuthError):
    """El device_code expiró antes de que el usuario autorizara."""


# ============================================================
# Modelos
# ============================================================
@dataclass(frozen=True)
class DeviceCodeInfo:
    """Respuesta de GitHub al /device/code."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int

    @property
    def deadline_monotonic(self) -> float:
        # Marcador de cuándo el device_code va a expirar.
        # Cacheado en _instance_state para que poll_for_token aborte.
        return time.monotonic() + self.expires_in


@dataclass
class _AuthState:
    """Estado in-memory (sin persistir)."""

    token: Optional[str] = None
    profile: dict = field(default_factory=dict)


# ============================================================
# QSettings helpers
# ============================================================
def _settings():
    try:
        from PySide6.QtCore import QSettings
        return QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    except Exception as exc:  # noqa: BLE001
        logger.debug("GitHubAuth: QSettings indispo (%s)", exc)
        return None


def _get_str(key: str, default: str = "") -> str:
    s = _settings()
    if s is None:
        return default
    val = s.value(key, default, type=str)
    return val if isinstance(val, str) else default


def _set_str(key: str, value: str) -> None:
    s = _settings()
    if s is None:
        return
    s.setValue(key, value)


def _remove(key: str) -> None:
    s = _settings()
    if s is None:
        return
    s.remove(key)


# ============================================================
# HTTP — extraído para que los tests lo parcheen
# ============================================================
# Tipo del callback de HTTP POST: recibe URL + dict de params + headers,
# devuelve dict parseado del JSON de respuesta.
HttpPostFn = Callable[[str, dict, dict], dict]
HttpGetFn = Callable[[str, dict], dict]


def _http_post_json(url: str, params: dict, headers: dict) -> dict:
    """POST form-encoded → parsea respuesta JSON.

    Aislado para que los tests parcheen ``_http_post_json`` sin
    necesidad de tocar urllib globalmente.
    """

    data = urllib.parse.urlencode(params).encode("utf-8")
    merged_headers = {
        "Accept": "application/json",
        "User-Agent": "SeismicGuard/0.5",
    }
    merged_headers.update(headers or {})
    req = urllib.request.Request(
        url, data=data, headers=merged_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        raise GitHubAuthError(
            f"GitHub HTTP {exc.code} en {url}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise GitHubAuthError(f"Red caída: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GitHubAuthError(
            f"Respuesta no-JSON de {url}") from exc


def _http_get_json(url: str, headers: dict) -> dict:
    merged_headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SeismicGuard/0.5",
    }
    merged_headers.update(headers or {})
    req = urllib.request.Request(url, headers=merged_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        raise GitHubAuthError(
            f"GitHub HTTP {exc.code} en {url}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise GitHubAuthError(f"Red caída: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GitHubAuthError(
            f"Respuesta no-JSON de {url}") from exc


# ============================================================
# Lógica del Device Flow
# ============================================================
class _GitHubAuth:
    """Implementación del singleton (toda API pasa por la fachada)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Cache in-memory; se rehidrata desde QSettings al primer acceso.
        self._state = _AuthState()
        self._hydrated = False
        # Inyección para tests: si ``_http_post`` se sobrescribe, lo
        # usamos en lugar de la implementación real.
        self._http_post: HttpPostFn = _http_post_json
        self._http_get: HttpGetFn = _http_get_json
        # Sleep extraído para poder mockear en tests sin esperar 5 s.
        self._sleep: Callable[[float], None] = time.sleep

    # ── Configuración ────────────────────────────────────────
    def client_id(self) -> str:
        # Prioridad: env var > QSettings > DEFAULT_CLIENT_ID baked-in > "".
        # v0.7.4 patch: añadido fallback al DEFAULT_CLIENT_ID para que la
        # app funcione out-of-the-box si el maintainer lo configura.
        env = os.environ.get("SEISMICGUARD_GITHUB_CLIENT_ID", "").strip()
        if env:
            return env
        stored = _get_str(KEY_CLIENT_ID, "")
        if stored:
            return stored
        return DEFAULT_CLIENT_ID.strip()

    def set_client_id(self, client_id: str) -> None:
        _set_str(KEY_CLIENT_ID, client_id.strip())

    def is_configured(self) -> bool:
        return bool(self.client_id())

    # ── Device Flow ──────────────────────────────────────────
    def start_device_flow(self, scope: str = DEFAULT_SCOPE) -> DeviceCodeInfo:
        cid = self.client_id()
        if not cid:
            raise NotConfiguredError(
                "GitHub client_id no configurado — define la env var "
                "SEISMICGUARD_GITHUB_CLIENT_ID o configúralo en Ajustes."
            )
        resp = self._http_post(DEVICE_CODE_URL,
                               {"client_id": cid, "scope": scope},
                               {})
        # Validación defensiva
        for key in ("device_code", "user_code", "verification_uri",
                    "expires_in", "interval"):
            if key not in resp:
                raise GitHubAuthError(
                    f"Respuesta de GitHub inválida (falta {key!r}): {resp}"
                )
        return DeviceCodeInfo(
            device_code=str(resp["device_code"]),
            user_code=str(resp["user_code"]),
            verification_uri=str(resp["verification_uri"]),
            expires_in=int(resp["expires_in"]),
            interval=int(resp["interval"]),
        )

    def poll_for_token(self, info: DeviceCodeInfo,
                       cancel_check: Optional[Callable[[], bool]] = None,
                       ) -> str:
        """Hace polling hasta obtener token, abortar o expirar.

        ``cancel_check`` se invoca en cada iteración; si devuelve True
        levantamos ``GitHubAuthError("cancelado")`` — útil para que la
        UI cancele desde un botón "Cancelar".
        """

        cid = self.client_id()
        if not cid:
            raise NotConfiguredError("client_id no configurado")
        deadline = time.monotonic() + info.expires_in
        interval = max(1, info.interval)
        while True:
            if cancel_check and cancel_check():
                raise GitHubAuthError("cancelado por el usuario")
            if time.monotonic() >= deadline:
                raise AuthorizationExpiredError(
                    "device_code expiró antes de autorizar")
            self._sleep(interval)
            resp = self._http_post(
                ACCESS_TOKEN_URL,
                {
                    "client_id": cid,
                    "device_code": info.device_code,
                    "grant_type":
                        "urn:ietf:params:oauth:grant-type:device_code",
                },
                {},
            )
            if "access_token" in resp:
                return str(resp["access_token"])
            err = str(resp.get("error", ""))
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval = min(
                    interval + SLOW_DOWN_INCREMENT_S, MAX_POLL_INTERVAL_S)
                continue
            if err == "expired_token":
                raise AuthorizationExpiredError("expired_token")
            if err == "access_denied":
                raise AuthorizationDeniedError("usuario denegó")
            # Cualquier otro error es desconocido pero terminal.
            raise GitHubAuthError(
                f"Error de GitHub: {err or resp}")

    def fetch_user_profile(self, token: str) -> dict:
        """GET /user → dict con campos públicos extendidos.

        v0.7.4: ampliado para incluir bio + ubicación + counts (repos,
        followers, following) + url + created_at, que la Profile dialog
        muestra como una "tarjeta GitHub" enriquecida. Todos los
        campos vienen del endpoint público /user — read:user scope ya
        los cubre, no requiere permisos extra.
        """

        resp = self._http_get(USER_API_URL,
                              {"Authorization": f"Bearer {token}"})
        # ``resp.get`` puede devolver None — normalizamos siempre a str/int.
        def _s(key: str) -> str:
            return str(resp.get(key) or "")
        def _i(key: str) -> int:
            try:
                return int(resp.get(key) or 0)
            except (TypeError, ValueError):
                return 0
        return {
            # Identidad básica
            "login":       _s("login"),
            "name":        _s("name"),
            "avatar_url":  _s("avatar_url"),
            "email":       _s("email"),
            "html_url":    _s("html_url"),
            # v0.7.4 — info extendida
            "bio":         _s("bio"),
            "company":     _s("company"),
            "blog":        _s("blog"),
            "location":    _s("location"),
            "created_at":  _s("created_at"),
            "public_repos":  _i("public_repos"),
            "followers":     _i("followers"),
            "following":     _i("following"),
            "public_gists":  _i("public_gists"),
        }

    # ── Persistencia / sesión ───────────────────────────────
    def _hydrate(self) -> None:
        with self._lock:
            if self._hydrated:
                return
            self._state.token = _get_str(KEY_TOKEN) or None
            raw = _get_str(KEY_PROFILE)
            if raw:
                try:
                    self._state.profile = json.loads(raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    self._state.profile = {}
            self._hydrated = True

    def save_token(self, token: str) -> None:
        with self._lock:
            self._state.token = token
            _set_str(KEY_TOKEN, token)

    def save_profile(self, profile: dict) -> None:
        with self._lock:
            self._state.profile = dict(profile)
            _set_str(KEY_PROFILE, json.dumps(profile, ensure_ascii=False))

    def is_authenticated(self) -> bool:
        self._hydrate()
        with self._lock:
            return bool(self._state.token)

    def current_user(self) -> dict:
        self._hydrate()
        with self._lock:
            return dict(self._state.profile)

    def current_token(self) -> str:
        """Acceso al token solo para code paths que lo necesiten."""

        self._hydrate()
        with self._lock:
            return self._state.token or ""

    def logout(self) -> None:
        """Borra token + perfil cacheado. No revoca en GitHub
        (GitHub no expone un endpoint público de revoke desde el
        device flow; el usuario puede revocar manualmente desde su
        configuración de OAuth Apps)."""

        with self._lock:
            self._state.token = None
            self._state.profile = {}
            _remove(KEY_TOKEN)
            _remove(KEY_PROFILE)


# ============================================================
# Fachada
# ============================================================
_instance: Optional[_GitHubAuth] = None
_instance_lock = threading.Lock()


def _get_instance() -> _GitHubAuth:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = _GitHubAuth()
    return _instance


class GitHubAuthService:
    """Fachada estática del singleton."""

    @staticmethod
    def client_id() -> str:
        return _get_instance().client_id()

    @staticmethod
    def set_client_id(client_id: str) -> None:
        _get_instance().set_client_id(client_id)

    @staticmethod
    def is_configured() -> bool:
        return _get_instance().is_configured()

    @staticmethod
    def start_device_flow(scope: str = DEFAULT_SCOPE) -> DeviceCodeInfo:
        return _get_instance().start_device_flow(scope)

    @staticmethod
    def poll_for_token(info: DeviceCodeInfo,
                       cancel_check: Optional[Callable[[], bool]] = None,
                       ) -> str:
        return _get_instance().poll_for_token(info, cancel_check)

    @staticmethod
    def fetch_user_profile(token: str) -> dict:
        return _get_instance().fetch_user_profile(token)

    @staticmethod
    def save_token(token: str) -> None:
        _get_instance().save_token(token)

    @staticmethod
    def save_profile(profile: dict) -> None:
        _get_instance().save_profile(profile)

    @staticmethod
    def is_authenticated() -> bool:
        return _get_instance().is_authenticated()

    @staticmethod
    def current_user() -> dict:
        return _get_instance().current_user()

    @staticmethod
    def current_token() -> str:
        return _get_instance().current_token()

    @staticmethod
    def logout() -> None:
        _get_instance().logout()


def _reset_for_tests() -> None:
    """Vacía el singleton y borra QSettings. Solo tests."""

    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.logout()
        _instance = None
    # Limpiar también client_id para evitar fugas entre tests.
    _remove(KEY_CLIENT_ID)
