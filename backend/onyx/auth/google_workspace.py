"""Workspace admission at Google OAuth login. Enabled by OU_ROLE_MAP."""

import json
import os
from typing import Any
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token, service_account
from httpx_oauth.oauth2 import OAuth2Token
from starlette.concurrency import run_in_threadpool

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

_DIRECTORY_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
_CONTENT_ROLES = frozenset({"interni", "tecnico", "agente", "concessionario"})


def workspace_role_map() -> dict[str, str] | None:
    raw_map = os.environ.get("OU_ROLE_MAP")
    if raw_map is None or raw_map == "":
        return None
    try:
        role_map = json.loads(raw_map)
        if (
            not isinstance(role_map, dict)
            or not role_map
            or any(
                not isinstance(path, str)
                or not path.startswith("/")
                or not isinstance(role, str)
                or role not in _CONTENT_ROLES
                for path, role in role_map.items()
            )
        ):
            raise ValueError("invalid OU_ROLE_MAP")
        return role_map
    except (ValueError, TypeError) as exc:
        raise OnyxError(OnyxErrorCode.VALIDATION_ERROR, "Invalid OU_ROLE_MAP") from exc


def role_for_ou(ou_path: str, role_map: dict[str, str]) -> str:
    path = ou_path.rstrip("/") or "/"
    while True:
        if path in role_map:
            return role_map[path]
        if path == "/":
            break
        path = path.rpartition("/")[0] or "/"
    raise OnyxError(OnyxErrorCode.UNAUTHORIZED, "Workspace OU is not authorized")


def _verify_workspace_identity(
    token: OAuth2Token, client_id: str, allowed_domains: list[str]
) -> tuple[str, str]:
    try:
        claims = id_token.verify_oauth2_token(token["id_token"], Request(), client_id)
    except (ValueError, KeyError) as exc:
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, "Invalid Google identity") from exc
    subject = claims.get("sub")
    email = claims.get("email")
    hosted_domain = claims.get("hd")
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(email, str)
        or claims.get("email_verified") is not True
        or not isinstance(hosted_domain, str)
        or hosted_domain.lower() not in {domain.lower() for domain in allowed_domains}
        or email.rpartition("@")[2].lower() != hosted_domain.lower()
    ):
        raise OnyxError(
            OnyxErrorCode.UNAUTHORIZED, "Google Workspace identity is not authorized"
        )
    return subject, email


def _directory_user(subject: str) -> dict[str, Any]:
    key_path = os.environ["GOOGLE_DIRECTORY_SERVICE_ACCOUNT_FILE"]
    credentials = service_account.Credentials.from_service_account_file(
        key_path, scopes=[_DIRECTORY_SCOPE]
    )
    if admin_email := os.environ.get("GOOGLE_DIRECTORY_ADMIN_EMAIL"):
        credentials = credentials.with_subject(admin_email)
    with AuthorizedSession(credentials) as session:
        response = session.get(
            "https://admin.googleapis.com/admin/directory/v1/users/"
            + quote(subject, safe=""),
            params={"projection": "basic"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


async def admit_google_workspace_login(
    token: OAuth2Token, client_id: str, allowed_domains: list[str]
) -> tuple[str, str, str]:
    """Return verified subject, email and content role, or deny before account creation."""
    if not allowed_domains:
        raise OnyxError(
            OnyxErrorCode.UNAUTHORIZED, "Workspace domain is not configured"
        )
    subject, email = await run_in_threadpool(
        _verify_workspace_identity, token, client_id, allowed_domains
    )
    try:
        directory_user = await run_in_threadpool(_directory_user, subject)
    except Exception as exc:
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY, "Workspace Directory is unavailable"
        ) from exc
    if (
        directory_user.get("id") != subject
        or directory_user.get("suspended") is True
        or directory_user.get("archived") is True
        or directory_user.get("deletionTime")
        or str(directory_user.get("primaryEmail", "")).lower() != email.lower()
    ):
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, "Workspace account is not active")
    ou_path = directory_user.get("orgUnitPath")
    if not isinstance(ou_path, str):
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, "Workspace OU is not authorized")
    role_map = workspace_role_map()
    if role_map is None:
        raise OnyxError(
            OnyxErrorCode.UNAUTHORIZED, "Workspace role map is not configured"
        )
    return subject, email, role_for_ou(ou_path, role_map)
