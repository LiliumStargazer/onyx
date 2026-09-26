import json
from unittest.mock import patch

import httpx
import pytest

from onyx.configs.constants import DocumentSource
from onyx.connectors.models import ConnectorMissingCredentialError, Document
from onyx.connectors.wikijs import WikiJsConnector

CONFIG = {
    "wiki_url": "https://wiki.example.test",
    "corpus_root": "/it",
    "excluded_folder_names": '["Bozze"]',
    "visibility_folders": '{"Riservato":"interni"}',
}


def _page(page_id: int, path: str, published: bool = True) -> dict[str, object]:
    return {
        "id": page_id,
        "path": path,
        "locale": "it",
        "title": f"Page {page_id}",
        "isPublished": published,
    }


def _graphql(data: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": {"pages": data}},
        request=httpx.Request("POST", "https://wiki.example.test/graphql"),
    )


def test_initial_snapshot_preserves_paths_visibility_and_section_links() -> None:
    responses = iter(
        [
            _graphql(
                {
                    "list": [
                        _page(1, "Help"),
                        _page(2, "Riservato/Manuale"),
                        _page(3, "Bozze/Old"),
                        _page(4, "NotReady", False),
                        _page(5, "Help/Other"),
                    ]
                }
            ),
            _graphql(
                {
                    "single": {
                        "id": 1,
                        "path": "Help",
                        "locale": "it",
                        "content": "# Installazione\nTesto\n",
                    }
                }
            ),
            _graphql(
                {
                    "single": {
                        "id": 2,
                        "path": "Riservato/Manuale",
                        "locale": "it",
                        "content": "## Accesso\nSegreto\n",
                    }
                }
            ),
            _graphql(
                {
                    "single": {
                        "id": 5,
                        "path": "Help/Other",
                        "locale": "it",
                        "content": "Altro",
                    }
                }
            ),
        ]
    )
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch("httpx.post", side_effect=list(responses)):
        batches = list(connector.load_from_state())

    docs = [doc for batch in batches for doc in batch if isinstance(doc, Document)]
    assert [doc.id for doc in docs] == [
        "/it/Help",
        "/it/Riservato/Manuale",
        "/it/Help/Other",
    ]
    assert [doc.metadata["visibility"] for doc in docs] == [
        "public",
        "interni",
        "public",
    ]
    assert docs[1].metadata["page_path"] == "/it/Riservato/Manuale"
    assert docs[0].title == "Page 1"
    assert docs[0].source == DocumentSource.WIKIJS
    assert docs[0].sections[0].link == "https://wiki.example.test/it/Help#installazione"
    assert "Testo" in docs[0].get_text_content()


def test_missing_or_invalid_policy_blocks_snapshot() -> None:
    for override in (
        {"excluded_folder_names": None},
        {"excluded_folder_names": "invalid"},
        {"excluded_folder_names": '["Bad/Folder"]'},
        {"visibility_folders": "{}"},
        {"visibility_folders": '{"x":"unknown"}'},
        {"visibility_folders": '{"x":[]}'},
        {"corpus_root": "it"},
    ):
        config = CONFIG | override
        with pytest.raises(ValueError):
            WikiJsConnector(
                wiki_url=CONFIG["wiki_url"],
                corpus_root=config["corpus_root"],
                excluded_folder_names=config["excluded_folder_names"],
                visibility_folders=config["visibility_folders"],
            )


def test_conflicting_visibility_fails_before_any_document_is_emitted() -> None:
    config = CONFIG | {
        "visibility_folders": json.dumps({"A": "interni", "B": "agenti"})
    }
    connector = WikiJsConnector(**config)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch("httpx.post", return_value=_graphql({"list": [_page(1, "A/B/Page")]})):
        with pytest.raises(ValueError, match="visibility"):
            list(connector.load_from_state())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            200,
            json={"data": {"pages": {"list": None}}},
            request=httpx.Request("POST", "https://wiki.example.test/graphql"),
        ),
        httpx.Response(
            200,
            json={"errors": [{"message": "not permitted"}]},
            request=httpx.Request("POST", "https://wiki.example.test/graphql"),
        ),
        httpx.Response(
            403, request=httpx.Request("POST", "https://wiki.example.test/graphql")
        ),
    ],
)
def test_incomplete_inventory_fails_closed(response: httpx.Response) -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch("httpx.post", return_value=response):
        with pytest.raises((ValueError, httpx.HTTPError)):
            list(connector.load_from_state())


def test_explicit_heading_anchor_is_preserved_and_code_fence_is_not_a_heading() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        side_effect=[
            _graphql({"list": [_page(1, "Help")]}),
            _graphql(
                {
                    "single": {
                        "id": 1,
                        "path": "Help",
                        "locale": "it",
                        "content": "# Setup {#install}\nText\n```\n# Not a heading\n```",
                    }
                }
            ),
        ],
    ):
        docs = [
            doc
            for batch in connector.load_from_state()
            for doc in batch
            if isinstance(doc, Document)
        ]

    assert len(docs) == 1
    assert [section.link for section in docs[0].sections] == [
        "https://wiki.example.test/it/Help#install"
    ]


def test_missing_token_and_duplicate_identity_stop_snapshot() -> None:
    connector = WikiJsConnector(**CONFIG)
    with pytest.raises(ConnectorMissingCredentialError):
        list(connector.load_from_state())
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        return_value=_graphql({"list": [_page(1, "Help"), _page(1, "Other")]}),
    ):
        with pytest.raises(ValueError, match="identity"):
            list(connector.load_from_state())


def test_inconsistent_page_response_fails_closed() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        side_effect=[
            _graphql({"list": [_page(1, "Help")]}),
            _graphql(
                {
                    "single": {
                        "id": 1,
                        "path": "Other",
                        "locale": "it",
                        "content": "wrong",
                    }
                }
            ),
        ],
    ):
        with pytest.raises(ValueError):
            list(connector.load_from_state())
