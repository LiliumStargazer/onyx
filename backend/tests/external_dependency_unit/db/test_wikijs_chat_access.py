"""Saved Wiki excerpts must obey the current policy before replay or reuse."""

from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ee.onyx.db.query_history import (
    fetch_persisting_chat_session_by_id,
    get_page_of_chat_sessions,
)
from onyx.access.access import get_acl_for_user
from onyx.access.utils import prefix_external_group, prefix_user_email
from onyx.cache.factory import get_cache_backend
from onyx.chat.stream_buffer import StreamBufferWriter, read_stream_chunks
from onyx.configs.constants import DocumentSource, MessageType
from onyx.connectors.wikijs import wiki_visibility_group
from onyx.context.search.models import SearchDoc
from onyx.db.chat import (
    create_chat_session,
    create_db_search_doc,
    create_new_chat_message,
    get_chat_message,
    get_chat_session_by_id,
    get_chat_sessions_by_user,
    get_or_create_root_message,
    translate_db_search_doc_to_saved_search_doc,
)
from onyx.db.chat_search import search_chat_sessions
from onyx.db.enums import ConnectorCredentialPairStatus, IncognitoRecordMode
from onyx.db.models import (
    ChatSession,
    Document,
    DocumentByConnectorCredentialPair,
    ToolCall,
)
from onyx.db.models import SearchDoc as DBSearchDoc
from onyx.error_handling.exceptions import OnyxError
from onyx.kg.models import KGStage
from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import OpenUrlDocuments, Packet
from shared_configs.contextvars import CURRENT_CONTENT_FREE_SESSION_ID_CONTEXTVAR
from tests.external_dependency_unit.conftest import create_test_user, delete_test_user
from tests.external_dependency_unit.indexing_helpers import (
    cleanup_cc_pair,
    make_cc_pair,
)


