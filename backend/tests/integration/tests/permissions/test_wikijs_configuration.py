"""Wiki.js policy writes go through the frontend without starting a Wiki sync."""

import json
import time
from collections.abc import Generator
from uuid import UUID, uuid4

import httpx
import pytest

from onyx.configs.constants import DocumentSource
from onyx.connectors.models import InputType
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import AccessType
from onyx.db.models import User
from tests.integration.common_utils.http_client import client, set_test_client
from tests.integration.common_utils.managers.cc_pair import CCPairManager
from tests.integration.common_utils.test_models import (
    DATestAPIKey,
    DATestUser,
)

FRONTEND_API = "http://localhost:3000/api"


def _route_through_frontend(request: httpx.Request) -> None:
    request.url = httpx.URL(
        f"{FRONTEND_API}{request.url.path.removeprefix('/api')}"
    ).copy_with(query=request.url.query)
    request.headers["Host"] = request.url.netloc.decode("ascii")


@pytest.fixture(scope="module", autouse=True)
def frontend_client(_test_client: httpx.Client) -> Generator[None, None, None]:
    # Managers use absolute backend URLs; route them through the real frontend too.
    with httpx.Client(
        timeout=120, event_hooks={"request": [_route_through_frontend]}
    ) as frontend:
        set_test_client(frontend)
        try:
            yield
        finally:
            set_test_client(_test_client)


def test_admin_can_update_role_visibility_configuration(
    admin_user: DATestUser,
) -> None:
    initial_map = (
        '{"interni":["public","interni"],"tecnico":[],"agente":[],"concessionario":[]}'
    )
    updated_map = '{"interni":["public"],"tecnico":[],"agente":[],"concessionario":[]}'
    config: dict[str, str | None] = {
        "wiki_url": "https://wiki.example.invalid",
        "corpus_root": "/it",
        "excluded_folder_names": "[]",
        "visibility_folders": '{"Riservato":"interni"}',
        "role_visibility_map": initial_map,
    }
    connector = {
        "name": f"wiki-policy-{uuid4()}",
        "source": DocumentSource.WIKIJS.value,
        "input_type": InputType.LOAD_STATE.value,
        "access_type": AccessType.PRIVATE.value,
        "connector_specific_config": config,
    }
    create = client.post(
        f"{FRONTEND_API}/manage/admin/connector",
        json=connector,
        headers=admin_user.headers,
    )
    create.raise_for_status()
    connector_id = create.json()["id"]

    for bad_map in (None, "{}", '{"interni":["unknown"]}'):
        config["role_visibility_map"] = bad_map
        response = client.patch(
            f"{FRONTEND_API}/manage/admin/connector/{connector_id}",
            json=connector,
            headers=admin_user.headers,
        )
        assert response.status_code == 400

    config["role_visibility_map"] = updated_map
    response = client.patch(
        f"{FRONTEND_API}/manage/admin/connector/{connector_id}",
        json=connector,
        headers=admin_user.headers,
    )
    response.raise_for_status()
    assert (
        response.json()["connector_specific_config"]["role_visibility_map"]
        == updated_map
    )


