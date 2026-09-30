"""Wiki.js ACL checks use the frontend, synthetic identities and paused fixtures."""

import json
import time
from collections.abc import Generator
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select, update

from onyx.cache.factory import get_cache_backend
from onyx.chat.chat_processing_checker import set_processing_status
from onyx.chat.stream_buffer import StreamBufferWriter, stream_buffer_key_pattern
from onyx.configs.constants import DocumentSource, MessageType
from onyx.connectors.models import InputType
from onyx.context.search.models import SearchDoc
from onyx.db.api_key import insert_api_key, remove_api_key
from onyx.db.chat import (
    create_db_search_doc,
    create_new_chat_message,
    get_or_create_root_message,
)
from onyx.db.connector_credential_pair import (
    add_credential_to_connector,
    delete_connector_credential_pair__no_commit,
)
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import AccessType, ConnectorCredentialPairStatus, SSOProviderType
from onyx.db.models import (
    ChatSession,
    ChatSessionSharedStatus,
    ConnectorCredentialPair,
    Document,
    DocumentByConnectorCredentialPair,
    OAuthAccount,
    SSOProvider,
    ToolCall,
    User,
    UserGroup,
)
from onyx.db.models import SearchDoc as DBSavedSearchDoc
from onyx.db.tools import get_tool_by_name
from onyx.kg.models import KGStage
from onyx.redis.redis_pool import get_redis_client
from onyx.server.api_key.models import APIKeyArgs
from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import AgentResponseDelta, Packet
from tests.external_dependency_unit.indexing_helpers import (
    cleanup_cc_pair,
    make_cc_pair,
)
from tests.integration.common_utils.http_client import client, set_test_client
from tests.integration.common_utils.managers.chat import ChatSessionManager
from tests.integration.common_utils.managers.connector import ConnectorManager
from tests.integration.common_utils.managers.credential import CredentialManager
from tests.integration.common_utils.test_models import (
    DATestCCPair,
    DATestUser,
    SimpleTestDocument,
)

FRONTEND_API = "http://localhost:3000/api"


def _route_through_frontend(request: httpx.Request) -> None:
    # Preserve escaping, including ingestion IDs containing encoded slashes.
    path = request.url.raw_path.split(b"?", 1)[0].decode("ascii")
    request.url = httpx.URL(f"{FRONTEND_API}{path.removeprefix('/api')}").copy_with(
        query=request.url.query
    )
    request.headers["Host"] = request.url.netloc.decode("ascii")


@pytest.fixture(scope="module", autouse=True)
def frontend_client(_test_client: httpx.Client) -> Generator[None, None, None]:
    with httpx.Client(
        timeout=120, event_hooks={"request": [_route_through_frontend]}
    ) as frontend:
        set_test_client(frontend)
        try:
            yield
        finally:
            set_test_client(_test_client)


