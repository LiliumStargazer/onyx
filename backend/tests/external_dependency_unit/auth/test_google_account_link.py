"""Google linking must preserve the existing admin account."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onyx.auth.google_workspace import recheck_google_workspace_user
from onyx.auth.permissions import get_effective_permissions
from onyx.auth.users import UserManager
from onyx.db.engine.async_sql_engine import get_async_session_context_manager
from onyx.db.enums import Permission
from onyx.db.models import OAuthAccount, User
from tests.external_dependency_unit.conftest import create_test_user, delete_test_user


@pytest.mark.asyncio
@pytest.mark.usefixtures("tenant_context")
async def test_google_link_preserves_admin_identity_and_persists_directory_role(
    db_session: Session,
) -> None:
    admin = create_test_user(db_session, "google_link_admin", is_admin=True)
    permissions = get_effective_permissions(admin)
    assert Permission.FULL_ADMIN_PANEL_ACCESS in permissions
    subject = f"subject-{uuid4().hex}"
    try:
        async with get_async_session_context_manager() as session:
            manager = UserManager(SQLAlchemyUserDatabase(session, User, OAuthAccount))
            linked = await manager.link_verified_google_account(
                admin.id,
                "google",
                subject,
                admin.email,
                "test-access",
                "interni",
                refresh_token="test-refresh",
            )
            assert linked.id == admin.id
            assert (
                await manager.get_by_oauth_account("google", subject)
            ).id == admin.id

        db_session.expire_all()
        saved_admin = db_session.get(User, admin.id)
        assert saved_admin is not None
        assert saved_admin.email == admin.email
        assert saved_admin.workspace_role == "interni"
        assert get_effective_permissions(saved_admin) == permissions

        async with get_async_session_context_manager() as session:
            linked_admin = await session.get(User, admin.id)
            assert linked_admin is not None
            with (
                patch(
                    "onyx.auth.google_workspace._directory_user",
                    return_value={
                        "id": subject,
                        "primaryEmail": admin.email,
                        "orgUnitPath": "/Staff",
                        "suspended": False,
                        "archived": False,
                    },
                ),
                patch(
                    "onyx.auth.google_workspace.workspace_role_map",
                    return_value={"/Staff": "agente"},
                ),
                patch(
                    "onyx.auth.google_workspace.get_security_settings",
                    return_value=SimpleNamespace(valid_email_domains=["example.com"]),
                ),
                patch(
                    "onyx.auth.google_workspace.get_async_redis_connection",
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
            ):
                await recheck_google_workspace_user(linked_admin, session)
                assert linked_admin.workspace_role == "agente"

        db_session.expire_all()
        saved_admin = db_session.get(User, admin.id)
        assert saved_admin is not None
        assert saved_admin.workspace_role == "agente"
        accounts = db_session.scalars(
            select(OAuthAccount).where(OAuthAccount.__table__.c.user_id == admin.id)
        ).all()
        assert [(account.oauth_name, account.account_id) for account in accounts] == [
            ("google", subject)
        ]
    finally:
        db_session.execute(
            delete(OAuthAccount).where(OAuthAccount.__table__.c.user_id == admin.id)
        )
        delete_test_user(db_session, admin)
        db_session.commit()
