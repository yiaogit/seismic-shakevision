"""
Pruebas de ``shakevision.services.github_auth`` (v0.5 阶段 K).

NO hacemos requests reales a GitHub. Inyectamos ``_http_post`` /
``_http_get`` / ``_sleep`` en el singleton para simular cada caso
del Device Flow:

  * is_configured False sin client_id
  * is_configured True con env var O QSettings
  * start_device_flow construye DeviceCodeInfo desde la respuesta JSON
  * poll_for_token reintenta en authorization_pending, slow_down,
    aborta en expired_token y access_denied, y respeta cancel_check.
  * fetch_user_profile extrae solo los campos esperados.
  * save_token/save_profile/current_user/logout round-trip.
"""

from __future__ import annotations

import pytest


pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")


# ============================================================
# Fixture: aislar QSettings + reset singleton + mocks de red
# ============================================================
@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))

    # Eliminar env vars que puedan colarse desde la shell del usuario
    monkeypatch.delenv("SEISMICGUARD_GITHUB_CLIENT_ID", raising=False)

    from shakevision.services import github_auth as ga
    ga._reset_for_tests()
    yield
    ga._reset_for_tests()


# ============================================================
# Configuración
# ============================================================
def test_not_configured_without_client_id() -> None:
    from shakevision.services.github_auth import GitHubAuthService

    assert GitHubAuthService.client_id() == ""
    assert GitHubAuthService.is_configured() is False


def test_client_id_from_env_takes_priority(monkeypatch) -> None:
    from shakevision.services.github_auth import GitHubAuthService

    GitHubAuthService.set_client_id("from-settings")
    monkeypatch.setenv("SEISMICGUARD_GITHUB_CLIENT_ID", "from-env")
    assert GitHubAuthService.client_id() == "from-env"
    assert GitHubAuthService.is_configured() is True


def test_client_id_from_qsettings_when_no_env() -> None:
    from shakevision.services.github_auth import GitHubAuthService

    GitHubAuthService.set_client_id("my-id")
    assert GitHubAuthService.client_id() == "my-id"


def test_start_device_flow_raises_when_not_configured() -> None:
    from shakevision.services.github_auth import (
        GitHubAuthService,
        NotConfiguredError,
    )

    with pytest.raises(NotConfiguredError):
        GitHubAuthService.start_device_flow()


# ============================================================
# start_device_flow
# ============================================================
def _set_client_id_and_mock_http(post_fn=None, get_fn=None, sleep_fn=None):
    """Helper: configura client_id + inyecta mocks de HTTP."""

    from shakevision.services.github_auth import GitHubAuthService
    from shakevision.services import github_auth as ga

    GitHubAuthService.set_client_id("dummy-client-id")
    inst = ga._get_instance()
    if post_fn is not None:
        inst._http_post = post_fn
    if get_fn is not None:
        inst._http_get = get_fn
    if sleep_fn is not None:
        inst._sleep = sleep_fn
    return inst


