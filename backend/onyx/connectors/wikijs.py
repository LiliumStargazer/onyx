"""Wiki.js Markdown snapshots; no permission sync or inventory-based pruning."""

import json
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.interfaces import GenerateDocumentsOutput, LoadConnector
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    HierarchyNode,
    TextSection,
)

_LIST_PAGES = "{ pages { list(orderBy: TITLE) { id path locale title isPublished } } }"
VISIBILITIES = frozenset({"public", "interni", "agenti", "tecnici", "concessionari"})
ROLES = frozenset({"interni", "tecnico", "agente", "concessionario"})
WIKI_ACL_PREFIX = "wikijs_visibility:"
_EXPLICIT_ANCHOR = re.compile(r"\s+\{#([\w-]+)\}$")
# ponytail: cap unpaged inventories and page bodies; add streaming only if a Wiki.js API supports it.
_MAX_INVENTORY_PAGES = 100_000
_MAX_PAGE_BYTES = 10 * 1024 * 1024


class _WikiPageNotFound(ValueError):
    pass


class _WikiPage(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int
    path: str
    locale: str
    title: str
    isPublished: bool

    @property
    def page_path(self) -> str:
        if (
            not self.locale
            or "/" in self.locale
            or not self.path
            or any(part in ("", ".", "..") for part in self.path.split("/"))
        ):
            raise ValueError("Invalid Wiki.js page path")
        return f"/{self.locale}/{self.path}"


def _folder_match(segment: str, folder: str) -> bool:
    segment, folder = segment.casefold(), folder.casefold()
    return segment == folder or (
        segment.startswith(folder)
        and len(segment) > len(folder) + 1
        and not segment[len(folder)].isalnum()
    )


def _folder_names(raw: str | None) -> list[str]:
    if raw is None:
        raise ValueError("Wiki.js folder configuration is required")
    value = json.loads(raw)
    if not isinstance(value, list) or any(
        not isinstance(name, str) or not name.strip() or "/" in name for name in value
    ):
        raise ValueError("Excluded folder names must be a JSON array of path segments")
    names = [name.casefold() for name in value]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate excluded folder names")
    return names


def parse_visibility_folders(raw: str | None) -> dict[str, str]:
    if raw is None:
        raise ValueError("Wiki.js visibility configuration is required")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or not value
        or any(
            not isinstance(folder, str)
            or not folder.strip()
            or "/" in folder
            or not isinstance(visibility, str)
            or visibility not in VISIBILITIES
            for folder, visibility in value.items()
        )
    ):
        raise ValueError("Invalid Wiki.js visibility folder map")
    folders = {folder.casefold(): visibility for folder, visibility in value.items()}
    if len(folders) != len(value):
        raise ValueError("Duplicate visibility folder names")
    return folders


def parse_role_visibility_map(raw: str | None) -> dict[str, list[str]]:
    if raw is None:
        raise ValueError("Wiki.js role visibility configuration is required")
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise ValueError("Invalid Wiki.js role visibility map") from exc
    if (
        not isinstance(value, dict)
        or set(value) != ROLES
        or any(
            not isinstance(visibilities, list)
            or len(visibilities) != len(set(map(str, visibilities)))
            or any(
                not isinstance(v, str) or v not in VISIBILITIES for v in visibilities
            )
            for visibilities in value.values()
        )
    ):
        raise ValueError("Invalid Wiki.js role visibility map")
    return value


def wiki_visibility_group(connector_id: int, visibility: str) -> str:
    return f"{WIKI_ACL_PREFIX}{connector_id}:{visibility}"