@pytest.mark.parametrize(
    "snapshot_link",
    ["message", "tool", "citation", "shared", "inflight", "content_free"],
)
def test_revoked_wiki_snapshots_block_chat_replay_and_reuse(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    snapshot_link: str,
) -> None:
    user = create_test_user(db_session, "wiki_chat", assign_default_group=False)
    user.workspace_role = "interni"
    pair = make_cc_pair(db_session, DocumentSource.WIKIJS, commit=False)
    pair.status = ConnectorCredentialPairStatus.PAUSED
    pair.connector.connector_specific_config = {
        "role_visibility_map": '{"interni":["interni"],"tecnico":[],"agente":[],"concessionario":[]}'
    }
    document_id = f"wiki-chat-{uuid4()}"
    db_session.add(
        Document(
            id=document_id,
            semantic_id=document_id,
            kg_stage=KGStage.NOT_STARTED,
            doc_metadata={"visibility": "interni"},
        )
    )
    db_session.add(
        DocumentByConnectorCredentialPair(
            id=document_id,
            connector_id=pair.connector_id,
            credential_id=pair.credential_id,
            has_been_indexed=True,
        )
    )
    db_session.commit()
    chat = create_chat_session(
        db_session,
        "Restricted answer",
        user.id,
        None,
        incognito_record_mode=IncognitoRecordMode.USAGE_ONLY
        if snapshot_link == "content_free"
        else None,
    )
    root = get_or_create_root_message(chat.id, db_session)
    message = create_new_chat_message(
        db_session=db_session,
        chat_session_id=chat.id,
        parent_message=root,
        message=""
        if snapshot_link in ("inflight", "content_free")
        else "Restricted answer",
        token_count=2,
        message_type=MessageType.ASSISTANT,
    )
    snapshot = create_db_search_doc(
        SearchDoc(
            document_id=document_id,
            chunk_ind=0,
            semantic_identifier="Restricted page",
            blurb="Restricted excerpt",
            source_type=DocumentSource.WEB
            if snapshot_link == "shared"
            else DocumentSource.WIKIJS,
            boost=1,
            hidden=False,
            metadata={"visibility": ["interni"]},
            match_highlights=[],
        ),
        db_session,
    )
    if snapshot_link == "tool":
        # Includes tools nested under an agent, without message-level sources.
        db_session.add(
            ToolCall(
                chat_session_id=chat.id,
                parent_chat_message_id=None,
                turn_number=0,
                tab_index=0,
                tool_id=1,
                tool_call_id=uuid4().hex,
                tool_call_arguments={},
                tool_call_response="Restricted tool output",
                tool_call_tokens=2,
                search_docs=[snapshot],
            )
        )
    elif snapshot_link not in ("inflight", "content_free"):
        if snapshot_link in ("message", "shared"):
            message.search_docs = [snapshot]
        message.citations = {1: snapshot.id}
    db_session.commit()
    cache = get_cache_backend()
    original_refs = list(message.search_docs)
    buffer = StreamBufferWriter(cache, chat.id, run_id=message.id, delete_on_done=True)
    try:
        packet = Packet(
            placement=Placement(turn_index=0),
            obj=OpenUrlDocuments(
                documents=[translate_db_search_doc_to_saved_search_doc(snapshot)]
            ),
        )
        if snapshot_link == "content_free":
            wiki_acl = prefix_external_group(
                wiki_visibility_group(pair.connector_id, "interni")
            )
            assert wiki_acl in get_acl_for_user(user, db_session)
            token = CURRENT_CONTENT_FREE_SESSION_ID_CONTEXTVAR.set(str(chat.id))
            try:
                acl = get_acl_for_user(user, db_session)
                assert wiki_acl not in acl
                assert prefix_user_email(user.email) in acl
            finally:
                CURRENT_CONTENT_FREE_SESSION_ID_CONTEXTVAR.reset(token)
            with pytest.raises(OnyxError):
                buffer.append_packet(packet)
            db_session.refresh(message)
            assert (
                not message.search_docs
                and not message.citations
                and message.message == ""
            )
            return
        buffer.append_packet(packet)
        buffer.flush()
        cached = read_stream_chunks(cache, chat.id, message.id, 0)
        assert cached is not None and cached.has_wiki_documents is True
        db_session.refresh(message)
        if snapshot_link != "inflight":
            # Legacy chats rely on their original message, citation or tool links.
            message.search_docs = original_refs
            db_session.commit()
        else:
            assert message.search_docs and not message.citations
            document = db_session.get(Document, document_id)
            assert document is not None
            document.doc_metadata = {"visibility": "tecnico"}
            db_session.commit()
            with pytest.raises(OnyxError):
                get_chat_session_by_id(chat.id, user.id, db_session)
            document.doc_metadata = {"visibility": "interni"}
            db_session.commit()
        assert get_chat_session_by_id(chat.id, user.id, db_session).id == chat.id
        assert get_chat_message(message.id, user.id, db_session).id == message.id
        assert (
            fetch_persisting_chat_session_by_id(
                chat.id, db_session, viewer_id=user.id
            ).id
            == chat.id
        )
        with pytest.raises(ValueError):
            fetch_persisting_chat_session_by_id(chat.id, db_session)
        assert chat.id in {
            session.id
            for session in get_page_of_chat_sessions(
                None, None, db_session, 0, 100, viewer_id=user.id
            )
        }

        pair.connector.connector_specific_config = {
            "role_visibility_map": '{"interni":[],"tecnico":[],"agente":[],"concessionario":[]}'
        }
        db_session.commit()
        for read in (
            lambda: get_chat_session_by_id(chat.id, user.id, db_session),
            lambda: get_chat_message(message.id, user.id, db_session),
        ):
            with pytest.raises(OnyxError):
                read()
        assert not get_chat_sessions_by_user(
            user.id, False, db_session, include_failed_chats=True
        )
        assert search_chat_sessions(user.id, db_session)[0] == []
        with pytest.raises(ValueError):
            fetch_persisting_chat_session_by_id(chat.id, db_session, viewer_id=user.id)
        assert chat.id not in {
            session.id
            for session in get_page_of_chat_sessions(
                None, None, db_session, 0, 100, viewer_id=user.id
            )
        }

        # A new chat remains usable; the saved answer is not deleted.
        fresh = create_chat_session(db_session, "New chat", user.id, None)
        assert get_chat_session_by_id(fresh.id, user.id, db_session).id == fresh.id
        assert db_session.get(ChatSession, chat.id) is not None
    finally:
        buffer.mark_done()
        db_session.rollback()
        db_session.execute(delete(ChatSession).where(ChatSession.user_id == user.id))
        db_session.execute(
            delete(DBSearchDoc).where(DBSearchDoc.document_id == document_id)
        )
        db_session.commit()
        cleanup_cc_pair(db_session, pair)
        delete_test_user(db_session, user)
        db_session.commit()
