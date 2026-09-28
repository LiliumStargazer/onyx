from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from onyx.access.models import DocumentAccess
from onyx.background.celery.tasks.shared.tasks import document_by_cc_pair_cleanup_task
from onyx.background.indexing.run_docfetching import remove_confirmed_wikijs_pages
from onyx.configs.constants import DocumentSource
from onyx.connectors.models import Document, IndexAttemptMetadata, TextSection
from onyx.connectors.wikijs import WikiJsConnector
from onyx.db.document import (
    get_wikijs_page_ids_for_cc_pair,
    upsert_document_by_connector_credential_pair,
)
from onyx.db.models import Document as DBDocument
from onyx.indexing.indexing_pipeline import get_docs_to_update, index_doc_batch_prepare


def test_wikijs_page_ids_are_scoped_to_cc_pair_and_legacy_shared_ids_are_ignored() -> (
    None
):
    db_session = Mock()
    db_session.execute.return_value = [
        ("/it/Shared", 7, {"wikijs_page_id": 8}, True),
        ("/it/Unknown", None, {"wikijs_page_id": 8}, True),
        ("/it/Legacy", None, {"wikijs_page_id": 9}, False),
    ]
    with patch(
        "onyx.db.document.get_connector_credential_pair_from_id",
        return_value=SimpleNamespace(connector_id=3, credential_id=4),
    ):
        assert get_wikijs_page_ids_for_cc_pair(db_session, 12) == {
            "/it/Shared": 7,
            "/it/Legacy": 9,
        }


def test_wikijs_page_id_is_saved_on_the_cc_pair_link_even_if_content_is_unchanged() -> (
    None
):
    document = Document(
        id="/it/Shared",
        source=DocumentSource.WIKIJS,
        semantic_identifier="Shared",
        sections=[TextSection(text="Content")],
        metadata={},
        doc_metadata={"wikijs_page_id": 7},
    )
    db_session = Mock()
    attempt = IndexAttemptMetadata(
        connector_id=3, credential_id=4, attempt_id=None, request_id="test"
    )
    with (
        patch(
            "onyx.indexing.indexing_pipeline.get_documents_by_ids",
            return_value=[
                SimpleNamespace(
                    id=document.id,
                    file_id=None,
                    doc_updated_at=None,
                    content_hash=document.content_hash(),
                )
            ],
        ),
        patch("onyx.indexing.indexing_pipeline.link_hierarchy_nodes_to_documents"),
        patch(
            "onyx.indexing.indexing_pipeline.upsert_document_by_connector_credential_pair"
        ) as upsert_link,
    ):
        assert index_doc_batch_prepare([document], attempt, db_session) is None

    upsert_link.assert_called_once_with(
        db_session, 3, 4, ["/it/Shared"], wikijs_page_ids={"/it/Shared": 7}
    )

    upsert_document_by_connector_credential_pair(
        db_session, 3, 4, ["/it/Shared"], wikijs_page_ids={"/it/Shared": 7}
    )
    statement = db_session.execute.call_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "('/it/Shared', 3, 4, false, 7)" in sql
    assert (
        "ON CONFLICT (id, connector_id, credential_id) DO UPDATE SET wikijs_page_id"
        in sql
    )


def test_confirmed_pages_use_cc_pair_cleanup_before_indexing() -> None:
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
            "onyx.background.indexing.run_docfetching.get_wikijs_page_ids_for_cc_pair",
            return_value={"/it/Old": 7},
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


