"""Stored Project data for tests that cannot create it through disabled APIs."""

from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import delete

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import IncognitoRecordMode, UserFileStatus
from onyx.db.models import ChatSession, UserFile, UserProject


@contextmanager
def seed_saved_project_chat(
    user_id: UUID, record_mode: IncognitoRecordMode | None = None
) -> Generator[tuple[int, UUID, UUID], None, None]:
    """Seed historical data without indexing, then remove only the seeded rows."""
    with get_session_with_current_tenant() as db_session:
        project = UserProject(name="Simulated saved Project", user_id=user_id)
        db_session.add(project)
        db_session.flush()
        chat = ChatSession(
            user_id=user_id,
            persona_id=0,
            description="Simulated saved Project chat",
            project_id=project.id,
            incognito_record_mode=record_mode,
        )
        db_session.add(chat)
        db_session.flush()
        user_file = UserFile(
            id=uuid4(),
            user_id=user_id,
            file_id=str(uuid4()),
            name="simulated.txt",
            file_type="text/plain",
            status=UserFileStatus.COMPLETED,
            incognito=record_mode is not None,
            incognito_session_id=chat.id if record_mode is not None else None,
        )
        db_session.add(user_file)
        project_id, chat_id, file_id = project.id, chat.id, user_file.id
        db_session.commit()

    try:
        yield project_id, chat_id, file_id
    finally:
        with get_session_with_current_tenant() as db_session:
            db_session.execute(delete(UserFile).where(UserFile.id == file_id))
            db_session.execute(delete(ChatSession).where(ChatSession.id == chat_id))
            db_session.execute(delete(UserProject).where(UserProject.id == project_id))
            db_session.commit()


def assert_saved_project_chat_preserved(
    project_id: int, chat_id: UUID, file_id: UUID
) -> None:
    """Check stored rows even though the Project API must deny access."""
    with get_session_with_current_tenant() as db_session:
        saved_chat = db_session.get(ChatSession, chat_id)
        assert saved_chat is not None and not saved_chat.deleted
        assert saved_chat.project_id == project_id
        assert db_session.get(UserProject, project_id) is not None
        saved_file = db_session.get(UserFile, file_id)
        assert saved_file is not None
        assert saved_file.status == UserFileStatus.COMPLETED