def test_start_device_flow_parses_response() -> None:
    from shakevision.services.github_auth import GitHubAuthService

    def fake_post(url, params, headers):
        assert "device/code" in url
        assert params["client_id"] == "dummy-client-id"
        return {
            "device_code": "DEVCODE123",
            "user_code": "WDJB-MJHT",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
    _set_client_id_and_mock_http(post_fn=fake_post)
    info = GitHubAuthService.start_device_flow()
    assert info.user_code == "WDJB-MJHT"
    assert info.device_code == "DEVCODE123"
    assert info.interval == 5
    assert info.expires_in == 900


def test_start_device_flow_raises_on_malformed_response() -> None:
    from shakevision.services.github_auth import (
        GitHubAuthError,
        GitHubAuthService,
    )

    def fake_post(url, params, headers):
        return {"user_code": "X"}     # falta device_code, etc.
    _set_client_id_and_mock_http(post_fn=fake_post)
    with pytest.raises(GitHubAuthError):
        GitHubAuthService.start_device_flow()


# ============================================================
# poll_for_token — autorización exitosa
# ============================================================
def test_poll_returns_access_token_on_success() -> None:
    from shakevision.services.github_auth import (
        DeviceCodeInfo,
        GitHubAuthService,
    )

    seq = iter([
        {"error": "authorization_pending"},
        {"error": "authorization_pending"},
        {"access_token": "ghp_TESTTOKEN"},
    ])

    def fake_post(url, params, headers):
        return next(seq)
    sleeps: list[float] = []
    _set_client_id_and_mock_http(
        post_fn=fake_post, sleep_fn=lambda s: sleeps.append(s))

    info = DeviceCodeInfo(
        device_code="d", user_code="u", verification_uri="v",
        expires_in=900, interval=1,
    )
    tok = GitHubAuthService.poll_for_token(info)
    assert tok == "ghp_TESTTOKEN"
    # Tres llamadas a sleep (una por iteración)
    assert len(sleeps) == 3


def test_poll_handles_slow_down() -> None:
    from shakevision.services.github_auth import (
        DeviceCodeInfo,
        GitHubAuthService,
    )

    seq = iter([
        {"error": "slow_down"},
        {"access_token": "ok"},
    ])

    def fake_post(url, params, headers):
        return next(seq)
    sleeps: list[float] = []
    _set_client_id_and_mock_http(
        post_fn=fake_post, sleep_fn=lambda s: sleeps.append(s))

    info = DeviceCodeInfo(
        device_code="d", user_code="u", verification_uri="v",
        expires_in=900, interval=5,
    )
    tok = GitHubAuthService.poll_for_token(info)
    assert tok == "ok"
    # Tras slow_down el intervalo debió subir a 10 s en el siguiente sleep
    assert sleeps[0] == 5
    assert sleeps[1] >= 10


def test_poll_raises_on_access_denied() -> None:
    from shakevision.services.github_auth import (
        AuthorizationDeniedError,
        DeviceCodeInfo,
        GitHubAuthService,
    )

    def fake_post(url, params, headers):
        return {"error": "access_denied"}
    _set_client_id_and_mock_http(post_fn=fake_post, sleep_fn=lambda s: None)
    info = DeviceCodeInfo(
        device_code="d", user_code="u", verification_uri="v",
        expires_in=900, interval=1,
    )
    with pytest.raises(AuthorizationDeniedError):
        GitHubAuthService.poll_for_token(info)


def test_poll_raises_on_expired_token() -> None:
    from shakevision.services.github_auth import (
        AuthorizationExpiredError,
        DeviceCodeInfo,
        GitHubAuthService,
    )

    def fake_post(url, params, headers):
        return {"error": "expired_token"}
    _set_client_id_and_mock_http(post_fn=fake_post, sleep_fn=lambda s: None)
    info = DeviceCodeInfo(
        device_code="d", user_code="u", verification_uri="v",
        expires_in=900, interval=1,
    )
    with pytest.raises(AuthorizationExpiredError):
        GitHubAuthService.poll_for_token(info)


def test_poll_respects_cancel_check() -> None:
    from shakevision.services.github_auth import (
        DeviceCodeInfo,
        GitHubAuthError,
        GitHubAuthService,
    )

    def fake_post(url, params, headers):
        return {"error": "authorization_pending"}
    _set_client_id_and_mock_http(post_fn=fake_post, sleep_fn=lambda s: None)
    info = DeviceCodeInfo(
        device_code="d", user_code="u", verification_uri="v",
        expires_in=900, interval=1,
    )
    with pytest.raises(GitHubAuthError):
        # cancel_check siempre True → debe abortar la primera iteración
        GitHubAuthService.poll_for_token(info, cancel_check=lambda: True)


# ============================================================
# fetch_user_profile
# ============================================================
def test_fetch_user_profile_extracts_only_allowed_fields() -> None:
    from shakevision.services.github_auth import GitHubAuthService

    def fake_get(url, headers):
        assert headers["Authorization"].startswith("Bearer ")
        return {
            "login": "yiaogit",
            "name": "Yiao",
            "avatar_url": "https://avatars.githubusercontent.com/u/1",
            "email": "yiaogit@gmail.com",
            "html_url": "https://github.com/yiaogit",
            "private_repos": 17,    # campo extra que NO debe propagarse
        }
    _set_client_id_and_mock_http(get_fn=fake_get)
    profile = GitHubAuthService.fetch_user_profile("ghp_token")
    assert profile["login"] == "yiaogit"
    assert profile["avatar_url"].startswith("https://")
    assert "private_repos" not in profile


# ============================================================
# Persistencia
# ============================================================
def test_save_token_and_profile_round_trip() -> None:
    from shakevision.services import github_auth as ga
    from shakevision.services.github_auth import GitHubAuthService

    assert GitHubAuthService.is_authenticated() is False
    GitHubAuthService.save_token("ghp_xxx")
    GitHubAuthService.save_profile({
        "login": "yiaogit",
        "name": "Yiao",
        "avatar_url": "https://avatars/u/1",
    })

    # Simular reinicio del singleton (token persiste en QSettings).
    ga._instance = None
    assert GitHubAuthService.is_authenticated() is True
    user = GitHubAuthService.current_user()
    assert user["login"] == "yiaogit"


def test_logout_clears_state() -> None:
    from shakevision.services.github_auth import GitHubAuthService

    GitHubAuthService.save_token("t")
    GitHubAuthService.save_profile({"login": "u"})
    assert GitHubAuthService.is_authenticated() is True
    GitHubAuthService.logout()
    assert GitHubAuthService.is_authenticated() is False
    assert GitHubAuthService.current_user() == {}
