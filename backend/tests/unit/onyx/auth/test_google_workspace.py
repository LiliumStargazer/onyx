"""Workspace login uses verified Google identity and Directory membership."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi_users import exceptions
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import OAuth2Token
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import Response

from onyx.auth.google_workspace import admit_google_workspace_login, workspace_role_map
from onyx.auth.users import (
    FASTAPI_USERS_AUTH_COOKIE_NAME,
    UserManager,
    complete_login_flow,
)
from onyx.db import sso_provider
from onyx.db.enums import Permission
from onyx.db.sso_provider import GoogleProviderConfig
from onyx.error_handling.exceptions import OnyxError


@pytest.mark.asyncio
async def test_workspace_login_inherits_nearest_ou_and_keeps_subject_on_email_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OU_ROLE_MAP", '{"/": "agente", "/Staff": "interni"}')
    claims = {
        "sub": "123",
        "email": "old@corp.test",
        "email_verified": True,
        "hd": "corp.test",
    }
    directory_user = {
        "id": "123",
        "primaryEmail": "old@corp.test",
        "orgUnitPath": "/Staff/Team",
        "suspended": False,
        "archived": False,
    }
    with (
        patch(
            "onyx.auth.google_workspace.id_token.verify_oauth2_token",
            return_value=claims,
        ),
        patch(
            "onyx.auth.google_workspace._directory_user", return_value=directory_user
        ) as directory,
    ):
        token = OAuth2Token({"id_token": "signed-token", "access_token": "access"})
        assert await admit_google_workspace_login(token, "client", ["corp.test"]) == (
            "123",
            "old@corp.test",
            "interni",
        )
        claims["email"] = "new@corp.test"
        directory_user["primaryEmail"] = "new@corp.test"
        assert await admit_google_workspace_login(token, "client", ["corp.test"]) == (
            "123",
            "new@corp.test",
            "interni",
        )
        assert directory.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim_change", "directory_change"),
    [
        ({"sub": ""}, {}),
        ({"email_verified": False}, {}),
        ({"hd": "other.test"}, {}),
        ({"hd": None}, {}),
        ({}, {"suspended": True}),
        ({}, {"suspended": None}),
        ({}, {"archived": True}),
        ({}, {"id": "different"}),
        ({}, {"orgUnitPath": "/Unknown"}),
        ({}, {"primaryEmail": "other@corp.test"}),
    ],
)
async def test_workspace_login_denies_unknown_identity_or_directory_account(
    monkeypatch: pytest.MonkeyPatch,
    claim_change: dict[str, object],
    directory_change: dict[str, object],
) -> None:
    monkeypatch.setenv("OU_ROLE_MAP", '{"/Staff": "interni"}')
    claims = {
        "sub": "123",
        "email": "user@corp.test",
        "email_verified": True,
        "hd": "corp.test",
    } | claim_change
    directory_user = {
        "id": "123",
        "primaryEmail": "user@corp.test",
        "orgUnitPath": "/Staff",
        "suspended": False,
        "archived": False,
    } | directory_change
    with (
        patch(
            "onyx.auth.google_workspace.id_token.verify_oauth2_token",
            return_value=claims,
        ),
        patch(
            "onyx.auth.google_workspace._directory_user", return_value=directory_user
        ),
    ):
        with pytest.raises(OnyxError):
            await admit_google_workspace_login(
                OAuth2Token({"id_token": "signed-token"}), "client", ["corp.test"]
            )


@pytest.mark.asyncio
async def test_google_provider_credentials_admit_login_without_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OU_ROLE_MAP", raising=False)
    monkeypatch.delenv("GOOGLE_DIRECTORY_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.setattr(sso_provider, "USER_AUTH_SECRET", "x" * 32)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    protected = sso_provider.protect_google_config_for_storage(
        {
            "directory_service_account_json": json.dumps(
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
        }
    )
    provider = GoogleProviderConfig(
        client_id="client",
        client_secret="secret",
        ou_role_map='{"/Staff":"interni"}',
        directory_service_account_json=protected["directory_service_account_json"],
    )
    with (
        patch(
            "onyx.auth.google_workspace.id_token.verify_oauth2_token",
            return_value={
                "sub": "123",
                "email": "admin@corp.test",
                "email_verified": True,
                "hd": "corp.test",
            },
        ),
        patch(
            "onyx.auth.google_workspace.service_account.Credentials.from_service_account_info"
        ) as load_credentials,
        patch("onyx.auth.google_workspace.AuthorizedSession") as session,
    ):
        session.return_value.__enter__.return_value.get.return_value.json.return_value = {
            "id": "123",
            "primaryEmail": "admin@corp.test",
            "orgUnitPath": "/Staff/Team",
            "suspended": False,
        }
        assert await admit_google_workspace_login(
            OAuth2Token({"id_token": "signed"}), "client", ["corp.test"], provider
        ) == ("123", "admin@corp.test", "interni")
        load_credentials.assert_called_once()
        assert load_credentials.call_args.args[0]["client_email"] == "sa@corp.test"


@pytest.mark.asyncio
async def test_google_provider_without_role_map_does_not_use_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OU_ROLE_MAP", '{"/":"interni"}')
    provider = GoogleProviderConfig(client_id="client", client_secret="secret")
    with pytest.raises(OnyxError, match="Workspace role map is not configured"):
        await admit_google_workspace_login(
            OAuth2Token({"id_token": "signed"}), "client", ["corp.test"], provider
        )


@pytest.mark.asyncio
async def test_admin_links_verified_google_identity_only_with_matching_session() -> (
    None
):
    admin_id = uuid4()
    admin = MagicMock(id=admin_id, email="admin@corp.test", is_active=True)
    oauth_client = GoogleOAuth2("client", "secret")
    user_manager = MagicMock()
    user_manager.link_verified_google_account = AsyncMock(return_value=admin)
    user_manager.oauth_callback = AsyncMock()
    user_manager.on_after_login = AsyncMock()
    strategy = MagicMock()
    strategy.read_token = AsyncMock(return_value=admin)
    backend = MagicMock()
    backend.login = AsyncMock(
        return_value=Response(headers={"set-cookie": "session=ok"})
    )
    token = OAuth2Token({"id_token": "signed", "access_token": "access"})

    with (
        patch(
            "onyx.auth.users.admit_google_workspace_login", new_callable=AsyncMock
        ) as admit,
        patch("onyx.auth.users.capture_oauth_login_claims", new_callable=AsyncMock),
        patch(
            "onyx.auth.users.fetch_ee_implementation_or_noop",
            return_value=lambda *_a: "default_schema",
        ),
        patch(
            "onyx.auth.users.get_effective_permissions",
            return_value={Permission.FULL_ADMIN_PANEL_ACCESS},
        ),
    ):
        admit.return_value = ("subject", "admin@corp.test", "interni")
        for current_user in (
            None,
            MagicMock(id=uuid4(), email="admin@corp.test", is_active=True),
        ):
            strategy.read_token.return_value = current_user
            with pytest.raises(OnyxError):
                await complete_login_flow(
                    oauth_client=oauth_client,
                    token=token,
                    state_data={"link_user_id": str(admin_id)},
                    request=Request(
                        {
                            "type": "http",
                            "headers": [
                                (
                                    b"cookie",
                                    f"{FASTAPI_USERS_AUTH_COOKIE_NAME}=session".encode(),
                                )
                            ],
                        }
                    ),
                    user_manager=user_manager,
                    backend=backend,
                    strategy=strategy,
                    associate_by_email=False,
                    is_verified_by_default=True,
                    allowed_email_domains_override=["corp.test"],
                )
        user_manager.link_verified_google_account.assert_not_awaited()

        strategy.read_token.return_value = admin
        response = await complete_login_flow(
            oauth_client=oauth_client,
            token=token,
            state_data={"link_user_id": str(admin_id)},
            request=Request(
                {
                    "type": "http",
                    "headers": [
                        (
                            b"cookie",
                            f"{FASTAPI_USERS_AUTH_COOKIE_NAME}=session".encode(),
                        )
                    ],
                }
            ),
            user_manager=user_manager,
            backend=backend,
            strategy=strategy,
            associate_by_email=False,
            is_verified_by_default=True,
            allowed_email_domains_override=["corp.test"],
        )
        assert response.status_code == 302
        user_manager.link_verified_google_account.assert_awaited_once()
        assert user_manager.link_verified_google_account.call_args.args[:4] == (
            admin_id,
            "google",
            "subject",
            "admin@corp.test",
        )
        user_manager.oauth_callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_google_link_keeps_admin_account_and_rejects_other_subjects() -> (
    None
):
    account = MagicMock(
        id=uuid4(), email="admin@corp.test", is_active=True, oauth_accounts=[]
    )
    account.account_type.is_web_login.return_value = True
    session = MagicMock()
    session.run_sync = AsyncMock(return_value=account)
    session.refresh = AsyncMock()
    manager = UserManager(MagicMock())
    manager.user_db.add_oauth_account = AsyncMock(return_value=account)
    manager.get_by_oauth_account = AsyncMock(side_effect=exceptions.UserNotExists())

    @asynccontextmanager
    async def tenant_session(_tenant_id: str) -> AsyncIterator[MagicMock]:
        yield session

    with patch.object(manager, "_tenant_session_with_bound_user_db", tenant_session):
        linked = await manager.link_verified_google_account(
            account.id, "google", "subject", "admin@corp.test", "access", "interni"
        )
        assert linked.id == account.id
        assert account.workspace_role == "interni"
        manager.user_db.add_oauth_account.assert_awaited_once()

        manager.user_db.add_oauth_account.reset_mock()
        with pytest.raises(OnyxError):
            await manager.link_verified_google_account(
                account.id,
                "google",
                "other-subject",
                "other@corp.test",
                "access",
                "interni",
            )
        manager.user_db.add_oauth_account.assert_not_awaited()

        manager.user_db.add_oauth_account.side_effect = IntegrityError(
            "insert", {}, Exception()
        )
        with pytest.raises(OnyxError, match="Google identity is already linked"):
            await manager.link_verified_google_account(
                account.id,
                "google",
                "other-subject",
                "admin@corp.test",
                "access",
                "interni",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_map", [None, ""])
async def test_google_login_denies_missing_ou_role_map_before_account_creation(
    monkeypatch: pytest.MonkeyPatch, raw_map: str | None
) -> None:
    if raw_map is None:
        monkeypatch.delenv("OU_ROLE_MAP", raising=False)
    else:
        monkeypatch.setenv("OU_ROLE_MAP", raw_map)
    oauth_client = GoogleOAuth2("client", "secret")
    oauth_client.get_id_email = AsyncMock(return_value=("subject", "user@corp.test"))
    user_manager = MagicMock()
    user_manager.oauth_callback = AsyncMock()

    with pytest.raises(OnyxError, match="Workspace role map is not configured"):
        await complete_login_flow(
            oauth_client=oauth_client,
            token=OAuth2Token({"access_token": "access"}),
            state_data={},
            request=Request({"type": "http"}),
            user_manager=user_manager,
            backend=MagicMock(),
            strategy=MagicMock(),
            associate_by_email=True,
            is_verified_by_default=True,
            allowed_email_domains_override=["corp.test"],
        )

    oauth_client.get_id_email.assert_not_awaited()
    user_manager.oauth_callback.assert_not_awaited()


@pytest.mark.parametrize(
    "raw_map", ['{"/Staff": "unknown"}', '{"Staff": "interni"}', "{}", "not-json"]
)
def test_workspace_rejects_invalid_role_maps(
    monkeypatch: pytest.MonkeyPatch, raw_map: str
) -> None:
    monkeypatch.setenv("OU_ROLE_MAP", raw_map)
    with pytest.raises(OnyxError):
        workspace_role_map()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "directory_error",
    [OSError("offline"), KeyError("GOOGLE_DIRECTORY_SERVICE_ACCOUNT_FILE")],
)
async def test_workspace_directory_failure_denies_login_without_changing_account(
    monkeypatch: pytest.MonkeyPatch, directory_error: Exception
) -> None:
    monkeypatch.setenv("OU_ROLE_MAP", '{"/Staff": "interni"}')
    with (
        patch(
            "onyx.auth.google_workspace.id_token.verify_oauth2_token",
            return_value={
                "sub": "123",
                "email": "user@corp.test",
                "email_verified": True,
                "hd": "corp.test",
            },
        ),
        patch(
            "onyx.auth.google_workspace._directory_user", side_effect=directory_error
        ),
        patch("onyx.auth.google_workspace.logger.exception") as log_error,
    ):
        with pytest.raises(OnyxError):
            await admit_google_workspace_login(
                OAuth2Token({"id_token": "signed-token"}), "client", ["corp.test"]
            )
        log_error.assert_called_once_with("Workspace Directory lookup failed")
