"""Saved chat access follows Workspace role changes, even without sources."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import OAuth2Token
from requests import HTTPError, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.requests import Request

from onyx.access.access import user_can_access_chat_file
from onyx.auth.google_workspace import recheck_google_workspace_user
from onyx.auth.users import UserManager, complete_login_flow
from onyx.configs.constants import (
    CHAT_SESSION_ID_FILE_METADATA_KEY,
    FileOrigin,
    MessageType,
)
from onyx.db.chat import (
    create_chat_session,
    create_new_chat_message,
    get_chat_session_by_id,
    get_chat_sessions_by_user,
    get_or_create_root_message,
    update_chat_session,
)
from onyx.db.chat_search import search_chat_sessions
from onyx.db.engine.async_sql_engine import (
    get_async_session_context_manager,
    reset_sqlalchemy_async_engine,
)
from onyx.db.enums import SSOProviderType
from onyx.db.models import (
    ChatSessionSharedStatus,
    FileRecord,
    OAuthAccount,
    SSOProvider,
    User,
)
from onyx.db.sso_provider import GoogleProviderConfig
from onyx.db.users import persist_user_workspace_role_and_revoke_chats
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.models import ChatFileType
from tests.external_dependency_unit.conftest import create_test_user, delete_test_user


@pytest.mark.asyncio
async def test_role_change_permanently_blocks_sourceless_chats_but_allows_new_chats(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, "chat_role", assign_default_group=False)
    user.workspace_role = "interni"
    db_session.commit()
    chat = create_chat_session(db_session, "Sourceless answer", user.id, None)
    try:
        async with get_async_session_context_manager() as role_session:
            linked_user = await role_session.get(User, user.id)
            assert linked_user is not None
            await persist_user_workspace_role_and_revoke_chats(
                role_session, linked_user, "tecnico"
            )
        db_session.expire_all()
        with pytest.raises(OnyxError):
            get_chat_session_by_id(chat.id, user.id, db_session)
        assert get_chat_sessions_by_user(user.id, False, db_session) == []
        assert search_chat_sessions(user.id, db_session)[0] == []
        assert search_chat_sessions(user.id, db_session, "Sourceless")[0] == []
        fresh = create_chat_session(db_session, "New answer", user.id, None)
        assert get_chat_session_by_id(fresh.id, user.id, db_session).id == fresh.id
        async with get_async_session_context_manager() as role_session:
            linked_user = await role_session.get(User, user.id)
            assert linked_user is not None
            await persist_user_workspace_role_and_revoke_chats(
                role_session, linked_user, "interni"
            )
        db_session.expire_all()
        for session_id in (chat.id, fresh.id):
            with pytest.raises(OnyxError):
                get_chat_session_by_id(session_id, user.id, db_session)
    finally:
        delete_test_user(db_session, user)
        db_session.commit()
        await reset_sqlalchemy_async_engine()


@pytest.mark.asyncio
async def test_concurrent_same_role_change_keeps_new_chats_accessible(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, "concurrent_role", assign_default_group=False)
    user.workspace_role = "interni"
    db_session.commit()
    old_chat = create_chat_session(db_session, "Old answer", user.id, None)
    try:
        async with (
            get_async_session_context_manager() as first_session,
            get_async_session_context_manager() as second_session,
        ):
            first_user = await first_session.get(User, user.id)
            second_user = await second_session.get(User, user.id)
            assert first_user is not None and second_user is not None
            await persist_user_workspace_role_and_revoke_chats(
                first_session, first_user, "tecnico"
            )
            fresh = create_chat_session(db_session, "New answer", user.id, None)
            assert get_chat_session_by_id(fresh.id, user.id, db_session).id == fresh.id
            await persist_user_workspace_role_and_revoke_chats(
                second_session, second_user, "tecnico"
            )
        db_session.expire_all()
        assert get_chat_session_by_id(fresh.id, user.id, db_session).id == fresh.id
        with pytest.raises(OnyxError):
            get_chat_session_by_id(old_chat.id, user.id, db_session)
    finally:
        delete_test_user(db_session, user)
        db_session.commit()
        await reset_sqlalchemy_async_engine()


def test_chat_sharing_denies_creation_and_existing_links(db_session: Session) -> None:
    user = create_test_user(db_session, "chat_sharing", assign_default_group=False)
    chat = create_chat_session(db_session, "Existing shared answer", user.id, None)
    chat.shared_status = ChatSessionSharedStatus.PUBLIC
    other_user = create_test_user(
        db_session, "share_reader", assign_default_group=False
    )
    attachment_id, image_id = str(uuid4()), str(uuid4())
    create_new_chat_message(
        db_session=db_session,
        chat_session_id=chat.id,
        parent_message=get_or_create_root_message(chat.id, db_session),
        message="Shared attachment",
        token_count=1,
        message_type=MessageType.ASSISTANT,
        files=[{"id": attachment_id, "type": ChatFileType.PLAIN_TEXT}],
    )
    db_session.add(
        FileRecord(
            file_id=image_id,
            file_origin=FileOrigin.CHAT_IMAGE_GEN,
            file_metadata={CHAT_SESSION_ID_FILE_METADATA_KEY: str(chat.id)},
            bucket_name="fixture",
            object_key="fixture",
        )
    )
    db_session.commit()
    try:
        for file_id in (attachment_id, image_id):
            assert user_can_access_chat_file(file_id, user, db_session)
            assert not user_can_access_chat_file(file_id, other_user, db_session)
        with pytest.raises(OnyxError):
            get_chat_session_by_id(chat.id, user.id, db_session, is_shared=True)
        with pytest.raises(OnyxError):
            update_chat_session(
                db_session,
                user.id,
                chat.id,
                sharing_status=ChatSessionSharedStatus.PUBLIC,
            )
        assert get_chat_session_by_id(chat.id, user.id, db_session).id == chat.id
    finally:
        db_session.execute(delete(FileRecord).where(FileRecord.file_id == image_id))
        delete_test_user(db_session, user, other_user)
        db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("request_kind", ["protected_request", "login"])
@pytest.mark.parametrize(
    "directory_state",
    [
        "suspended",
        "archived",
        "unmapped",
        "deleted",
        "outage",
        "renamed",
        "identity_mismatch",
        "renamed_unmapped",
    ],
)
async def test_directory_recovery_preserves_chats_only_without_role_loss(
    db_session: Session,
    directory_state: str,
    request_kind: str,
    tenant_context: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, "revoked_chat", assign_default_group=False)
    user.workspace_role = "interni"
    provider_name = str(uuid4())
    subject = str(uuid4())
    provider = SSOProvider(
        name=provider_name,
        display_name="Fixture",
        provider_type=SSOProviderType.GOOGLE_OAUTH,
        allowed_email_domains=["example.com"],
        config={
            "client_id": "fixture",
            "client_secret": "fixture",
            "ou_role_map": '{"/Fixtures":"interni"}',
            "directory_service_account_json": json.dumps(
                {
                    "type": "service_account",
                    "client_email": "fixture@example.com",
                    "private_key": "fixture-not-a-key",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            ),
        },
    )
    assert provider.config is not None
    google_config = GoogleProviderConfig.model_validate(
        provider.config.get_value(apply_mask=False)
    )
    db_session.add(provider)
    user.oauth_accounts.append(
        OAuthAccount(
            oauth_name=provider_name,
            account_id=subject,
            account_email=user.email,
            access_token="fixture",
            refresh_token="fixture",
        )
    )
    db_session.commit()
    chat = create_chat_session(db_session, "Saved answer", user.id, None)
    directory_user = {
        "id": subject,
        "primaryEmail": user.email,
        "orgUnitPath": "/Fixtures",
        "suspended": False,
        "archived": False,
    }
    if directory_state in ("suspended", "archived"):
        directory_user[directory_state] = True
    elif directory_state == "unmapped":
        directory_user["orgUnitPath"] = "/Other"
    elif directory_state == "renamed":
        directory_user["primaryEmail"] = f"renamed-{user.email}"
    elif directory_state == "identity_mismatch":
        directory_user["id"] = f"other-{subject}"
    elif directory_state == "renamed_unmapped":
        directory_user.update(
            primaryEmail=f"renamed-{user.email}", orgUnitPath="/Other"
        )
    response = Response()
    response.status_code = 404
    failure = (
        HTTPError(response=response)
        if directory_state == "deleted"
        else OSError("offline")
    )
    redis = AsyncMock()
    redis.get.return_value = None
    try:
        async with get_async_session_context_manager() as role_session:
            linked_user = await role_session.get(User, user.id)
            assert linked_user is not None
            with (
                patch(
                    "onyx.auth.google_workspace.id_token.verify_oauth2_token",
                    return_value={
                        "sub": subject,
                        "email": user.email,
                        "email_verified": True,
                        "hd": "example.com",
                    },
                ),
                patch(
                    "onyx.auth.google_workspace.get_async_redis_connection",
                    return_value=redis,
                ),
                patch(
                    "onyx.auth.google_workspace._directory_user",
                    return_value=directory_user,
                    side_effect=failure
                    if directory_state in ("deleted", "outage")
                    else None,
                ) as directory,
            ):
                with pytest.raises(OnyxError):
                    if request_kind == "login":
                        await complete_login_flow(
                            oauth_client=GoogleOAuth2(
                                "fixture", "fixture", name=provider_name
                            ),
                            token=OAuth2Token({"id_token": "signed-fixture"}),
                            state_data={},
                            request=Request({"type": "http"}),
                            user_manager=UserManager(
                                SQLAlchemyUserDatabase(role_session, User, OAuthAccount)
                            ),
                            backend=MagicMock(),
                            strategy=MagicMock(),
                            associate_by_email=False,
                            is_verified_by_default=True,
                            allowed_email_domains_override=["example.com"],
                            google_provider_config=google_config,
                        )
                    else:
                        await recheck_google_workspace_user(linked_user, role_session)
                directory.side_effect = None
                directory_user.update(
                    id=subject,
                    primaryEmail=user.email,
                    suspended=False,
                    archived=False,
                    orgUnitPath="/Fixtures",
                )
                await recheck_google_workspace_user(linked_user, role_session)
        db_session.expire_all()
        if directory_state in ("outage", "renamed", "identity_mismatch"):
            assert get_chat_session_by_id(chat.id, user.id, db_session).id == chat.id
        else:
            with pytest.raises(OnyxError):
                get_chat_session_by_id(chat.id, user.id, db_session)
            fresh = create_chat_session(db_session, "New answer", user.id, None)
            assert get_chat_session_by_id(fresh.id, user.id, db_session).id == fresh.id
    finally:
        delete_test_user(db_session, user)
        db_session.delete(provider)
        db_session.commit()
        await reset_sqlalchemy_async_engine()
