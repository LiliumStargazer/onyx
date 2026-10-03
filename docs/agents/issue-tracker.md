# Issue tracker: GitHub

Issues and specs live in `LiliumStargazer/wiki-copilot`. Use the `gh` CLI.
Set `GH_REPO=LiliumStargazer/wiki-copilot` for every `gh` command. Do not rely on the repo that `gh` selects from remotes.

## Conventions

- Create: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- Read: `gh issue view <number> --comments`; fetch labels as needed.
- List: `gh issue list --state open --json number,title,body,labels,comments`, with appropriate filters.
- Comment: `gh issue comment <number> --body "..."`
- Apply or remove labels: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

## Pull requests as a triage surface

**PRs as a request surface: no.** Set this to `yes` if external PRs should enter the triage queue.

When set to `yes`, use `gh pr` equivalents. Read a PR with `gh pr view <number> --comments` and `gh pr diff <number>`. List open PRs and keep authors with `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE`. A bare issue number may name a PR: try `gh pr view <number>`, then `gh issue view <number>`.

## Skill operations

- To publish to the issue tracker, create a GitHub issue.
- To fetch a ticket, run `gh issue view <number> --comments`.

## Wayfinding

Use one issue labelled `wayfinder:map` for the map. Link child issues as GitHub sub-issues. If sub-issues are unavailable, add children to a task list in the map and put `Part of #<map>` in each child. Label children `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`).

Use native issue dependencies for blocking. Call `gh api --method POST repos/LiliumStargazer/wiki-copilot/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`. Get the database ID with `gh api repos/LiliumStargazer/wiki-copilot/issues/<n> --jq .id`. If dependencies are unavailable, put `Blocked by: #<n>` in the child body.

For the frontier, take the first open, unassigned child without an open blocker, in map order. Claim it with `gh issue edit <n> --add-assignee @me`. To resolve it, comment with the answer, close it, and add a context pointer to the map's Decisions-so-far.
