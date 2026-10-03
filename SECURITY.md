# Wiki Copilot Security Policy

## Supported versions

Security maintenance targets `main` and the latest Wiki Copilot release.
Passing application tests does not mean that a release has no known vulnerabilities.

## Reporting vulnerabilities

Do not publish vulnerabilities or credentials in public issues, pull requests, or discussions.

While this repository is public, use its private vulnerability reporting page:
<https://github.com/LiliumStargazer/wiki-copilot/security/advisories/new>.

After the repository becomes private, report issues through its private issue tracker.
Verify that the repository is private before you submit sensitive information.

Include the affected version, deployment details, impact, and reproduction steps.
Remove credentials, user data, and restricted Wiki content from examples and logs.
Rotate exposed credentials before you discuss their replacement.

Report upstream-only vulnerabilities to the relevant upstream maintainers.

## Security checks

Wiki Copilot audits its deployed services and its build, test, and CI dependencies.
Desktop, widget, mobile, and disabled upstream workflow manifests are outside this deployment scope.

See [the security setup](docs/security.md) for the checks, credentials, and known limits.