@pytest.fixture
def workspace_admin(admin_user: DATestUser) -> Generator[DATestUser, None, None]:
    """Use a temporary API-key identity, leaving the existing admin unchanged."""
    with get_session_with_current_tenant() as db_session:
        admin_group_id = db_session.scalar(
            select(UserGroup.id).where(
                UserGroup.name == "Admin", UserGroup.is_default.is_(True)
            )
        )
        assert admin_group_id is not None
        api_key = insert_api_key(
            db_session,
            APIKeyArgs(name=f"wiki-acl-{uuid4()}", group_ids=[admin_group_id]),
            UUID(admin_user.id),
        )
    assert api_key.api_key is not None
    headers = {"Authorization": f"Bearer {api_key.api_key}"}
    provider_name = f"wiki-acl-{uuid4().hex}"
    subject = uuid4().hex
    email = f"{subject}@example.com"
    cache_key = (
        f"workspace-directory:{api_key.user_id}:{provider_name}:{subject}:{email}"
    )
    directory_cache = get_redis_client().raw_client
    try:
        with get_session_with_current_tenant() as db_session:
            # No real credentials: requests use only this identity's Directory cache.
            db_session.add(
                SSOProvider(
                    name=provider_name,
                    display_name="Wiki ACL fixture",
                    provider_type=SSOProviderType.GOOGLE_OAUTH,
                    allowed_email_domains=["example.com"],
                    config={
                        "client_id": "fixture-client",
                        "client_secret": "fixture-secret",
                        "ou_role_map": '{"/Fixtures":"interni"}',
                        "directory_service_account_json": json.dumps(
                            {
                                "type": "service_account",
                                "client_email": "fixture@example.com",
                                "private_key": "fixture-not-a-real-key",
                                "token_uri": "https://oauth2.googleapis.com/token",
                            }
                        ),
                    },
                )
            )
            user = db_session.get(User, api_key.user_id)
            assert user is not None
            user.email = email
            user.workspace_role = "interni"
            db_session.add(
                OAuthAccount(
                    user_id=user.id,
                    oauth_name=provider_name,
                    account_id=subject,
                    account_email=email,
                    access_token="fixture-token",
                    refresh_token="fixture-token",
                    expires_at=int(time.time()) + 3600,
                )
            )
            db_session.commit()
        directory_cache.set(
            cache_key,
            json.dumps(
                {
                    "id": subject,
                    "primaryEmail": email,
                    "suspended": False,
                    "archived": False,
                    "orgUnitPath": "/Fixtures",
                }
            ),
            ex=300,
        )
        yield DATestUser(
            id=str(api_key.user_id),
            email=email,
            password="unused",
            headers=headers,
            is_admin=True,
            is_active=True,
        )
    finally:
        directory_cache.delete(cache_key)
        with get_session_with_current_tenant() as db_session:
            remove_api_key(db_session, api_key.api_key_id)
            db_session.execute(
                delete(SSOProvider).where(SSOProvider.name == provider_name)
            )
            db_session.commit()


@pytest.fixture
def wikijs_connection(
    workspace_admin: DATestUser,
) -> Generator[tuple[DATestCCPair, dict[str, str]], None, None]:
    config = {
        "wiki_url": "https://wiki.example.invalid",
        "corpus_root": "/it",
        "excluded_folder_names": "[]",
        "visibility_folders": '{"Riservato":"interni"}',
        "role_visibility_map": '{"interni":["public","interni"],"tecnico":[],"agente":[],"concessionario":[]}',
    }
    connector = ConnectorManager.create(
        user_performing_action=workspace_admin,
        source=DocumentSource.WIKIJS,
        access_type=AccessType.PRIVATE,
        connector_specific_config=config,
    )
    credential = CredentialManager.create(
        user_performing_action=workspace_admin,
        source=DocumentSource.WIKIJS,
        credential_json={"wikijs_api_token": "fixture-token"},
        admin_public=False,
        curator_public=False,
    )
    cc_pair: DATestCCPair | None = None
    try:
        # Seed PAUSED so the workers cannot start a connector fetch before ingestion.
        with get_session_with_current_tenant() as db_session:
            user = db_session.get(User, UUID(workspace_admin.id))
            assert user is not None
            response = add_credential_to_connector(
                db_session=db_session,
                user=user,
                connector_id=connector.id,
                credential_id=credential.id,
                cc_pair_name=f"wiki-acl-{uuid4()}",
                access_type=AccessType.PRIVATE,
                groups=[],
                initial_status=ConnectorCredentialPairStatus.PAUSED,
            )
            assert response.success and isinstance(response.data, int)
            cc_pair = DATestCCPair(
                id=response.data,
                name=f"wiki-acl-{connector.id}",
                connector_id=connector.id,
                credential_id=credential.id,
                access_type=AccessType.PRIVATE,
                groups=[],
            )
        yield cc_pair, config
    finally:
        if cc_pair is not None:
            for document in cc_pair.documents:
                response = client.delete(
                    f"{FRONTEND_API}/onyx-api/ingestion/{quote(document.id, safe='')}",
                    headers=workspace_admin.headers,
                )
                response.raise_for_status()
            with get_session_with_current_tenant() as db_session:
                delete_connector_credential_pair__no_commit(
                    db_session, connector.id, credential.id
                )
                db_session.commit()
        CredentialManager.delete(credential, workspace_admin)
        ConnectorManager.delete(connector, workspace_admin)