def _sections(markdown: str, url: str) -> list[TextSection]:
    headings = [
        token.map[0]
        for token in MarkdownIt("commonmark").parse(markdown)
        if token.type == "heading_open" and token.map is not None
    ]
    lines = markdown.splitlines(keepends=True)
    sections: list[TextSection] = []
    seen_anchors: dict[str, int] = {}
    if headings and headings[0] > 0:
        sections.append(TextSection(text="".join(lines[: headings[0]]), link=url))
    for index, heading_line in enumerate(headings):
        next_line = headings[index + 1] if index + 1 < len(headings) else len(lines)
        heading = lines[heading_line].lstrip("# ").rstrip(" #\n")
        explicit_anchor = _EXPLICIT_ANCHOR.search(heading)
        if explicit_anchor:
            heading = heading[: explicit_anchor.start()]
        # Plain headings use Wiki.js slugs; complex Markdown keeps the page link.
        plain_heading = all(
            char.isalnum() or char.isspace() or char in "-_" for char in heading
        )
        if explicit_anchor:
            anchor = explicit_anchor.group(1)
        elif plain_heading:
            anchor = "-".join(heading.lower().split())
        else:
            anchor = ""
        anchor = quote(anchor, safe="-")
        link = url
        if anchor:
            count = seen_anchors.get(anchor, 0)
            seen_anchors[anchor] = count + 1
            link = f"{url}#{anchor}{f'-{count}' if count else ''}"
        sections.append(
            TextSection(
                text="".join(lines[heading_line:next_line]), link=link, heading=heading
            )
        )
    return sections or [TextSection(text=markdown, link=url)]


