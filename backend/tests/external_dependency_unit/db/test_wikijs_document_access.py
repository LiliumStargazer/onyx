"""A shared Wiki.js document must not gain access through one of its connectors."""

from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from onyx.access.access import get_access_for_documents
from onyx.configs.constants import DocumentSource
from onyx.db.document_access import get_accessible_documents_by_ids
from onyx.db.models import (
    ConnectorCredentialPair,
    Document,
    DocumentByConnectorCredentialPair,
)
from onyx.kg.models import KGStage
from tests.external_dependency_unit.conftest import create_test_user, delete_test_user
from tests.external_dependency_unit.indexing_helpers import (
    cleanup_cc_pair,
    make_cc_pair,
)


def test_shared_wikijs_document_is_denied_even_if_one_connector_allows_role(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, "wikijs_acl", assign_default_group=False)
    user.workspace_role = "interni"
    first = make_cc_pair(db_session, DocumentSource.WIKIJS)
    second = make_cc_pair(db_session, DocumentSource.WIKIJS)
    first.connector.connector_specific_config = {
        "role_visibility_map": '{"interni":["interni"],"tecnico":[],"agente":[],"concessionario":[]}'
    }
    second.connector.connector_specific_config = {
        "role_visibility_map": '{"interni":[],"tecnico":[],"agente":[],"concessionario":[]}'
    }
    document_id = f"/it/Riservato/{uuid4()}"
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
            connector_id=first.connector_id,
            credential_id=first.credential_id,
            has_been_indexed=True,
        )
    )
    db_session.commit()
    try:
        assert [
            doc.id
            for doc in get_accessible_documents_by_ids(
                db_session, [document_id], user.email, [], user_id=user.id
            )
        ] == [document_id]
        db_session.add(
            DocumentByConnectorCredentialPair(
                id=document_id,
                connector_id=second.connector_id,
                credential_id=second.credential_id,
                has_been_indexed=True,
            )
        )
        db_session.commit()
        assert (
            get_accessible_documents_by_ids(
                db_session, [document_id], user.email, [], user_id=user.id
            )
            == []
        )
    finally:
        cleanup_cc_pair(db_session, first)
        cleanup_cc_pair(db_session, second)
        delete_test_user(db_session, user)
        db_session.commit()


def test_wikijs_document_keeps_visibility_acl_when_cc_pair_is_missing(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    enable_ee: None,  # noqa: ARG001
) -> None:
    pair = make_cc_pair(db_session, DocumentSource.WIKIJS)
    document_id = f"/it/Riservato/{uuid4()}"
    connector_id = pair.connector_id
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
            connector_id=connector_id,
            credential_id=pair.credential_id,
            has_been_indexed=True,
        )
    )
    db_session.commit()
    try:
        with db_session.begin_nested() as transaction:
            db_session.execute(
                delete(ConnectorCredentialPair).where(
                    ConnectorCredentialPair.id == pair.id
                )
            )
            access = get_access_for_documents([document_id], db_session)
            assert access[document_id].to_acl() == {
                f"external_group:wikijs_visibility:{connector_id}:interni"
            }
            transaction.rollback()
    finally:
        cleanup_cc_pair(db_session, pair)
