"""Workspace admission at Google OAuth login."""

import json
import os
from typing import Any
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token, service_account
from httpx_oauth.oauth2 import OAuth2Token
from requests import HTTPError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from onyx.db.enums import SSOProviderType
from onyx.db.models import User
from onyx.db.sso_provider import (
    GoogleProviderConfig,
    decrypt_directory_service_account_json,
    fetch_sso_provider_by_name_async,
    parse_ou_role_map,
)
from onyx.db.users import (
    persist_user_workspace_role_and_revoke_chats,
    revoke_oauth_account_chat_access,
    revoke_user_chat_access,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.redis.redis_pool import get_async_redis_connection
from onyx.server.security.store import get_security_settings
from onyx.utils.logger import setup_logger

logger = setup_logger()

_DIRECTORY_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
_DIRECTORY_CACHE_SECONDS = 300


def workspace_role_map() -> dict[str, str] | None:
    raw_map = os.environ.get("OU_ROLE_MAP")
    if raw_map is None or raw_map == "":
        return None
    try:
        return parse_ou_role_map(raw_map)
    except ValueError as exc:
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


def _directory_user(
    subject: str, provider_config: GoogleProviderConfig | None = None
) -> dict[str, Any]:
    if provider_config is None:
        credentials = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_DIRECTORY_SERVICE_ACCOUNT_FILE"],
            scopes=[_DIRECTORY_SCOPE],
        )
        if admin_email := os.environ.get("GOOGLE_DIRECTORY_ADMIN_EMAIL"):
            credentials = credentials.with_subject(admin_email)
    else:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(
                decrypt_directory_service_account_json(
                    provider_config.directory_service_account_json
                )
            ),
            scopes=[_DIRECTORY_SCOPE],
        )
    with AuthorizedSession(credentials) as session:
        response = session.get(
            "https://admin.googleapis.com/admin/directory/v1/users/"
            + quote(subject, safe=""),
            params={"projection": "basic"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


def _directory_account_was_deleted(error: HTTPError) -> bool:
    return (
        error.response is not None
        and error.response.status_code == OnyxErrorCode.NOT_FOUND.status_code
    )


async def admit_google_workspace_login(
    token: OAuth2Token,
    client_id: str,
    allowed_domains: list[str],
    provider_config: GoogleProviderConfig | None = None,
    *,
    oauth_name: str = "google",
) -> tuple[str, str, str]:
    """Return verified subject, email and content role, or deny before account creation."""
    role_map = (
        parse_ou_role_map(provider_config.ou_role_map)
        if provider_config is not None and provider_config.ou_role_map
        else workspace_role_map()
        if provider_config is None
        else None
    )
    if role_map is None:
        raise OnyxError(
            OnyxErrorCode.UNAUTHORIZED, "Workspace role map is not configured"
        )
    if (
        provider_config is not None
        and not provider_config.directory_service_account_json
    ):
        raise OnyxError(
            OnyxErrorCode.VALIDATION_ERROR,
            "Workspace Directory credentials are not configured",
        )
    if not allowed_domains:
        raise OnyxError(
            OnyxErrorCode.UNAUTHORIZED, "Workspace domain is not configured"
        )
    subject, email = await run_in_threadpool(
        _verify_workspace_identity, token, client_id, allowed_domains
    )
    try:
        directory_user = await run_in_threadpool(
            _directory_user, subject, provider_config
        )
        role = _active_directory_role(directory_user, subject, email, role_map)
    except OnyxError as exc:
        if exc.error_code is OnyxErrorCode.UNAUTHORIZED:
            await revoke_oauth_account_chat_access(oauth_name, subject)
        raise
    except Exception as exc:
        if isinstance(exc, HTTPError) and _directory_account_was_deleted(exc):
            await revoke_oauth_account_chat_access(oauth_name, subject)
            raise OnyxError(
                OnyxErrorCode.UNAUTHORIZED, "Workspace account was deleted"
            ) from exc
        logger.exception("Workspace Directory lookup failed")
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY, "Workspace Directory is unavailable"
        ) from exc
    return subject, email, role


def _active_directory_role(
    directory_user: dict[str, Any], subject: str, email: str, role_map: dict[str, str]
) -> str:
    if directory_user.get("id") != subject:
        raise OnyxError(
            OnyxErrorCode.UNAUTHENTICATED, "Workspace identity does not match"
        )
    if (
        directory_user.get("suspended") is not False
        or directory_user.get("archived") not in (False, None)
        or directory_user.get("deletionTime")
    ):
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, "Workspace account is not active")
    ou_path = directory_user.get("orgUnitPath")
    if not isinstance(ou_path, str):
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, "Workspace OU is not authorized")
    role = role_for_ou(ou_path, role_map)
    if str(directory_user.get("primaryEmail", "")).lower() != email.lower():
        # An email change alone requires login, not permanent chat revocation.
        raise OnyxError(
            OnyxErrorCode.UNAUTHENTICATED, "Workspace email changed; sign in again"
        )
    return role