def test_admin_can_update_role_visibility_configuration(
    workspace_admin: DATestUser,
    wikijs_connection: tuple[DATestCCPair, dict[str, str]],
) -> None:
    cc_pair, config = wikijs_connection
    connector = {
        "name": cc_pair.name,
        "source": DocumentSource.WIKIJS.value,
        "input_type": InputType.LOAD_STATE.value,
        "access_type": AccessType.PRIVATE.value,
        "connector_specific_config": config,
    }
    for bad_map in (None, "{}", '{"interni":["unknown"]}'):
        response = client.patch(
            f"{FRONTEND_API}/manage/admin/connector/{cc_pair.connector_id}",
            json={
                **connector,
                "connector_specific_config": {**config, "role_visibility_map": bad_map},
            },
            headers=workspace_admin.headers,
        )
        assert response.status_code == 400

    updated_map = '{"interni":["public"],"tecnico":[],"agente":[],"concessionario":[]}'
    config["role_visibility_map"] = updated_map
    response = client.patch(
        f"{FRONTEND_API}/manage/admin/connector/{cc_pair.connector_id}",
        json=connector,
        headers=workspace_admin.headers,
    )
    response.raise_for_status()
    assert (
        response.json()["connector_specific_config"]["role_visibility_map"]
        == updated_map
    )


def test_role_visibility_update_revokes_search_and_direct_access_without_reindexing(
    workspace_admin: DATestUser,
    wikijs_connection: tuple[DATestCCPair, dict[str, str]],
) -> None:
    cc_pair, config = wikijs_connection
    content = f"wiki-acl-{uuid4()}"
    ingestion = client.post(
        f"{FRONTEND_API}/onyx-api/ingestion",
        json={
            "cc_pair_id": cc_pair.id,
            "document": {
                "id": f"/it/Riservato/{uuid4()}",
                "source": DocumentSource.WIKIJS.value,
                "semantic_identifier": content,
                "sections": [
                    {
                        "text": content,
                        "link": "https://wiki.example.invalid/it/Riservato",
                    }
                ],
                "metadata": {"visibility": "interni"},
                "doc_metadata": {"wikijs_page_id": 1, "visibility": "interni"},
            },
        },
        headers=workspace_admin.headers,
    )
    ingestion.raise_for_status()
    document_id = ingestion.json()["document_id"]
    cc_pair.documents.append(SimpleTestDocument(id=document_id, content=content))

    search_url = f"{FRONTEND_API}/admin/search"
    search_body = {"query": content, "filters": {}}
    # Wait only for initial index refresh, never for a policy change.
    for _ in range(30):
        allowed_search = client.post(
            search_url, json=search_body, headers=workspace_admin.headers
        )
        allowed_search.raise_for_status()
        if any(
            result["document_id"] == document_id
            for result in allowed_search.json()["documents"]
        ):
            break
        time.sleep(1)
    else:
        pytest.fail("Wiki.js document did not become searchable within 30 seconds")

    chunk_params = {"document_id": document_id, "chunk_id": 0}
    for route in ("document-size-info", "chunk-info"):
        allowed_document = client.get(
            f"{FRONTEND_API}/document/{route}",
            params=chunk_params,
            headers=workspace_admin.headers,
        )
        allowed_document.raise_for_status()

    config["role_visibility_map"] = (
        '{"interni":[],"tecnico":[],"agente":[],"concessionario":[]}'
    )
    update = client.patch(
        f"{FRONTEND_API}/manage/admin/connector/{cc_pair.connector_id}",
        json={
            "name": cc_pair.name,
            "source": DocumentSource.WIKIJS.value,
            "input_type": InputType.LOAD_STATE.value,
            "access_type": AccessType.PRIVATE.value,
            "connector_specific_config": config,
        },
        headers=workspace_admin.headers,
    )
    update.raise_for_status()

    denied_search = client.post(
        search_url, json=search_body, headers=workspace_admin.headers
    )
    denied_search.raise_for_status()
    assert all(
        result["document_id"] != document_id
        for result in denied_search.json()["documents"]
    )
    for route in ("document-size-info", "chunk-info"):
        denied_chunk = client.get(
            f"{FRONTEND_API}/document/{route}",
            params=chunk_params,
            headers=workspace_admin.headers,
        )
        assert denied_chunk.status_code == 404


