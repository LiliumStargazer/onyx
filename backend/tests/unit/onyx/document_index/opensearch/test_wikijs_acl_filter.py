"""Wiki.js chunks need a visibility token even when old chunks are public."""

from typing import Any

from onyx.document_index.interfaces_new import TenantState
from onyx.document_index.opensearch.schema import (
    ACCESS_CONTROL_LIST_FIELD_NAME,
    SOURCE_TYPE_FIELD_NAME,
)
from onyx.document_index.opensearch.search import DocumentQuery
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA


def _acl_clauses(acl: list[str]) -> list[dict[str, Any]]:
    return DocumentQuery._get_search_filters(
        tenant_state=TenantState(tenant_id=POSTGRES_DEFAULT_SCHEMA, multitenant=False),
        include_hidden=True,
        access_control_list=acl,
        source_types=[],
        tags=[],
        document_sets=[],
        project_id_filter=None,
        persona_id_filter=None,
        created_at_range=None,
        updated_at_range=None,
        min_chunk_index=None,
        max_chunk_index=None,
        max_chunk_size=None,
        document_id=None,
        attached_document_ids=None,
        hierarchy_node_ids=None,
    )


def test_wikijs_requires_own_visibility_token_without_hiding_other_sources() -> None:
    clauses = _acl_clauses(["PUBLIC", "user_email:owner@example.com"])
    assert clauses[1] == {
        "bool": {
            "should": [
                {"bool": {"must_not": [{"term": {SOURCE_TYPE_FIELD_NAME: "wikijs"}}]}},
                {"terms": {ACCESS_CONTROL_LIST_FIELD_NAME: []}},
            ],
            "minimum_should_match": 1,
        }
    }

    token = "external_group:wikijs_visibility:17:interni"
    allowed = _acl_clauses(["PUBLIC", token, "user_email:owner@example.com"])
    assert allowed[1]["bool"]["should"][1] == {
        "terms": {ACCESS_CONTROL_LIST_FIELD_NAME: [token]}
    }