async def recheck_google_workspace_user(user: User, db_session: AsyncSession) -> None:
    """Recheck linked Workspace membership on every request, with a short positive cache."""
    if not user.oauth_accounts:
        if user.workspace_role is not None:
            raise OnyxError(
                OnyxErrorCode.UNAUTHORIZED, "Workspace identity is not linked"
            )
        return
    for link in user.oauth_accounts:
        provider = await fetch_sso_provider_by_name_async(db_session, link.oauth_name)
        if provider is None and link.oauth_name != "google":
            continue
        if (
            provider is not None
            and provider.provider_type is not SSOProviderType.GOOGLE_OAUTH
        ):
            continue
        if user.workspace_role is None:
            await revoke_user_chat_access(db_session, user.id)
            raise OnyxError(
                OnyxErrorCode.UNAUTHORIZED, "Workspace role is not assigned"
            )
        if provider is not None and not provider.enabled:
            raise OnyxError(
                OnyxErrorCode.UNAUTHORIZED, "Workspace provider is disabled"
            )
        try:
            config = (
                GoogleProviderConfig.model_validate(
                    provider.config.get_value(apply_mask=False)
                )
                if provider is not None and provider.config
                else None
            )
            role_map = (
                parse_ou_role_map(config.ou_role_map)
                if config is not None
                else workspace_role_map()
            )
            domains = (
                provider.allowed_email_domains
                if provider is not None
                else get_security_settings().valid_email_domains
            )
            if (
                not role_map
                or not domains
                or not any(
                    user.email.lower().endswith("@" + domain.lower())
                    for domain in domains
                )
                or (config is not None and not config.directory_service_account_json)
            ):
                raise ValueError("Workspace configuration is incomplete")
        except ValueError as exc:
            raise OnyxError(
                OnyxErrorCode.UNAUTHORIZED, "Workspace configuration is invalid"
            ) from exc

        cache_key = f"workspace-directory:{user.id}:{link.oauth_name}:{link.account_id}:{user.email.lower()}"
        try:
            redis = await get_async_redis_connection()
            cached = await redis.get(cache_key)
            directory_user = (
                json.loads(cached)
                if cached is not None
                else await run_in_threadpool(_directory_user, link.account_id, config)
            )
            role = _active_directory_role(
                directory_user, link.account_id, user.email, role_map
            )
            if cached is None:
                await redis.set(
                    cache_key, json.dumps(directory_user), ex=_DIRECTORY_CACHE_SECONDS
                )
        except OnyxError as exc:
            if exc.error_code is OnyxErrorCode.UNAUTHORIZED:
                await revoke_user_chat_access(db_session, user.id)
            raise
        except HTTPError as exc:
            if _directory_account_was_deleted(exc):
                await revoke_user_chat_access(db_session, user.id)
                raise OnyxError(
                    OnyxErrorCode.UNAUTHORIZED, "Workspace account was deleted"
                ) from exc
            raise OnyxError(
                OnyxErrorCode.BAD_GATEWAY, "Workspace Directory is unavailable"
            ) from exc
        except Exception as exc:
            logger.warning("Workspace Directory recheck failed", exc_info=True)
            raise OnyxError(
                OnyxErrorCode.BAD_GATEWAY, "Workspace Directory is unavailable"
            ) from exc
        await persist_user_workspace_role_and_revoke_chats(db_session, user, role)
        return
    if user.workspace_role is not None:
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, "Workspace identity is not linked")
