"""Unit coverage for the DB-backed OIDC/Google router: fail-closed provider
resolution, the per-provider client cache (keying, config-rotation bust),
per-provider client construction, and OAuth state/CSRF validation. No DB, no
network, no live IdP."""

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.orm import Session
from starlette.requests import Request

from onyx.auth.users import (
    CSRF_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_KEY,
    decode_and_validate_oauth_state,
    generate_csrf_token,
    generate_state_token,
)
from onyx.db.enums import Permission, SSOProviderType
from onyx.db.models import SSOProvider
from onyx.error_handling.exceptions import OnyxError
from onyx.server import oidc_multi
from onyx.utils.sensitive import make_mock_sensitive_value

_OIDC_CONFIG = {
    "client_id": "cid",
    "client_secret": "secret",
    "openid_config_url": "https://idp.example.com/.well-known/openid-configuration",
}
_GOOGLE_CONFIG = {"client_id": "gid", "client_secret": "gsecret"}


@pytest.fixture(autouse=True)
def _stub_idp_url_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # These tests build clients from fake IdP URLs and stay off the network. The
    # URL guard's own DNS/SSRF checks live in test_sso_url_guard.
    monkeypatch.setattr(oidc_multi, "validate_idp_url", lambda *_a, **_k: None)
    monkeypatch.setattr(
        oidc_multi, "validate_discovered_endpoints", lambda *_a, **_k: None
    )


_DB = cast(Session, object())
_TEST_SECRET = "unit-test-secret"


def _provider(**overrides: object) -> SSOProvider:
    base: dict[str, Any] = {
        "name": "okta",
        "provider_type": SSOProviderType.OIDC,
        "allowed_email_domains": ["companya.com"],
        "config": make_mock_sensitive_value(dict(_OIDC_CONFIG)),
    }
    base.update(overrides)
    return cast(SSOProvider, SimpleNamespace(**base))