@pytest.fixture
def saved_wiki_connection(
    workspace_admin: DATestUser,
) -> Generator[ConnectorCredentialPair, None, None]:
    # Saved-answer checks need no index or embedding service.
    with get_session_with_current_tenant() as db_session:
        pair = make_cc_pair(db_session, DocumentSource.WIKIJS, commit=False)
        pair.status = ConnectorCredentialPairStatus.PAUSED
        pair.access_type = AccessType.PRIVATE
        pair.credential.user_id = UUID(workspace_admin.id)
        pair.connector.connector_specific_config = {
            "wiki_url": "https://wiki.example.invalid",
            "role_visibility_map": '{"interni":["interni"],"tecnico":[],"agente":[],"concessionario":[]}',
        }
        db_session.commit()
        try:
            yield pair
        finally:
            cleanup_cc_pair(db_session, pair)


@pytest.mark.parametrize("role", ["interni", "tecnico", "agente", "concessionario"])
def test_chat_answers_sources_and_tool_replay_obey_current_wiki_policy(
    workspace_admin: DATestUser,
    saved_wiki_connection: ConnectorCredentialPair,
    role: str,
) -> None:
    cc_pair = saved_wiki_connection
    chat = ChatSessionManager.create(workspace_admin, description="Wiki fixture answer")
    document_ids = [f"wiki-chat-{uuid4()}" for _ in range(2)]
    content = f"Restricted-excerpt-{uuid4()}"
    with get_session_with_current_tenant() as db_session:
        user = db_session.get(User, UUID(workspace_admin.id))
        assert user is not None
        provider = db_session.scalar(
            select(SSOProvider).where(
                SSOProvider.name == user.oauth_accounts[0].oauth_name
            )
        )
        assert provider is not None and provider.config is not None
        provider_config = provider.config.get_value(apply_mask=False)
        provider_config["ou_role_map"] = json.dumps({"/Fixtures": role})
        db_session.execute(
            update(SSOProvider)
            .where(SSOProvider.id == provider.id)
            .values(config=provider_config)
        )
        root = get_or_create_root_message(chat.id, db_session)
        message = create_new_chat_message(
            db_session=db_session,
            chat_session_id=chat.id,
            parent_message=root,
            message=f"{content} [1]",
            token_count=3,
            message_type=MessageType.ASSISTANT,
        )
        snapshots: list[DBSavedSearchDoc] = []
        for document_id in document_ids:
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
                    connector_id=cc_pair.connector_id,
                    credential_id=cc_pair.credential_id,
                    has_been_indexed=True,
                )
            )
            snapshots.append(
                create_db_search_doc(
                    SearchDoc(
                        document_id=document_id,
                        chunk_ind=0,
                        semantic_identifier="Wiki fixture",
                        blurb=content,
                        source_type=DocumentSource.WIKIJS,
                        boost=1,
                        hidden=False,
                        metadata={"visibility": ["interni"]},
                        match_highlights=[],
                    ),
                    db_session,
                    commit=False,
                )
            )
        message.search_docs = snapshots
        message.citations = {1: snapshots[0].id}
        tool = get_tool_by_name("internal_search", db_session)
        db_session.add(
            ToolCall(
                chat_session_id=chat.id,
                parent_chat_message_id=message.id,
                turn_number=0,
                tab_index=0,
                tool_id=tool.id,
                tool_call_id=uuid4().hex,
                tool_call_arguments={"queries": ["fixture"]},
                tool_call_response=content,
                tool_call_tokens=2,
                search_docs=snapshots,
            )
        )
        db_session.commit()
    try:
        url = f"{FRONTEND_API}/chat/get-chat-session/{chat.id}"
        initial = client.get(url, headers=workspace_admin.headers)
        if role == "interni":
            initial.raise_for_status()
            assert content in initial.text
            answer = next(
                msg
                for msg in initial.json()["messages"]
                if msg["message_type"] == "assistant"
            )
            # Only one citation supplies Sources; the tool retrieved two documents.
            assert answer["citations"] == {"1": document_ids[0]}
            packets = [
                packet["obj"] for turn in initial.json()["packets"] for packet in turn
            ]
            retrieved = next(
                packet
                for packet in packets
                if packet["type"] == "search_tool_documents_delta"
            )
            assert {doc["document_id"] for doc in retrieved["documents"]} == set(
                document_ids
            )
        else:
            assert initial.status_code == 403
            assert content not in initial.text

        # Simulate a policy revocation without indexing or changing the real Wiki.
        with get_session_with_current_tenant() as db_session:
            pair = db_session.scalar(
                select(ConnectorCredentialPair).where(
                    ConnectorCredentialPair.id == cc_pair.id
                )
            )
            assert pair is not None
            pair.connector.connector_specific_config = {
                **pair.connector.connector_specific_config,
                "role_visibility_map": '{"interni":[],"tecnico":[],"agente":[],"concessionario":[]}',
            }
            db_session.commit()
        for path in (
            url,
            f"{url}?is_shared=true",
            f"{FRONTEND_API}/chat/chat-session/{chat.id}/resume-stream",
        ):
            denied = client.get(path, headers=workspace_admin.headers)
            assert denied.status_code in (403, 404)
            assert content not in denied.text
        for path in ("get-user-chat-sessions", "search", "search?query=Wiki"):
            history = client.get(
                f"{FRONTEND_API}/chat/{path}", headers=workspace_admin.headers
            )
            history.raise_for_status()
            assert str(chat.id) not in history.text
        continuation = client.post(
            f"{FRONTEND_API}/chat/send-chat-message",
            json={
                "message": "Continue",
                "chat_session_id": str(chat.id),
                "parent_message_id": -1,
                "mock_llm_response": "This must not be generated",
            },
            headers=workspace_admin.headers,
        )
        assert content not in continuation.text
        assert "This must not be generated" not in continuation.text
        assert "Wiki documents are no longer authorized" in continuation.text
        fresh = ChatSessionManager.create(workspace_admin)
        new_chat = client.get(
            f"{FRONTEND_API}/chat/get-chat-session/{fresh.id}",
            headers=workspace_admin.headers,
        )
        new_chat.raise_for_status()
        # An in-flight buffer has no saved sources yet.
        cache = get_cache_backend()
        set_processing_status(fresh.id, cache, True, run_id=1)
        buffer = StreamBufferWriter(cache, fresh.id, run_id=1)
        buffer.append_line(
            json.dumps(
                {
                    "obj": {"type": "message_delta", "content": content},
                    "placement": {"turn_index": 0},
                }
            )
            + "\n"
        )
        buffer.mark_done()
        try:
            replay = client.get(
                f"{FRONTEND_API}/chat/chat-session/{fresh.id}/resume-stream?cursor=0",
                headers=workspace_admin.headers,
            )
            assert replay.status_code == 404
            assert content not in replay.text
            set_processing_status(fresh.id, cache, True, run_id=2)
            safe_buffer = StreamBufferWriter(cache, fresh.id, run_id=2)
            safe_buffer.append_packet(
                Packet(
                    placement=Placement(turn_index=0),
                    obj=AgentResponseDelta(content="Non-Wiki answer"),
                )
            )
            safe_buffer.mark_done()
            safe_replay = client.get(
                f"{FRONTEND_API}/chat/chat-session/{fresh.id}/resume-stream",
                headers=workspace_admin.headers,
            )
            safe_replay.raise_for_status()
            assert "Non-Wiki answer" in safe_replay.text
        finally:
            set_processing_status(fresh.id, cache, False)
            redis = get_redis_client()
            keys = list(redis.scan_iter(match=stream_buffer_key_pattern(fresh.id)))
            if keys:
                redis.delete(*keys)
    finally:
        with get_session_with_current_tenant() as db_session:
            db_session.execute(
                delete(ChatSession).where(
                    ChatSession.user_id == UUID(workspace_admin.id)
                )
            )
            db_session.execute(
                delete(DBSavedSearchDoc).where(
                    DBSavedSearchDoc.document_id.in_(document_ids)
                )
            )
            db_session.execute(
                delete(DocumentByConnectorCredentialPair).where(
                    DocumentByConnectorCredentialPair.id.in_(document_ids)
                )
            )
            db_session.execute(delete(Document).where(Document.id.in_(document_ids)))
            db_session.commit()


