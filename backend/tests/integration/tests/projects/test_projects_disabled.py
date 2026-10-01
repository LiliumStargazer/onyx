"""Project chats remain stored but cannot be used through the frontend API."""

import os
from uuid import UUID

import httpx
import pytest

from onyx.db.enums import IncognitoRecordMode
from onyx.db.seeding.project_chat_seeding import (
    assert_saved_project_chat_preserved,
    seed_saved_project_chat,
)
from tests.integration.common_utils.test_models import DATestUser


@pytest.mark.parametrize("is_admin", [False, True])
@pytest.mark.parametrize("record_mode", [None, *IncognitoRecordMode])
def test_saved_project_chats_are_unavailable(
    basic_user: DATestUser,
    admin_user: DATestUser,
    is_admin: bool,
    record_mode: IncognitoRecordMode | None,
) -> None:
    user = admin_user if is_admin else basic_user
    with seed_saved_project_chat(UUID(user.id), record_mode) as (
        project_id,
        chat_id,
        user_file_id,
    ):
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
        assert_saved_project_chat_preserved(project_id, chat_id, user_file_id)