def test_resolve_oidc_returns_config(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider()
    monkeypatch.setattr(
        oidc_multi, "fetch_sso_provider_by_name", lambda **_kw: provider
    )
    resolved, config = oidc_multi._resolve_oidc_provider(_DB, "okta")
    assert resolved is provider
    assert config == {
        **_OIDC_CONFIG,
        "legacy_callback": False,
        "require_verified_email": False,
        "pkce_enabled": False,
        "scopes": [],
    }


def test_google_provider_validates_role_map_and_masks_directory_credentials() -> None:
    from onyx.db.sso_provider import mask_secret_config_values, validate_sso_config

    config = validate_sso_config(
        SSOProviderType.GOOGLE_OAUTH,
        {
            **_GOOGLE_CONFIG,
            "ou_role_map": '{"/Staff":"interni"}',
            "directory_auth_mode": "service_account",
            "directory_service_account_json": '{"type":"service_account","client_email":"sa@corp.test","private_key":"secret","token_uri":"https://oauth2.googleapis.com/token"}',
        },
    )
    assert config["ou_role_map"] == '{"/Staff":"interni"}'
    masked = mask_secret_config_values(SSOProviderType.GOOGLE_OAUTH, config)
    assert "private_key" not in masked["directory_service_account_json"]

    for role_map in ({"/Staff": "unknown"}, {"Staff": "interni"}):
        with pytest.raises(ValueError):
            validate_sso_config(
                SSOProviderType.GOOGLE_OAUTH,
                {**_GOOGLE_CONFIG, "ou_role_map": json.dumps(role_map)},
            )
    with pytest.raises(ValueError) as exc:
        validate_sso_config(
            SSOProviderType.GOOGLE_OAUTH,
            {**_GOOGLE_CONFIG, "directory_service_account_json": "private-secret"},
        )
    assert "private-secret" not in str(exc.value)


def test_google_directory_json_is_encrypted_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.db import sso_provider

    monkeypatch.setattr(sso_provider, "USER_AUTH_SECRET", "x" * 32)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    plaintext = json.dumps(
        {
            "type": "service_account",
            "client_email": "sa@corp.test",
            "private_key": private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    db_session = MagicMock()
    provider = sso_provider.create_sso_provider(
        db_session,
        name="workspace",
        display_name="Workspace",
        provider_type=SSOProviderType.GOOGLE_OAUTH,
        config={**_GOOGLE_CONFIG, "directory_service_account_json": plaintext},
        allowed_email_domains=["corp.test"],
    )
    assert provider.config is not None
    stored = provider.config.get_value(apply_mask=False)
    assert plaintext not in str(stored)
    assert (
        sso_provider.decrypt_directory_service_account_json(
            stored["directory_service_account_json"]
        )
        == plaintext
    )
    assert (
        sso_provider.protect_google_config_for_storage(stored)[
            "directory_service_account_json"
        ]
        == stored["directory_service_account_json"]
    )

    from onyx.server.manage.sso.api import update_sso_provider_endpoint
    from onyx.server.manage.sso.models import SSOProviderUpdateRequest

    provider.id = 17
    provider.enabled = True
    db_session.get.return_value = provider
    with (
        patch("onyx.server.manage.sso.api._sync_login_domain_routing"),
        patch("onyx.server.manage.sso.api.invalidate_sso_provider_options_cache"),
    ):
        response = update_sso_provider_endpoint(
            17,
            SSOProviderUpdateRequest(
                config={
                    "directory_service_account_json": sso_provider.DIRECTORY_JSON_MASK
                }
            ),
            MagicMock(),
            db_session,
        )
    assert (
        response.config["directory_service_account_json"]
        == sso_provider.DIRECTORY_JSON_MASK
    )
    assert provider.config is not None
    assert (
        provider.config.get_value(apply_mask=False)["directory_service_account_json"]
        == stored["directory_service_account_json"]
    )
    with pytest.raises(ValueError, match="Invalid Directory private key"):
        sso_provider.create_sso_provider(
            db_session,
            name="bad-credentials",
            display_name="Invalid credentials",
            provider_type=SSOProviderType.GOOGLE_OAUTH,
            config={
                **_GOOGLE_CONFIG,
                "directory_service_account_json": json.dumps(
                    {
                        "type": "service_account",
                        "client_email": "sa@corp.test",
                        "private_key": "invalid",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                ),
            },
            allowed_email_domains=["corp.test"],
        )


def test_resolve_google_returns_config(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(
        name="google",
        provider_type=SSOProviderType.GOOGLE_OAUTH,
        config=make_mock_sensitive_value(dict(_GOOGLE_CONFIG)),
    )
    monkeypatch.setattr(
        oidc_multi, "fetch_sso_provider_by_name", lambda **_kw: provider
    )
    _resolved, config = oidc_multi._resolve_oidc_provider(_DB, "google")
    assert config == {
        **_GOOGLE_CONFIG,
        "legacy_callback": False,
        "pkce_enabled": False,
        "scopes": [],
        "ou_role_map": "",
        "directory_auth_mode": "service_account",
        "directory_service_account_json": "",
    }


@pytest.mark.asyncio
async def test_google_link_authorize_requires_admin_session_and_signs_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(name="google", provider_type=SSOProviderType.GOOGLE_OAUTH)
    monkeypatch.setattr(
        oidc_multi, "_resolve_oidc_provider", lambda *_a: (provider, _GOOGLE_CONFIG)
    )
    client = MagicMock()
    client.get_authorization_url = AsyncMock(
        return_value="https://accounts.google.com/login"
    )
    monkeypatch.setattr(oidc_multi, "_get_oauth_client", AsyncMock(return_value=client))
    state: dict[str, object] = {}
    monkeypatch.setattr(
        oidc_multi,
        "generate_state_token",
        lambda data, _key: (state.update(data), "signed")[1],
    )
    monkeypatch.setattr(
        oidc_multi,
        "get_effective_permissions",
        lambda _user: {Permission.FULL_ADMIN_PANEL_ACCESS},
    )
    strategy = MagicMock()
    strategy.read_token = AsyncMock(return_value=None)
    request = Request(
        {
            "type": "http",
            "query_string": b"link_account=true",
            "headers": [
                (
                    b"cookie",
                    f"{oidc_multi.FASTAPI_USERS_AUTH_COOKIE_NAME}=session".encode(),
                )
            ],
        }
    )
    with pytest.raises(OnyxError):
        await oidc_multi.oidc_login_for_provider(
            "google", request, _DB, strategy, MagicMock()
        )
    assert not state
    admin = MagicMock(id=uuid4(), is_active=True)
    strategy.read_token.return_value = admin
    await oidc_multi.oidc_login_for_provider(
        "google", request, _DB, strategy, MagicMock()
    )
    assert state["link_user_id"] == str(admin.id)


def test_resolve_fail_closed_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oidc_multi, "fetch_sso_provider_by_name", lambda **_kw: None)
    with pytest.raises(OnyxError):
        oidc_multi._resolve_oidc_provider(_DB, "missing")


def test_resolve_fail_closed_saml_type(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(provider_type=SSOProviderType.SAML)
    monkeypatch.setattr(
        oidc_multi, "fetch_sso_provider_by_name", lambda **_kw: provider
    )
    with pytest.raises(OnyxError):
        oidc_multi._resolve_oidc_provider(_DB, "saml-row")


def test_resolve_fail_closed_incomplete_config(monkeypatch: pytest.MonkeyPatch) -> None:
    # An OIDC row missing openid_config_url fails model validation -> fail closed.
    provider = _provider(
        config=make_mock_sensitive_value({"client_id": "c", "client_secret": "s"})
    )
    monkeypatch.setattr(
        oidc_multi, "fetch_sso_provider_by_name", lambda **_kw: provider
    )
    with pytest.raises(OnyxError):
        oidc_multi._resolve_oidc_provider(_DB, "okta")


def test_cache_key_stable_and_config_sensitive() -> None:
    provider = _provider()
    key = oidc_multi._get_cache_key(provider, dict(_OIDC_CONFIG))
    assert key == oidc_multi._get_cache_key(provider, dict(_OIDC_CONFIG))
    rotated = oidc_multi._get_cache_key(
        provider, {**_OIDC_CONFIG, "client_secret": "rotated"}
    )
    assert key != rotated


def test_build_client_google_uses_provider_name() -> None:
    provider = _provider(name="google", provider_type=SSOProviderType.GOOGLE_OAUTH)
    client = oidc_multi._build_client(provider, dict(_GOOGLE_CONFIG))
    assert client.name == "google"


def test_build_client_oidc_uses_provider_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # VerifiedEmailOpenID.__init__ fetches the discovery doc over the network.
    # Stub it so the unit test stays offline.
    def _fake_openid(
        _client_id: str,
        _client_secret: str,
        _config_url: str,
        *,
        name: str,
        **_kwargs: Any,
    ) -> Any:
        return SimpleNamespace(name=name)

    monkeypatch.setattr(oidc_multi, "VerifiedEmailOpenID", _fake_openid)
    client = oidc_multi._build_client(_provider(name="okta"), dict(_OIDC_CONFIG))
    assert client.name == "okta"


def _openid_stub_with_discovery(scopes_supported: list[str] | None) -> Any:
    class _FakeOpenID:
        def __init__(
            self,
            _client_id: str,
            _client_secret: str,
            _config_url: str,
            *,
            name: str,
            base_scopes: list[str] | None = None,
            **_kwargs: Any,
        ) -> None:
            self.name = name
            self.base_scopes = list(base_scopes or [])
            self.openid_configuration: dict[str, Any] = (
                {}
                if scopes_supported is None
                else {"scopes_supported": scopes_supported}
            )

    return _FakeOpenID


def test_offline_access_dropped_when_idp_does_not_advertise_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Amazon Cognito advertises scopes_supported without offline_access and
    # rejects the whole authorize request when it is included.
    monkeypatch.setattr(
        oidc_multi,
        "VerifiedEmailOpenID",
        _openid_stub_with_discovery(["openid", "email", "profile"]),
    )
    client = oidc_multi._build_client(_provider(), dict(_OIDC_CONFIG))
    assert "offline_access" not in (client.base_scopes or [])


def test_offline_access_kept_when_idp_advertises_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        oidc_multi,
        "VerifiedEmailOpenID",
        _openid_stub_with_discovery(["openid", "email", "offline_access"]),
    )
    client = oidc_multi._build_client(_provider(), dict(_OIDC_CONFIG))
    assert "offline_access" in (client.base_scopes or [])


def test_offline_access_kept_when_discovery_has_no_scopes_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        oidc_multi, "VerifiedEmailOpenID", _openid_stub_with_discovery(None)
    )
    client = oidc_multi._build_client(_provider(), dict(_OIDC_CONFIG))
    assert "offline_access" in (client.base_scopes or [])


def test_explicitly_configured_offline_access_is_never_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        oidc_multi,
        "VerifiedEmailOpenID",
        _openid_stub_with_discovery(["openid", "email"]),
    )
    config = {**_OIDC_CONFIG, "scopes": ["openid", "email", "offline_access"]}
    client = oidc_multi._build_client(_provider(), config)
    assert "offline_access" in (client.base_scopes or [])


@pytest.mark.asyncio
async def test_client_cache_hits_and_rebuilds_on_config_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oidc_multi._CLIENT_CACHE.clear()
    builds = {"count": 0}

    def _fake_build(provider: SSOProvider, _config: dict[str, Any]) -> Any:
        builds["count"] += 1
        return SimpleNamespace(name=provider.name)

    monkeypatch.setattr(oidc_multi, "_build_client", _fake_build)
    provider = _provider()

    await oidc_multi._get_oauth_client(provider, dict(_OIDC_CONFIG))
    await oidc_multi._get_oauth_client(provider, dict(_OIDC_CONFIG))
    assert builds["count"] == 1  # same key is a cache hit

    # A rotated secret changes the config hash, so the key changes and rebuilds.
    await oidc_multi._get_oauth_client(
        provider, {**_OIDC_CONFIG, "client_secret": "rotated"}
    )
    assert builds["count"] == 2
    oidc_multi._CLIENT_CACHE.clear()


def test_decode_state_accepts_valid() -> None:
    csrf = generate_csrf_token()
    state = generate_state_token(
        {"next_url": "/", "provider_name": "okta", CSRF_TOKEN_KEY: csrf}, _TEST_SECRET
    )
    request = cast(
        Any,
        SimpleNamespace(
            cookies={CSRF_TOKEN_COOKIE_NAME: csrf}, state=SimpleNamespace()
        ),
    )
    data = decode_and_validate_oauth_state(
        request=request,
        state_value=state,
        state_secret=_TEST_SECRET,
        expected_provider_name="okta",
    )
    assert data[CSRF_TOKEN_KEY] == csrf


def test_decode_state_rejects_mismatched_csrf() -> None:
    csrf = generate_csrf_token()
    state = generate_state_token(
        {"next_url": "/", "provider_name": "okta", CSRF_TOKEN_KEY: csrf}, _TEST_SECRET
    )
    request = cast(Any, SimpleNamespace(cookies={CSRF_TOKEN_COOKIE_NAME: "different"}))
    with pytest.raises(OnyxError):
        decode_and_validate_oauth_state(
            request=request,
            state_value=state,
            state_secret=_TEST_SECRET,
            expected_provider_name="okta",
        )


def test_decode_state_rejects_wrong_provider() -> None:
    # A state minted for one provider must not validate on another's callback.
    csrf = generate_csrf_token()
    state = generate_state_token(
        {"next_url": "/", "provider_name": "okta", CSRF_TOKEN_KEY: csrf}, _TEST_SECRET
    )
    request = cast(
        Any,
        SimpleNamespace(
            cookies={CSRF_TOKEN_COOKIE_NAME: csrf}, state=SimpleNamespace()
        ),
    )
    with pytest.raises(OnyxError):
        decode_and_validate_oauth_state(
            request=request,
            state_value=state,
            state_secret=_TEST_SECRET,
            expected_provider_name="google",
        )


def test_decode_state_rejects_bad_jwt() -> None:
    request = cast(Any, SimpleNamespace(cookies={CSRF_TOKEN_COOKIE_NAME: "x"}))
    with pytest.raises(OnyxError):
        decode_and_validate_oauth_state(
            request=request,
            state_value="not-a-jwt",
            state_secret=_TEST_SECRET,
            expected_provider_name="okta",
        )


# ---------------------------------------------------------------------------
# Legacy callback routing: migrated rows keep the redirect URI their IdP
# client already allowlists, so upgrading never requires an IdP console edit.
# ---------------------------------------------------------------------------


def test_callback_uri_parametric_by_default() -> None:
    provider = _provider()
    assert oidc_multi._callback_uri(provider, dict(_OIDC_CONFIG)).endswith(
        "/api/auth/oidc/okta/callback"
    )


def test_callback_uri_legacy_oidc() -> None:
    provider = _provider()
    config: dict[str, object] = {**_OIDC_CONFIG, "legacy_callback": True}
    uri = oidc_multi._callback_uri(provider, config)
    assert uri.endswith("/auth/oidc/callback")
    assert "/api/" not in uri


def test_callback_uri_legacy_google() -> None:
    provider = _provider(name="google", provider_type=SSOProviderType.GOOGLE_OAUTH)
    config: dict[str, object] = {**_GOOGLE_CONFIG, "legacy_callback": True}
    uri = oidc_multi._callback_uri(provider, config)
    assert uri.endswith("/auth/oauth/callback")
    assert "/api/" not in uri


def test_validate_config_accepts_legacy_callback_for_oauth_types() -> None:
    from onyx.db.sso_provider import validate_sso_config

    oidc = validate_sso_config(
        SSOProviderType.OIDC, {**_OIDC_CONFIG, "legacy_callback": True}
    )
    assert oidc["legacy_callback"] is True
    google = validate_sso_config(
        SSOProviderType.GOOGLE_OAUTH, {**_GOOGLE_CONFIG, "legacy_callback": True}
    )
    assert google["legacy_callback"] is True
    # Omitting the flag stays valid and defaults off.
    assert (
        validate_sso_config(SSOProviderType.OIDC, dict(_OIDC_CONFIG))["legacy_callback"]
        is False
    )


def test_validate_config_require_verified_email_is_oidc_only() -> None:
    from onyx.db.sso_provider import validate_sso_config

    oidc = validate_sso_config(
        SSOProviderType.OIDC, {**_OIDC_CONFIG, "require_verified_email": True}
    )
    assert oidc["require_verified_email"] is True
    # Omitting the flag stays valid and defaults off.
    assert (
        validate_sso_config(SSOProviderType.OIDC, dict(_OIDC_CONFIG))[
            "require_verified_email"
        ]
        is False
    )
    # The flag only parameterizes the OIDC client, and the Google config
    # model forbids unknown keys.
    with pytest.raises(ValueError):
        validate_sso_config(
            SSOProviderType.GOOGLE_OAUTH,
            {**_GOOGLE_CONFIG, "require_verified_email": True},
        )


def test_build_client_passes_require_verified_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_openid(
        _client_id: str,
        _client_secret: str,
        _config_url: str,
        *,
        require_verified_email: bool = False,
        **_kwargs: Any,
    ) -> Any:
        return SimpleNamespace(require_verified_email=require_verified_email)

    monkeypatch.setattr(oidc_multi, "VerifiedEmailOpenID", _fake_openid)
    client = cast(
        Any,
        oidc_multi._build_client(
            _provider(name="entra"),
            {**_OIDC_CONFIG, "require_verified_email": True},
        ),
    )
    assert client.require_verified_email is True


def test_validate_config_rejects_legacy_callback_for_saml() -> None:
    from onyx.db.sso_provider import validate_sso_config

    with pytest.raises(ValueError):
        validate_sso_config(
            SSOProviderType.SAML,
            {
                "idp_entity_id": "e",
                "idp_sso_url": "https://idp/sso",
                "idp_x509_cert": "cert",
                "sp_entity_id": "sp",
                "legacy_callback": True,
            },
        )


def test_login_callback_uri_saml_is_fixed_acs() -> None:
    from onyx.db.sso_provider import sso_login_callback_uri

    provider = _provider(name="corp-saml", provider_type=SSOProviderType.SAML)
    uri = sso_login_callback_uri(provider, {}, "https://onyx.example.com")
    assert uri == "https://onyx.example.com/auth/saml/callback"


def test_fixed_callback_rejects_missing_state() -> None:
    import asyncio

    request = cast(Any, SimpleNamespace(cookies={}))
    with pytest.raises(OnyxError):
        asyncio.run(
            oidc_multi.oidc_login_callback(
                request=request,
                code="code",
                state=None,
                error=None,
                strategy=cast(Any, None),
                user_manager=cast(Any, None),
            )
        )


def test_fixed_callback_rejects_state_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    monkeypatch.setattr(oidc_multi, "USER_AUTH_SECRET", _TEST_SECRET)
    csrf = generate_csrf_token()
    state = generate_state_token({"next_url": "/", CSRF_TOKEN_KEY: csrf}, _TEST_SECRET)
    request = cast(
        Any,
        SimpleNamespace(
            cookies={CSRF_TOKEN_COOKIE_NAME: csrf}, state=SimpleNamespace()
        ),
    )
    with pytest.raises(OnyxError):
        asyncio.run(
            oidc_multi.oidc_login_callback(
                request=request,
                code="code",
                state=state,
                error=None,
                strategy=cast(Any, None),
                user_manager=cast(Any, None),
            )
        )


def test_validate_config_pkce_and_scopes_on_oauth_types() -> None:
    from onyx.db.sso_provider import validate_sso_config

    oidc = validate_sso_config(
        SSOProviderType.OIDC,
        {**_OIDC_CONFIG, "pkce_enabled": True, "scopes": ["openid", "email"]},
    )
    assert oidc["pkce_enabled"] is True
    assert oidc["scopes"] == ["openid", "email"]
    google = validate_sso_config(
        SSOProviderType.GOOGLE_OAUTH,
        {**_GOOGLE_CONFIG, "pkce_enabled": True, "scopes": ["openid"]},
    )
    assert google["pkce_enabled"] is True
    # SAML has no OAuth flow, so the fields are invalid there.
    with pytest.raises(ValueError):
        validate_sso_config(
            SSOProviderType.SAML,
            {
                "idp_entity_id": "e",
                "idp_sso_url": "https://idp/sso",
                "idp_x509_cert": "cert",
                "sp_entity_id": "sp",
                "pkce_enabled": True,
            },
        )


def test_pkce_row_true_sufficient_env_can_force_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc_multi, "OIDC_PKCE_ENABLED", False)
    assert oidc_multi._pkce_enabled({"pkce_enabled": True}) is True
    assert oidc_multi._pkce_enabled({"pkce_enabled": False}) is False
    assert oidc_multi._pkce_enabled({}) is False
    # The deployment-wide env flag still forces PKCE on while it exists.
    monkeypatch.setattr(oidc_multi, "OIDC_PKCE_ENABLED", True)
    assert oidc_multi._pkce_enabled({"pkce_enabled": False}) is True


def test_build_client_scopes_row_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_openid(
        _client_id: str,
        _client_secret: str,
        _config_url: str,
        *,
        base_scopes: list[str],
        **_kwargs: Any,
    ) -> Any:
        captured["scopes"] = base_scopes
        return SimpleNamespace(base_scopes=base_scopes)

    monkeypatch.setattr(oidc_multi, "VerifiedEmailOpenID", _fake_openid)
    monkeypatch.setattr(oidc_multi, "OIDC_SCOPE_OVERRIDE", ["env-scope"])

    # Row scopes win over the env override.
    oidc_multi._build_client(
        _provider(), {**_OIDC_CONFIG, "scopes": ["openid", "profile"]}
    )
    assert captured["scopes"] == ["openid", "profile", "offline_access"]

    # Empty row scopes fall back to the env override.
    oidc_multi._build_client(_provider(), {**_OIDC_CONFIG, "scopes": []})
    assert captured["scopes"] == ["env-scope", "offline_access"]


def test_build_client_google_scopes_row_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc_multi, "GOOGLE_OAUTH_SCOPE_OVERRIDE", ["env-scope"])
    provider = _provider(name="google", provider_type=SSOProviderType.GOOGLE_OAUTH)

    client = oidc_multi._build_client(
        provider, {**_GOOGLE_CONFIG, "scopes": ["openid", "email"]}
    )
    assert client.base_scopes == ["openid", "email"]

    client = oidc_multi._build_client(provider, {**_GOOGLE_CONFIG, "scopes": []})
    assert client.base_scopes == ["env-scope"]


def test_state_pins_pkce_mode() -> None:
    # The callback must honor the mode the authorize leg minted, not the
    # row's current setting, so mid-flow provider edits cannot break logins.
    csrf = generate_csrf_token()
    state = generate_state_token(
        {
            "next_url": "/",
            "provider_name": "okta",
            "pkce": True,
            CSRF_TOKEN_KEY: csrf,
        },
        _TEST_SECRET,
    )
    request = cast(
        Any,
        SimpleNamespace(
            cookies={CSRF_TOKEN_COOKIE_NAME: csrf}, state=SimpleNamespace()
        ),
    )
    data = decode_and_validate_oauth_state(
        request=request,
        state_value=state,
        state_secret=_TEST_SECRET,
        expected_provider_name="okta",
    )
    assert data["pkce"] is True