def test_role_visibility_update_revokes_search_and_direct_access_without_reindexing(
    admin_user: DATestUser,
    api_key: DATestAPIKey,
) -> None:
    with get_session_with_current_tenant() as db_session:
        admin = db_session.get(User, UUID(admin_user.id))
        assert admin is not None
        previous_role = admin.workspace_role
        admin.workspace_role = "interni"
        db_session.commit()

    try:
        role_map = {
            "interni": ["interni"],
            "tecnico": [],
            "agente": [],
            "concessionario": [],
        }
        config = {
            "wiki_url": "https://wiki.example.invalid",
            "corpus_root": "/it",
            "excluded_folder_names": "[]",
            "visibility_folders": '{"Riservato":"interni"}',
            "role_visibility_map": json.dumps(role_map),
        }
        cc_pair = CCPairManager.create_from_scratch(
            user_performing_action=admin_user,
            source=DocumentSource.WIKIJS,
            access_type=AccessType.PUBLIC,
            connector_specific_config=config,
            credential_json={"wikijs_api_token": "fixture-token"},
        )
        CCPairManager.pause_cc_pair(cc_pair, admin_user)
        document_id = f"/it/Riservato/{uuid4()}"
        content = f"wiki-acl-{uuid4()}"
        ingestion = client.post(
            f"{FRONTEND_API}/onyx-api/ingestion",
            json={
                "cc_pair_id": cc_pair.id,
                "document": {
                    "id": document_id,
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
            headers=api_key.headers,
        )
        ingestion.raise_for_status()

        search_url = f"{FRONTEND_API}/admin/search"
        search_body = {"query": content, "filters": {}}
        # Wait only for initial index refresh, never for a policy change.
        for _ in range(30):
            allowed_search = client.post(
                search_url, json=search_body, headers=admin_user.headers
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
                headers=admin_user.headers,
            )
            allowed_document.raise_for_status()

        role_map["interni"] = []
        config["role_visibility_map"] = json.dumps(role_map)
        update = client.patch(
            f"{FRONTEND_API}/manage/admin/connector/{cc_pair.connector_id}",
            json={
                "name": cc_pair.name,
                "source": DocumentSource.WIKIJS.value,
                "input_type": InputType.LOAD_STATE.value,
                "access_type": AccessType.PUBLIC.value,
                "connector_specific_config": config,
            },
            headers=admin_user.headers,
        )
        update.raise_for_status()

        denied_search = client.post(
            search_url, json=search_body, headers=admin_user.headers
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
                headers=admin_user.headers,
            )
            assert denied_chunk.status_code == 404
    finally:
        with get_session_with_current_tenant() as db_session:
            admin = db_session.get(User, UUID(admin_user.id))
            assert admin is not None
            admin.workspace_role = previous_role
            db_session.commit()


def test_wikijs_page_without_indexed_visibility_denies_connector_owner(
    admin_user: DATestUser,
    api_key: DATestAPIKey,
) -> None:
    # Keep the required page ID but omit the indexed visibility.
    cc_pair = CCPairManager.create_from_scratch(
        user_performing_action=admin_user,
        source=DocumentSource.WIKIJS,
        access_type=AccessType.PUBLIC,
        connector_specific_config={
            "wiki_url": "https://wiki.example.invalid",
            "corpus_root": "/it",
            "excluded_folder_names": "[]",
            "visibility_folders": '{"Test":"public"}',
            "role_visibility_map": '{"interni":["public"],"tecnico":["public"],"agente":["public"],"concessionario":["public"]}',
        },
        credential_json={"wikijs_api_token": "fixture-token"},
    )
    CCPairManager.pause_cc_pair(cc_pair, admin_user)
    document_id = f"/it/Test/{uuid4()}"
    content = f"wiki-acl-{uuid4()}"
    ingestion = client.post(
        f"{FRONTEND_API}/onyx-api/ingestion",
        json={
            "cc_pair_id": cc_pair.id,
            "document": {
                "id": document_id,
                "source": DocumentSource.WIKIJS.value,
                "semantic_identifier": content,
                "sections": [
                    {"text": content, "link": "https://wiki.example.invalid/it/Test"}
                ],
                "metadata": {"visibility": "public"},
                "doc_metadata": {"wikijs_page_id": 1},
            },
        },
        headers=api_key.headers,
    )
    ingestion.raise_for_status()

    search = client.post(
        f"{FRONTEND_API}/admin/search",
        json={"query": content, "filters": {}},
        headers=admin_user.headers,
    )
    search.raise_for_status()
    assert all(
        result["document_id"] != document_id for result in search.json()["documents"]
    )
    for route in ("document-size-info", "chunk-info"):
        response = client.get(
            f"{FRONTEND_API}/document/{route}",
            params={"document_id": document_id, "chunk_id": 0},
            headers=admin_user.headers,
        )
        assert response.status_code == 404
