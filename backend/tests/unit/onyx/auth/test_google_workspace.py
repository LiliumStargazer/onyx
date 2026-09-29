"""Workspace login uses verified Google identity and Directory membership."""

from unittest.mock import patch

import pytest
from httpx_oauth.oauth2 import OAuth2Token

from onyx.auth.google_workspace import admit_google_workspace_login, workspace_role_map
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
async def test_workspace_directory_failure_denies_login_without_changing_account(
    monkeypatch: pytest.MonkeyPatch,
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
            "onyx.auth.google_workspace._directory_user", side_effect=OSError("offline")
        ),
    ):
        with pytest.raises(OnyxError):
            await admit_google_workspace_login(
                OAuth2Token({"id_token": "signed-token"}), "client", ["corp.test"]
            )