def test_rename_removes_old_link_and_updates_existing_new_path() -> None:
    connector = WikiJsConnector(
        wiki_url="https://wiki.example.test",
        corpus_root="/it",
        excluded_folder_names="[]",
        visibility_folders='{"Riservato":"interni"}',
    )
    connector.load_credentials({"wikijs_api_token": "fixture-token"})

    def response(pages: dict[str, object]) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"pages": pages}},
            request=httpx.Request("POST", "https://wiki.example.test/graphql"),
        )

    new_page = {
        "id": 7,
        "path": "Riservato/New",
        "locale": "it",
        "title": "Current title",
        "isPublished": True,
    }
    cleanup = Mock()
    cleanup.apply.return_value.get.return_value = True
    with (
        patch(
            "httpx.post",
            side_effect=[
                response({"list": [new_page]}),
                response({"single": new_page}),
                response({"single": new_page}),
                response({"list": [new_page]}),
                response(
                    {
                        "single": {
                            "id": 7,
                            "path": "Riservato/New",
                            "locale": "it",
                            "content": "Current content",
                        }
                    }
                ),
            ],
        ),
        patch(
            "onyx.background.indexing.run_docfetching.get_session_with_current_tenant",
            return_value=nullcontext(Mock()),
        ),
        patch(
            "onyx.background.indexing.run_docfetching.get_wikijs_page_ids_for_cc_pair",
            return_value={"/it/Old": 7, "/it/Riservato/New": 7},
        ),
        patch(
            "onyx.background.indexing.run_docfetching.document_by_cc_pair_cleanup_task",
            cleanup,
        ),
    ):
        remove_confirmed_wikijs_pages(connector, 12, 3, 4, "tenant")
        documents = [
            doc
            for batch in connector.load_from_state()
            for doc in batch
            if isinstance(doc, Document)
        ]

    assert [doc.id for doc in documents] == ["/it/Riservato/New"]
    new_document = documents[0]
    assert cleanup.apply.call_count == 1
    assert cleanup.apply.call_args.kwargs["kwargs"]["document_id"] == "/it/Old"
    assert new_document.id == "/it/Riservato/New"
    assert new_document.title == "Current title"
    assert new_document.get_text_content() == "Current content"
    assert new_document.doc_metadata == {"wikijs_page_id": 7, "visibility": "interni"}
    previous = cast(
        DBDocument,
        SimpleNamespace(
            id=new_document.id, doc_updated_at=None, content_hash="old revision"
        ),
    )
    assert get_docs_to_update([new_document], [previous]).updatable_docs == [
        new_document
    ]


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
            "onyx.background.indexing.run_docfetching.get_wikijs_page_ids_for_cc_pair",
            return_value={"/it/Old": 7},
        ),
        patch(
            "onyx.background.indexing.run_docfetching.document_by_cc_pair_cleanup_task",
            cleanup,
        ),
    ):
        with pytest.raises(ValueError, match="GraphQL"):
            remove_confirmed_wikijs_pages(connector, 12, 3, 4, "tenant")
    cleanup.apply.assert_not_called()


def test_active_cc_pair_removal_revokes_shared_document_access() -> None:
    linked = True
    db_session = MagicMock()
    preview = db_session.begin_nested.return_value.__enter__.return_value

    def unlink(*_args: object, **_kwargs: object) -> None:
        nonlocal linked
        linked = False

    def restore_link() -> None:
        nonlocal linked
        linked = True

    def current_access(*_args: object, **_kwargs: object) -> DocumentAccess:
        return DocumentAccess.build(
            user_emails=[],
            user_groups=[],
            external_user_emails=[],
            external_user_group_ids=[],
            is_public=linked,
        )

    preview.rollback.side_effect = restore_link
    index = Mock()
    retry_index = Mock()
    with (
        patch(
            "onyx.background.celery.tasks.shared.tasks.get_session_with_current_tenant",
            return_value=nullcontext(db_session),
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.get_active_search_settings",
            return_value=SimpleNamespace(primary=Mock(), secondary=None),
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.get_document_connector_count",
            return_value=2,
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.get_document",
            return_value=SimpleNamespace(
                last_modified=datetime.now(timezone.utc),
                chunk_count=1,
                boost=0,
                hidden=False,
            ),
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.delete_document_by_connector_credential_pair__no_commit",
            side_effect=unlink,
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.get_access_for_document",
            side_effect=current_access,
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.fetch_document_sets_for_document",
            return_value=["remaining-set"],
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.get_all_document_indices",
            return_value=[index],
        ),
        patch(
            "onyx.background.celery.tasks.shared.tasks.RetryDocumentIndex",
            return_value=retry_index,
        ),
        patch("onyx.background.celery.tasks.shared.tasks.mark_document_as_synced"),
        patch(
            "onyx.background.celery.tasks.shared.tasks._clear_port_orphan_candidate_for_live_doc"
        ),
    ):
        result = document_by_cc_pair_cleanup_task.apply(
            args=("/it/Shared", 3, 4, "tenant")
        )

    assert result.successful(), result.traceback
    assert result.get() is True
    assert preview.rollback.called
    update = retry_index.update.call_args.args[0][0]
    assert update.access is not None and not update.access.is_public
    assert update.document_sets == {"remaining-set"}
    assert not linked


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
            "onyx.background.indexing.run_docfetching.get_wikijs_page_ids_for_cc_pair",
            return_value={"/it/Old": 7},
        ),
        patch(
            "onyx.background.indexing.run_docfetching.document_by_cc_pair_cleanup_task",
            cleanup,
        ),
    ):
        with pytest.raises(RuntimeError, match="cleanup"):
            remove_confirmed_wikijs_pages(connector, 12, 3, 4, "tenant")
