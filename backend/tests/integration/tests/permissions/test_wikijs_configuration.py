"""Wiki.js policy writes go through the frontend without starting a Wiki sync."""

from uuid import uuid4

from onyx.configs.constants import DocumentSource
from onyx.connectors.models import InputType
from onyx.db.enums import AccessType
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.cc_pair import CCPairManager
from tests.integration.common_utils.test_models import (
    DATestAPIKey,
    DATestLLMProvider,
    DATestUser,
)

FRONTEND_API = "http://localhost:3000/api"


def test_admin_can_change_role_visibility_without_reindexing(
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


def test_wikijs_page_without_indexed_visibility_denies_connector_owner(
    admin_user: DATestUser,
    api_key: DATestAPIKey,
    llm_provider: DATestLLMProvider,  # noqa: ARG001
) -> None:
    # Ingestion omits doc_metadata, so this is a legacy page without a verified visibility.
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
            },
        },
        headers=api_key.headers,
    )
    ingestion.raise_for_status()

    search = client.post(
        f"{FRONTEND_API}/search",
        json={"query": content},
        headers=admin_user.headers,
    )
    search.raise_for_status()
    assert all(
        result["document_id"] != document_id for result in search.json()["results"]
    )
    for route in ("document-size-info", "chunk-info"):
        response = client.get(
            f"{FRONTEND_API}/document/{route}",
            params={"document_id": document_id, "chunk_id": 0},
            headers=admin_user.headers,
        )
        assert response.status_code == 404