@pytest.mark.parametrize("new_role", ["tecnico", None])
def test_sourceless_chat_revocation_and_disabled_existing_share_links(
    workspace_admin: DATestUser, new_role: str | None
) -> None:
    chat = ChatSessionManager.create(workspace_admin, description="Sourceless fixture")
    content = f"Sourceless-answer-{uuid4()}"
    with get_session_with_current_tenant() as db_session:
        root = get_or_create_root_message(chat.id, db_session)
        create_new_chat_message(
            db_session=db_session,
            chat_session_id=chat.id,
            parent_message=root,
            message=content,
            token_count=1,
            message_type=MessageType.ASSISTANT,
        )
        saved_chat = db_session.get(ChatSession, chat.id)
        assert saved_chat is not None
        # Simulate a link saved before sharing was disabled.
        saved_chat.shared_status = ChatSessionSharedStatus.PUBLIC
        db_session.commit()
    url = f"{FRONTEND_API}/chat/get-chat-session/{chat.id}"
    initial = client.get(url, headers=workspace_admin.headers)
    initial.raise_for_status()
    assert content in initial.text
    for headers in (workspace_admin.headers, {}):
        shared = client.get(f"{url}?is_shared=true", headers=headers)
        assert shared.status_code in (401, 403)
        assert content not in shared.text
    sharing = client.patch(
        f"{FRONTEND_API}/chat/chat-session/{chat.id}",
        json={"sharing_status": "PUBLIC"},
        headers=workspace_admin.headers,
    )
    assert sharing.status_code == 403

    with get_session_with_current_tenant() as db_session:
        user = db_session.get(User, UUID(workspace_admin.id))
        assert user is not None
        provider = db_session.scalar(
            select(SSOProvider).where(
                SSOProvider.name == user.oauth_accounts[0].oauth_name
            )
        )
        assert provider is not None and provider.config is not None
        config = provider.config.get_value(apply_mask=False)
        config["ou_role_map"] = json.dumps(
            {"/Fixtures": new_role} if new_role else {"/Other": "interni"}
        )
        db_session.execute(
            update(SSOProvider)
            .where(SSOProvider.id == provider.id)
            .values(config=config)
        )
        db_session.commit()
    denied = client.get(url, headers=workspace_admin.headers)
    assert denied.status_code == 403
    assert content not in denied.text
    if new_role:
        authorized_chat = ChatSessionManager.create(workspace_admin)
        client.get(
            f"{FRONTEND_API}/chat/get-chat-session/{authorized_chat.id}",
            headers=workspace_admin.headers,
        ).raise_for_status()

    # Restoring the old role must not restore access to saved answers.
    with get_session_with_current_tenant() as db_session:
        config["ou_role_map"] = '{"/Fixtures":"interni"}'
        db_session.execute(
            update(SSOProvider)
            .where(SSOProvider.id == provider.id)
            .values(config=config)
        )
        db_session.commit()
    denied = client.get(url, headers=workspace_admin.headers)
    assert denied.status_code == 403
    assert content not in denied.text
    for path in ("get-user-chat-sessions", "search", "search?query=Sourceless"):
        history = client.get(
            f"{FRONTEND_API}/chat/{path}", headers=workspace_admin.headers
        )
        history.raise_for_status()
        assert str(chat.id) not in history.text
    continuation = client.post(
        f"{FRONTEND_API}/chat/send-chat-message",
        json={
            "message": "Continue",
            "chat_session_id": str(chat.id),
            "parent_message_id": -1,
            "mock_llm_response": "Forbidden continuation",
        },
        headers=workspace_admin.headers,
    )
    assert "Forbidden continuation" not in continuation.text
    assert "Chat access was revoked" in continuation.text
    fresh = ChatSessionManager.create(workspace_admin)
    client.get(
        f"{FRONTEND_API}/chat/get-chat-session/{fresh.id}",
        headers=workspace_admin.headers,
    ).raise_for_status()


