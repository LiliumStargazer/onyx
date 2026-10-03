"""Keep vulnerability reports within Wiki Copilot's deployment and CI scope."""

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

REPOSITORY = "LiliumStargazer/wiki-copilot"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_REQUIREMENTS = tuple(
    f"backend/requirements/{group}.txt"
    for group in ("default", "dev", "ee", "model_server")
)
ACTIVE_WORKFLOWS = {
    ".github/workflows/audit.yml",
    ".github/workflows/pr-quality-checks.yml",
    ".github/workflows/publish-wikijs-images.yml",
}
EXCLUSION_COMMENT = "Outside Wiki Copilot deployment and CI scope; managed by tools/wiki_copilot_security.py."


class Finding(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: str = Field(min_length=1)
    ecosystem: str = Field(min_length=1)
    package: str = Field(min_length=1)
    severity: Literal["critical", "high", "moderate", "low", "unknown"]
    manifest: str = Field(min_length=1)
    version: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, severity: object) -> object:
        return "moderate" if severity == "medium" else severity


class AuditReport(BaseModel):
    model_config = ConfigDict(strict=True)

    findings: list[Finding] | None
    ignored: list[Finding] | None = None
    blocking: list[Finding] | None = None
    excluded: list[Finding] = Field(default_factory=list)


class DependabotAlert(Finding):
    number: int
    state: Literal["open", "dismissed", "fixed", "auto_dismissed"]
    dismissed_comment: str | None = None


def normalize_python_package(package: str) -> str:
    return re.sub(r"[-_.]+", "-", package).lower()


def load_python_packages() -> dict[str, set[str]]:
    packages: dict[str, set[str]] = {}
    for manifest in PYTHON_REQUIREMENTS:
        exported = [
            (normalize_python_package(match[1]), match[2])
            for line in (REPOSITORY_ROOT / manifest).read_text().splitlines()
            if (
                match := re.match(
                    r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;\\]+)", line
                )
            )
        ]
        if not exported:
            raise ValueError(f"No pinned packages in {manifest}")
        for package, version in exported:
            packages.setdefault(package, set()).add(version)
    return packages


def is_used_dependency(finding: Finding, python_packages: dict[str, set[str]]) -> bool:
    manifest = finding.manifest.removeprefix("./")
    if (
        manifest.startswith("web/")
        or manifest in ACTIVE_WORKFLOWS
        or manifest in ("tools/ods/go.mod", "tools/ods/go.sum")
    ):
        return True
    if manifest in ("uv.lock", "pyproject.toml", *PYTHON_REQUIREMENTS):
        versions = python_packages.get(normalize_python_package(finding.package), set())
        return bool(versions) and (not finding.version or finding.version in versions)
    return False


def filter_dependency_report(
    report: AuditReport, python_packages: dict[str, set[str]]
) -> AuditReport:
    if report.ignored:
        raise ValueError("Wiki Copilot audits must run without advisory suppressions")
    used: list[Finding] = []
    excluded: list[Finding] = []
    for finding in report.findings or []:
        (used if is_used_dependency(finding, python_packages) else excluded).append(
            finding
        )
    return AuditReport(
        findings=used,
        ignored=[],
        blocking=[finding for finding in used if finding.severity == "critical"],
        excluded=excluded,
    )


def github_api(*arguments: str) -> str:
    return subprocess.check_output(
        ["gh", "api", *arguments],
        text=True,
        env={**os.environ, "GH_REPO": REPOSITORY},
    )


def sync_dependabot_alerts(python_packages: dict[str, set[str]]) -> None:
    # ponytail: filtering follows alert creation; paid auto-triage removes this delay.
    alerts = github_api(
        "--paginate",
        f"repos/{REPOSITORY}/dependabot/alerts?per_page=100",
        "--jq",
        ".[] | {id:.security_advisory.ghsa_id,ecosystem:.dependency.package.ecosystem,"
        "package:.dependency.package.name,severity:.security_advisory.severity,"
        "manifest:.dependency.manifest_path,number,state,dismissed_comment} | @json",
    )
    for line in alerts.splitlines():
        alert = DependabotAlert.model_validate_json(line)
        used = is_used_dependency(alert, python_packages)
        endpoint = f"repos/{REPOSITORY}/dependabot/alerts/{alert.number}"
        if not used and alert.state == "open":
            github_api(
                "--method",
                "PATCH",
                endpoint,
                "-f",
                "state=dismissed",
                "-f",
                "dismissed_reason=not_used",
                "-f",
                f"dismissed_comment={EXCLUSION_COMMENT}",
            )
            print(f"Excluded Dependabot alert #{alert.number}: {alert.manifest}")
            time.sleep(1)  # Stay below GitHub's content-generation rate limit.
        elif (
            used
            and alert.state in ("dismissed", "auto_dismissed")
            and alert.dismissed_comment == EXCLUSION_COMMENT
        ):
            github_api("--method", "PATCH", endpoint, "-f", "state=open")
            print(f"Restored Dependabot alert #{alert.number}: {alert.manifest}")
            time.sleep(1)


def main() -> int:
    python_packages = load_python_packages()
    if sys.argv[1:] == ["sync-dependabot"]:
        sync_dependabot_alerts(python_packages)
        return 0
    if len(sys.argv) < 4 or sys.argv[1] != "filter":
        raise SystemExit(
            "Usage: wiki_copilot_security.py filter OUTPUT INPUT... | sync-dependabot"
        )
    reports = [
        AuditReport.model_validate_json(Path(filename).read_text())
        for filename in sys.argv[3:]
    ]
    report = AuditReport(
        findings=[finding for source in reports for finding in source.findings or []],
        ignored=[finding for source in reports for finding in source.ignored or []],
    )
    filtered = filter_dependency_report(report, python_packages)
    Path(sys.argv[2]).write_text(filtered.model_dump_json(indent=2) + "\n")
    print("## Wiki Copilot dependency audit\n")
    print(
        f"{len(filtered.findings or [])} findings; {len(filtered.excluded)} outside scope.\n"
    )
    for finding in filtered.findings or []:
        print(
            f"- **{finding.severity}** {finding.package}@{finding.version}: {finding.id} ({finding.manifest})"
        )
    blocking = len(filtered.blocking or [])
    print(f"\n{blocking} critical finding(s) block publication.")
    return int(blocking > 0)


if __name__ == "__main__":
    sys.exit(main())
