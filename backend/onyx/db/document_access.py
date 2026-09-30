"""SQL filters matching indexed document visibility."""

from uuid import UUID

from sqlalchemy import Select, String, and_, any_, cast, false, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from onyx.configs.constants import DocumentSource
from onyx.connectors.wikijs import VISIBILITIES, wiki_visibility_group
from onyx.db.connector import get_wikijs_role_visibilities
from onyx.db.connector_credential_pair import build_user_cc_pair_access_filter
from onyx.db.enums import AccessType, ConnectorCredentialPairStatus
from onyx.db.models import (
    Connector,
    ConnectorCredentialPair,
    Document,
    DocumentByConnectorCredentialPair,
    User,
)


def get_wikijs_document_groups(
    db_session: Session, document_ids: list[str]
) -> dict[str, str | None]:
    """Bind the indexed visibility to its connector, never its owner."""
    if not document_ids:
        return {}
    rows = db_session.execute(
        select(Document.id, Document.doc_metadata, Connector.id)
        .join(
            DocumentByConnectorCredentialPair,
            Document.id == DocumentByConnectorCredentialPair.id,
        )
        .join(Connector, Connector.id == DocumentByConnectorCredentialPair.connector_id)
        .where(Document.id.in_(document_ids), Connector.source == DocumentSource.WIKIJS)
    ).all()
    connector_ids: dict[str, set[int]] = {}
    visibility_by_id: dict[str, str | None] = {}
    for document_id, metadata, connector_id in rows:
        connector_ids.setdefault(document_id, set()).add(connector_id)
        visibility_by_id[document_id] = (metadata or {}).get("visibility")
    groups: dict[str, str | None] = {}
    for document_id, ids in connector_ids.items():
        visibility = visibility_by_id[document_id]
        groups[document_id] = (
            wiki_visibility_group(next(iter(ids)), visibility)
            if len(ids) == 1 and visibility in VISIBILITIES
            else None
        )
    return groups


def apply_document_access_filter(
    stmt: Select,
    db_session: Session,
    user_email: str | None,
    external_group_ids: list[str],
    user_id: UUID | None = None,
    prior_emails: list[str] | None = None,
) -> Select:
    """Filter documents by source ACL or associated connector access."""
    stmt = stmt.join(
        DocumentByConnectorCredentialPair,
        Document.id == DocumentByConnectorCredentialPair.id,
    ).join(
        ConnectorCredentialPair,
        and_(
            DocumentByConnectorCredentialPair.connector_id
            == ConnectorCredentialPair.connector_id,
            DocumentByConnectorCredentialPair.credential_id
            == ConnectorCredentialPair.credential_id,
        ),
    )

    stmt = stmt.where(
        ConnectorCredentialPair.status != ConnectorCredentialPairStatus.DELETING
    )

    access_filters: list[ColumnElement[bool]] = [
        ConnectorCredentialPair.access_type == AccessType.PUBLIC,
        Document.is_public.is_(True),
    ]
    if user_email:
        access_filters.append(any_(Document.external_user_emails) == user_email)
    if prior_emails:
        access_filters.append(
            Document.external_user_emails.overlap(
                cast(postgresql.array(prior_emails), postgresql.ARRAY(String))
            )
        )
    if external_group_ids:
        access_filters.append(
            Document.external_user_group_ids.overlap(
                cast(postgresql.array(external_group_ids), postgresql.ARRAY(String))
            )
        )
    if user_id:
        access_filters.append(build_user_cc_pair_access_filter(user_id))

    user = db_session.get(User, user_id) if user_id else None
    allowed = get_wikijs_role_visibilities(
        db_session, user.workspace_role if user else None
    )
    wiki_filters = [
        and_(
            ConnectorCredentialPair.connector_id == connector_id,
            Document.doc_metadata["visibility"].astext.in_(visibilities),
        )
        for connector_id, visibilities in allowed.items()
        if visibilities
    ]
    wiki_link = aliased(DocumentByConnectorCredentialPair)
    wiki_connector = aliased(Connector)
    wiki_links = (
        select(wiki_link.id)
        .join(wiki_connector, wiki_connector.id == wiki_link.connector_id)
        .where(
            wiki_link.id == Document.id, wiki_connector.source == DocumentSource.WIKIJS
        )
    )
    has_wiki_link = wiki_links.exists()
    has_other_wiki_connector = wiki_links.where(
        wiki_link.connector_id != ConnectorCredentialPair.connector_id
    ).exists()
    stmt = stmt.join(Connector, Connector.id == ConnectorCredentialPair.connector_id)
    return stmt.where(
        or_(
            and_(~has_wiki_link, or_(*access_filters)),
            and_(
                Connector.source == DocumentSource.WIKIJS,
                ~has_other_wiki_connector,
                or_(*wiki_filters),
            )
            if wiki_filters
            else false(),
        )
    )


def get_accessible_documents_by_ids(
    db_session: Session,
    document_ids: list[str],
    user_email: str | None,
    external_group_ids: list[str],
    user_id: UUID | None = None,
) -> list[Document]:
    """Return requested documents allowed by the retrieval-time access policy."""
    if not document_ids:
        return []

    stmt = select(Document).where(Document.id.in_(document_ids))
    stmt = apply_document_access_filter(
        stmt, db_session, user_email, external_group_ids, user_id=user_id
    )
    stmt = stmt.distinct()
    return list(db_session.execute(stmt).scalars().all())
