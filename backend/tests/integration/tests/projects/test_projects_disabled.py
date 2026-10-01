"""Project chats remain stored but cannot be used through the frontend API."""

import os
from uuid import UUID

import httpx
import pytest
from sqlalchemy import delete

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.models import ChatSession, UserProject
from tests.integration.common_utils.test_models import DATestUser


@pytest.mark.parametrize("is_admin", [False, True])
def test_saved_project_chats_are_unavailable(
    basic_user: DATestUser, admin_user: DATestUser, is_admin: bool
) -> None:
    user = admin_user if is_admin else basic_user
    # Simulate saved data from before Projects was disabled. No indexing needed.
    with get_session_with_current_tenant() as db_session:
        project = UserProject(name="Simulated saved Project", user_id=UUID(user.id))
        db_session.add(project)
        db_session.flush()
        chat = ChatSession(
            user_id=UUID(user.id),
            persona_id=0,
            description="Simulated saved Project chat",
            project_id=project.id,
        )
        db_session.add(chat)
        db_session.commit()
        project_id, chat_id = project.id, chat.id

    try:
        with httpx.Client(
            base_url=os.environ.get("WEB_DOMAIN", "http://localhost:3000"),
            cookies=user.cookies,
            timeout=30,
        ) as frontend:
            for path in [
                f"/api/chat/get-chat-session/{chat_id}",
                f"/api/chat/chat-session/{chat_id}/resume-stream",
                f"/api/user/projects/session/{chat_id}/files",
                f"/api/user/projects/session/{chat_id}/token-count",
                f"/api/user/projects/{project_id}/details",
            ]:
                response = frontend.get(path)
                assert response.status_code == 403, (path, response.text)
            for stream in [True, False]:
                response = frontend.post(
                    "/api/chat/send-chat-message",
                    json={
                        "message": "Simulated",
                        "chat_session_id": str(chat_id),
                        "stream": stream,
                    },
                )
                assert response.status_code == 403, response.text
            history = frontend.get(
                "/api/chat/get-user-chat-sessions",
                params={
                    "only_non_project_chats": "false",
                    "include_failed_chats": "true",
                },
            )
            assert history.status_code == 200, history.text
            assert str(chat_id) not in {
                session["id"] for session in history.json()["sessions"]
            }
            for query in ["", "Simulated"]:
                search = frontend.get("/api/chat/search", params={"query": query})
                assert search.status_code == 200, search.text
                assert str(chat_id) not in search.text
            response = frontend.delete(f"/api/chat/delete-chat-session/{chat_id}")
            assert response.status_code == 403, response.text
            response = frontend.delete("/api/chat/delete-all-chat-sessions")
            assert response.status_code == 200, response.text
        with get_session_with_current_tenant() as db_session:
            saved_chat = db_session.get(ChatSession, chat_id)
            assert saved_chat is not None and not saved_chat.deleted
            assert saved_chat.project_id == project_id
            assert db_session.get(UserProject, project_id) is not None
    finally:
        with get_session_with_current_tenant() as db_session:
            db_session.execute(delete(ChatSession).where(ChatSession.id == chat_id))
            db_session.execute(delete(UserProject).where(UserProject.id == project_id))
            db_session.commit()