class WikiJsConnector(LoadConnector):
    """Read a Wiki.js snapshot with visibility metadata for Onyx ACLs."""

    def __init__(
        self,
        wiki_url: str,
        corpus_root: str | None,
        excluded_folder_names: str | None,
        visibility_folders: str | None,
        role_visibility_map: str | None,
    ) -> None:
        parsed_url = urlsplit(wiki_url)
        if (
            parsed_url.scheme not in ("http", "https")
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("Wiki.js URL must be an HTTP(S) base URL")
        if (
            not corpus_root
            or not corpus_root.startswith("/")
            or (corpus_root != "/" and corpus_root.endswith("/"))
            or (
                corpus_root != "/"
                and any(
                    part in ("", ".", "..")
                    for part in corpus_root.strip("/").split("/")
                )
            )
        ):
            raise ValueError("Invalid Wiki.js corpus root")
        self.wiki_url = wiki_url.rstrip("/")
        self.corpus_root = corpus_root
        self.excluded_folder_names = _folder_names(excluded_folder_names)
        self.visibility_folders = parse_visibility_folders(visibility_folders)
        parse_role_visibility_map(role_visibility_map)
        self.api_token: str | None = None
        # Reconcile the later snapshot with per-ID proof, even if the inventory is stale.
        self._verified_pages: dict[int, _WikiPage | None] = {}

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        token = credentials.get("wikijs_api_token")
        if not isinstance(token, str) or not token.strip():
            raise ConnectorMissingCredentialError("Wiki.js")
        self.api_token = token

    def validate_connector_settings(self) -> None:
        if not self.api_token:
            raise ConnectorMissingCredentialError("Wiki.js")

    def _query(self, query: str) -> dict[str, Any]:
        self.validate_connector_settings()
        response = httpx.post(
            f"{self.wiki_url}/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {self.api_token}"},
            timeout=30.0,
        )
        response.raise_for_status()
        if len(response.content) > _MAX_PAGE_BYTES:
            raise ValueError("Wiki.js response exceeds snapshot limit")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Wiki.js GraphQL query failed")
        errors = payload.get("errors")
        if errors:
            if (
                "single(id:" in query
                and isinstance(errors, list)
                and len(errors) == 1
                and isinstance(errors[0], dict)
                and errors[0].get("path") == ["pages", "single"]
                and isinstance(errors[0].get("extensions"), dict)
                and errors[0]["extensions"].get("code") == "PageNotFound"
            ):
                raise _WikiPageNotFound("Wiki.js page not found")
            raise ValueError("Wiki.js GraphQL query failed")
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
            raise ValueError("Incomplete Wiki.js GraphQL response")
        return data["pages"]

    def _visibility(self, page_path: str) -> str | None:
        if self.corpus_root != "/" and not (
            page_path.casefold() == self.corpus_root.casefold()
            or page_path.casefold().startswith(self.corpus_root.casefold() + "/")
        ):
            return None
        relative_path = page_path[len(self.corpus_root) :].strip("/")
        if any(
            segment.casefold() in self.excluded_folder_names
            for segment in relative_path.split("/")[:-1]
        ):
            return None
        matched = {
            visibility
            for segment in page_path.strip("/").split("/")
            for folder, visibility in self.visibility_folders.items()
            if _folder_match(segment, folder)
        }
        if len(matched) > 1:
            raise ValueError(f"Conflicting Wiki.js visibility for {page_path}")
        return next(iter(matched)) if matched else "public"

    def _list_pages(self) -> list[_WikiPage]:
        # Wiki.js pages.list has no page/offset argument.
        listing = self._query(_LIST_PAGES).get("list")
        if not isinstance(listing, list) or len(listing) > _MAX_INVENTORY_PAGES:
            raise ValueError("Incomplete or oversized Wiki.js inventory")
        seen_paths: set[str] = set()
        seen_ids: set[int] = set()
        pages: list[_WikiPage] = []
        for item in listing:
            page = _WikiPage.model_validate(item)
            page_path = page.page_path
            if page_path in seen_paths or page.id in seen_ids:
                raise ValueError("Conflicting Wiki.js page identity")
            seen_paths.add(page_path)
            seen_ids.add(page.id)
            pages.append(page)
        return pages

    def _snapshot_pages(self) -> list[tuple[_WikiPage, str]]:
        pages_by_id = {page.id: page for page in self._list_pages()}
        for page_id, verified_page in self._verified_pages.items():
            if verified_page is None:
                pages_by_id.pop(page_id, None)
            else:
                pages_by_id[page_id] = verified_page
        pages = list(pages_by_id.values())
        if len({page.page_path for page in pages}) != len(pages):
            raise ValueError("Conflicting Wiki.js page identity")
        return [
            (page, visibility)
            for page in pages
            if page.isPublished
            and (visibility := self._visibility(page.page_path)) is not None
        ]

    def confirm_removed_pages(self, indexed_pages: dict[str, int]) -> list[str]:
        """Confirm each indexed ID against Wiki.js; inventory absence is never proof."""
        unpublished_ids = {
            page.id for page in self._list_pages() if not page.isPublished
        }
        removed_paths: list[str] = []
        verified_pages: dict[int, _WikiPage | None] = dict.fromkeys(unpublished_ids)
        for page_path, page_id in indexed_pages.items():
            if page_id in unpublished_ids:
                removed_paths.append(page_path)
                continue
            try:
                details = self._query(
                    f"{{ pages {{ single(id: {page_id}) {{ id path locale title isPublished }} }} }}"
                ).get("single")
            except _WikiPageNotFound:
                verified_pages[page_id] = None
                removed_paths.append(page_path)
                continue
            if details is None:
                continue  # A null response is not structured PageNotFound proof.
            if not isinstance(details, dict):
                raise ValueError("Incomplete Wiki.js page verification")
            page = _WikiPage.model_validate(details)
            if page.id != page_id:
                raise ValueError("Mismatched Wiki.js page verification")
            verified_pages[page_id] = page
            if (
                not page.isPublished
                or page.page_path != page_path
                or self._visibility(page.page_path) is None
            ):
                removed_paths.append(page_path)
        self._verified_pages = verified_pages
        return removed_paths

    def load_from_state(self) -> GenerateDocumentsOutput:
        batch: list[Document | HierarchyNode] = []
        for page, visibility in self._snapshot_pages():
            details = self._query(
                f"{{ pages {{ single(id: {page.id}) {{ id path locale title isPublished content }} }} }}"
            ).get("single")
            if not isinstance(details, dict) or not isinstance(
                details.get("content"), str
            ):
                raise ValueError(f"Incomplete Wiki.js page: {page.page_path}")
            current_page = _WikiPage.model_validate(details)
            if (
                current_page.id != page.id
                or current_page.page_path != page.page_path
                or not current_page.isPublished
            ):
                raise ValueError(f"Changed Wiki.js page: {page.page_path}")
            url = f"{self.wiki_url}{quote(page.page_path, safe='/')}"
            batch.append(
                Document(
                    id=page.page_path,
                    source=DocumentSource.WIKIJS,
                    semantic_identifier=current_page.title,
                    title=current_page.title,
                    sections=_sections(details["content"], url),
                    metadata={"page_path": page.page_path, "visibility": visibility},
                    doc_metadata={"wikijs_page_id": page.id, "visibility": visibility},
                )
            )
            if len(batch) >= INDEX_BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch
