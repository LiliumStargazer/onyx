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
    assert docs[1].doc_metadata == {"wikijs_page_id": 2, "visibility": "interni"}
    assert docs[0].title == "Page 1"
    assert docs[0].source == DocumentSource.WIKIJS
    assert docs[0].sections[0].link == "https://wiki.example.test/it/Help#installazione"
    assert "Testo" in docs[0].get_text_content()


def test_next_snapshot_emits_changed_content_and_visibility_at_same_path() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})

    def snapshot(title: str, content: str, path: str) -> Document:
        with patch(
            "httpx.post",
            side_effect=[
                _graphql({"list": [{**_page(7, path), "title": title}]}),
                _graphql(
                    {
                        "single": {
                            "id": 7,
                            "path": path,
                            "locale": "it",
                            "content": content,
                        }
                    }
                ),
            ],
        ):
            return next(
                doc
                for batch in connector.load_from_state()
                for doc in batch
                if isinstance(doc, Document)
            )

    old = snapshot("First", "Old text", "Riservato/Manuale")
    connector.visibility_folders = {"riservato": "agenti"}
    new = snapshot("Second", "New text", "Riservato/Manuale")
    assert old.id == new.id == "/it/Riservato/Manuale"
    assert new.title == "Second"
    assert new.get_text_content() == "New text"
    assert new.doc_metadata == {"wikijs_page_id": 7, "visibility": "agenti"}
    assert old.content_hash() != new.content_hash()


def test_confirmed_removals_require_per_id_proof_even_with_partial_inventory() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        side_effect=[
            _graphql({"list": [_page(1, "Help"), _page(2, "Old", False)]}),
            _graphql({"single": {**_page(1, "Help"), "content": "still here"}}),
            _graphql({"single": None}),
            httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Missing",
                            "path": ["pages", "single"],
                            "extensions": {"code": "PageNotFound"},
                        }
                    ]
                },
                request=httpx.Request("POST", "https://wiki.example.test/graphql"),
            ),
        ],
    ):
        assert connector.confirm_removed_pages(
            {"/it/Help": 1, "/it/Old": 2, "/it/Unknown": 3, "/it/Deleted": 4}
        ) == ["/it/Old", "/it/Deleted"]


@pytest.mark.parametrize(
    "failure",
    [
        httpx.TimeoutException("timed out"),
        _graphql({"single": None}),
        httpx.Response(
            200,
            json={
                "errors": [{"message": "Denied", "extensions": {"code": "Forbidden"}}]
            },
            request=httpx.Request("POST", "https://wiki.example.test/graphql"),
        ),
    ],
)
def test_unproven_removal_is_not_confirmed(failure: object) -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch("httpx.post", side_effect=[_graphql({"list": []}), failure]):
        if (
            isinstance(failure, httpx.TimeoutException)
            or isinstance(failure, httpx.Response)
            and failure.json().get("errors")
        ):
            with pytest.raises((httpx.TimeoutException, ValueError)):
                connector.confirm_removed_pages({"/it/Missing": 8})
        else:
            assert connector.confirm_removed_pages({"/it/Missing": 8}) == []


def test_unpublished_single_confirms_removal_from_partial_inventory() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        side_effect=[
            _graphql({"list": []}),
            _graphql({"single": _page(7, "Old", False)}),
        ],
    ):
        assert connector.confirm_removed_pages({"/it/Old": 7}) == ["/it/Old"]


def test_verified_move_and_exit_from_scope_remove_old_paths() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        side_effect=[
            _graphql({"list": []}),
            _graphql({"single": _page(7, "Moved")}),
            _graphql({"single": _page(8, "Bozze/Hidden")}),
            _graphql({"single": {**_page(9, "Outside"), "locale": "en"}}),
        ],
    ):
        assert connector.confirm_removed_pages(
            {"/it/Old": 7, "/it/Bozze/PreviouslyPublic": 8, "/it/Outside": 9}
        ) == ["/it/Old", "/it/Bozze/PreviouslyPublic", "/it/Outside"]


def test_verified_rename_indexes_new_path_from_stale_inventory() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        side_effect=[
            _graphql({"list": [_page(7, "Old"), _page(8, "Other")]}),
            _graphql({"single": {**_page(7, "Riservato/New"), "title": "New title"}}),
            _graphql({"list": [_page(7, "Old"), _page(8, "Other")]}),
            _graphql(
                {
                    "single": {
                        "id": 7,
                        "path": "Riservato/New",
                        "locale": "it",
                        "content": "New text",
                    }
                }
            ),
            _graphql(
                {
                    "single": {
                        "id": 8,
                        "path": "Other",
                        "locale": "it",
                        "content": "Other text",
                    }
                }
            ),
        ],
    ):
        assert connector.confirm_removed_pages({"/it/Old": 7}) == ["/it/Old"]
        docs = [
            doc
            for batch in connector.load_from_state()
            for doc in batch
            if isinstance(doc, Document)
        ]

    assert [doc.id for doc in docs] == ["/it/Riservato/New", "/it/Other"]
    assert docs[0].title == "New title"
    assert docs[0].get_text_content() == "New text"
    assert docs[0].doc_metadata == {"wikijs_page_id": 7, "visibility": "interni"}


def test_verified_move_out_of_scope_does_not_reload_old_path() -> None:
    connector = WikiJsConnector(**CONFIG)
    connector.load_credentials({"wikijs_api_token": "fixture-token"})
    with patch(
        "httpx.post",
        side_effect=[
            _graphql({"list": [_page(7, "Old"), _page(8, "Previous")]}),
            _graphql({"single": {**_page(7, "Elsewhere"), "locale": "en"}}),
            _graphql({"single": _page(8, "Bozze/Hidden")}),
            _graphql({"list": [_page(7, "Old"), _page(8, "Previous")]}),
        ],
    ):
        assert connector.confirm_removed_pages({"/it/Old": 7, "/it/Previous": 8}) == [
            "/it/Old",
            "/it/Previous",
        ]
        assert list(connector.load_from_state()) == []


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
