from contextlib import nullcontext
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

import pytest

from onyx.background.indexing.run_docfetching import remove_confirmed_wikijs_pages
from onyx.connectors.wikijs import WikiJsConnector
from onyx.db.models import Document


def test_confirmed_pages_use_cc_pair_cleanup_before_indexing() -> None:
    documents = [
        SimpleNamespace(id="/it/Old", doc_metadata={"wikijs_page_id": 7}),
        SimpleNamespace(id="/it/Unknown", doc_metadata=None),
    ]
    connector = Mock(spec=WikiJsConnector)
    connector.confirm_removed_pages.return_value = ["/it/Old"]
    cleanup = Mock()
    cleanup.apply.return_value.get.return_value = True
    with (
        patch(
            "onyx.background.indexing.run_docfetching.get_session_with_current_tenant",
            return_value=nullcontext(Mock()),
        ),
        patch(
            "onyx.background.indexing.run_docfetching.get_documents_for_cc_pair",
            return_value=cast(list[Document], documents),
        ),
        patch(
            "onyx.background.indexing.run_docfetching.document_by_cc_pair_cleanup_task",
            cleanup,
        ),
    ):
        remove_confirmed_wikijs_pages(connector, 12, 3, 4, "tenant")

    connector.confirm_removed_pages.assert_called_once_with({"/it/Old": 7})
    cleanup.apply.assert_called_once_with(
        kwargs={
            "document_id": "/it/Old",
            "connector_id": 3,
            "credential_id": 4,
            "tenant_id": "tenant",
        }
    )


def test_verification_error_never_starts_cleanup() -> None:
    connector = Mock(spec=WikiJsConnector)
    connector.confirm_removed_pages.side_effect = ValueError(
        "Wiki.js GraphQL query failed"
    )
    cleanup = Mock()
    with (
        patch(
            "onyx.background.indexing.run_docfetching.get_session_with_current_tenant",
            return_value=nullcontext(Mock()),
        ),
        patch(
            "onyx.background.indexing.run_docfetching.get_documents_for_cc_pair",
            return_value=cast(
                list[Document],
                [SimpleNamespace(id="/it/Old", doc_metadata={"wikijs_page_id": 7})],
            ),
        ),
        patch(
            "onyx.background.indexing.run_docfetching.document_by_cc_pair_cleanup_task",
            cleanup,
        ),
    ):
        with pytest.raises(ValueError, match="GraphQL"):
            remove_confirmed_wikijs_pages(connector, 12, 3, 4, "tenant")
    cleanup.apply.assert_not_called()


def test_failed_cleanup_stops_run() -> None:
    connector = Mock(spec=WikiJsConnector)
    connector.confirm_removed_pages.return_value = ["/it/Old"]
    cleanup = Mock()
    cleanup.apply.return_value.get.return_value = False
    with (
        patch(
            "onyx.background.indexing.run_docfetching.get_session_with_current_tenant",
            return_value=nullcontext(Mock()),
        ),
        patch(
            "onyx.background.indexing.run_docfetching.get_documents_for_cc_pair",
            return_value=cast(
                list[Document],
                [SimpleNamespace(id="/it/Old", doc_metadata={"wikijs_page_id": 7})],
            ),
        ),
        patch(
            "onyx.background.indexing.run_docfetching.document_by_cc_pair_cleanup_task",
            cleanup,
        ),
    ):
        with pytest.raises(RuntimeError, match="cleanup"):
            remove_confirmed_wikijs_pages(connector, 12, 3, 4, "tenant")