def test_ingestion_reports_wikijs_indexing_failure(
    workspace_admin: DATestUser,
    wikijs_connection: tuple[DATestCCPair, dict[str, str]],
) -> None:
    cc_pair, _ = wikijs_connection
    response = client.post(
        f"{FRONTEND_API}/onyx-api/ingestion",
        json={
            "cc_pair_id": cc_pair.id,
            "document": {
                "id": f"wiki-invalid-{uuid4()}",
                "source": DocumentSource.WIKIJS.value,
                "semantic_identifier": "Invalid Wiki fixture",
                "sections": [
                    {"text": "Fixture content", "link": "https://example.com"}
                ],
                "metadata": {"visibility": "public"},
                "doc_metadata": {"wikijs_page_id": True, "visibility": "public"},
            },
        },
        headers=workspace_admin.headers,
    )
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"


def test_wikijs_page_without_indexed_visibility_denies_connector_owner(
    workspace_admin: DATestUser,
    wikijs_connection: tuple[DATestCCPair, dict[str, str]],
) -> None:
    cc_pair, _ = wikijs_connection
    content = f"wiki-acl-{uuid4()}"
    ingestion = client.post(
        f"{FRONTEND_API}/onyx-api/ingestion",
        json={
            "cc_pair_id": cc_pair.id,
            "document": {
                "id": f"/it/Test/{uuid4()}",
                "source": DocumentSource.WIKIJS.value,
                "semantic_identifier": content,
                "sections": [
                    {"text": content, "link": "https://wiki.example.invalid/it/Test"}
                ],
                "metadata": {"visibility": "public"},
                "doc_metadata": {"wikijs_page_id": 1},
            },
        },
        headers=workspace_admin.headers,
    )
    ingestion.raise_for_status()
    document_id = ingestion.json()["document_id"]
    cc_pair.documents.append(SimpleTestDocument(id=document_id, content=content))

    search = client.post(
        f"{FRONTEND_API}/admin/search",
        json={"query": content, "filters": {}},
        headers=workspace_admin.headers,
    )
    search.raise_for_status()
    assert all(
        result["document_id"] != document_id for result in search.json()["documents"]
    )
    for route in ("document-size-info", "chunk-info"):
        response = client.get(
            f"{FRONTEND_API}/document/{route}",
            params={"document_id": document_id, "chunk_id": 0},
            headers=workspace_admin.headers,
        )
        assert response.status_code == 404
