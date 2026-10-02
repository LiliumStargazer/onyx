# Wiki.js snapshot connector (#1)

This connector reads Wiki.js Markdown through GraphQL and emits Onyx `Document` batches. It is for a **first test snapshot on an empty, isolated test index**. Do not connect it to the production Wiki or publish an index that contains restricted pages. Issue #2 must settle deployment and access controls before a real import.

In the Onyx Admin Panel, create a Wiki.js connector with:

- **Wiki.js URL:** the HTTP(S) base URL of the test Wiki.js instance.
- **Corpus root:** an absolute path, such as `/it`. Use `/` only to include all locales.
- **Excluded folder names:** a JSON array of whole folder segment names, such as `["Bozze"]`. Use `[]` to exclude none. Matching is case-insensitive and applies below the corpus root.
- **Visibility folders:** a nonempty JSON object that maps folder names to `public`, `interni`, `agenti`, `tecnici`, or `concessionari`. Matching is case-insensitive. A segment matches the name exactly or a name followed by a non-alphanumeric separator and more text. Conflicting values stop the run. Pages without a marker receive `public` metadata.
- **Credential:** a separate `wikijs_api_token` in the same Admin Panel. The connector only sends read queries. In the documented wiki-copilot clone, Wiki.js `pages.single` requires **`manage:pages`**, even though the connector does not write. Reading Markdown also requires **`read:source`**. The connector reads publication state through `pages.list`, without requesting the write-protected `Page.isPublished` field. Limit the token to the minimum access the Wiki.js instance supports. Do not place it in Portainer variables.

Keep the connector **private** in a test instance with no generic users. The form creates a private connector and sets refresh and prune frequencies to `null`. The backend rejects scheduled refresh or prune and blocks manual pruning for Wiki.js. Do not change its access or attach it to shared groups. `visibility` is searchable metadata, **not** an Onyx access rule. The connector does not implement permission sync. Never expose restricted content through web, chat, or API.

Wiki.js 2 `pages.list` returns an unpaged array. It does not accept a page/offset argument. The connector validates the response before producing documents. It rejects responses over 10 MB and inventories over 100,000 pages. It reads Markdown with `pages.single` and verifies page identity. It confirms publication from a fresh inventory before emitting each batch. It stops on missing data, changed publication state, network errors, or permission errors. It does not delete documents or assert that a failed run was complete. Only pages marked published in the inventory and within the root are eligible. Drafts, out-of-root paths, and excluded folders are omitted. All other published pages, including restricted pages, are included. `page_path` is the document ID and a metadata field; each section has a source URL and a heading anchor when available.

The snapshot does **not** track subsequent edits, renames, unpublish events, or deletions. Do not use it as a continuing service. The next issue owns lifecycle and pruning. Fixture tests use synthetic Wiki.js responses only; no live Wiki, embedding provider, or index is needed to run them:

```sh
uv run pytest -q backend/tests/unit/onyx/connectors/test_wikijs.py backend/tests/unit/onyx/connectors/test_wikijs_pruning.py
```
