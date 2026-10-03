import json
import subprocess

import pytest
from pydantic import ValidationError
from wiki_copilot_security import (
    AuditReport,
    filter_dependency_report,
    sync_dependabot_alerts,
)


def test_audit_keeps_used_dependencies_and_rejects_invalid_reports() -> None:
    report = AuditReport.model_validate(
        {
            "findings": [
                {
                    "id": "GHSA-web",
                    "ecosystem": "npm",
                    "package": "next",
                    "severity": "critical",
                    "manifest": "web/bun.lock",
                },
                {
                    "id": "GHSA-widget",
                    "ecosystem": "npm",
                    "package": "next",
                    "severity": "critical",
                    "manifest": "bun.lock",
                },
                {
                    "id": "GHSA-models",
                    "ecosystem": "PyPI",
                    "package": "sentence_transformers",
                    "severity": "critical",
                    "manifest": "uv.lock",
                },
                {
                    "id": "GHSA-loadtest",
                    "ecosystem": "PyPI",
                    "package": "locust",
                    "severity": "critical",
                    "manifest": "uv.lock",
                },
                {
                    "id": "GHSA-ci",
                    "ecosystem": "GitHub Actions",
                    "package": "actions/checkout",
                    "severity": "medium",
                    "manifest": ".github/workflows/publish-wikijs-images.yml",
                },
                {
                    "id": "GHSA-disabled-ci",
                    "ecosystem": "GitHub Actions",
                    "package": "actions/checkout",
                    "severity": "critical",
                    "manifest": ".github/workflows/pr-desktop-build.yml",
                },
            ]
        }
    )
    filtered = filter_dependency_report(report, {"sentence-transformers": {"5.4.1"}})
    assert [finding.id for finding in filtered.findings or []] == [
        "GHSA-web",
        "GHSA-models",
        "GHSA-ci",
    ]
    assert [finding.id for finding in filtered.blocking or []] == [
        "GHSA-web",
        "GHSA-models",
    ]
    assert len(filtered.excluded) == 3
    assert filtered.findings is not None
    assert filtered.findings[-1].severity == "moderate"
    assert filter_dependency_report(AuditReport(findings=None), {}).blocking == []
    assert report.findings is not None
    report.findings[4].title = "unverified pin — Actions version unavailable"
    with pytest.raises(ValueError, match="Action pin could not be verified"):
        filter_dependency_report(report, {"sentence-transformers": {"5.4.1"}})
    report.ignored = report.findings
    with pytest.raises(ValueError, match="without advisory suppressions"):
        filter_dependency_report(report, {"sentence-transformers": {"5.4.1"}})
    with pytest.raises(ValidationError):
        AuditReport.model_validate({"findings": [{"id": "malformed"}]})
    with pytest.raises(ValidationError):
        AuditReport.model_validate({})


def test_native_sync_preserves_used_alerts_and_manual_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = {1: "open", 2: "open", 3: "dismissed", 4: "dismissed"}
    comments = {
        1: None,
        2: None,
        3: "Outside Wiki Copilot deployment and CI scope; managed by tools/wiki_copilot_security.py.",
        4: "Reviewed manual exception",
    }

    def github_response(command: list[str], **_kwargs: object) -> str:
        if "--method" not in command:
            assert "state=all" not in command[3]
            return "\n".join(
                json.dumps(
                    {
                        "id": f"GHSA-{number}",
                        "ecosystem": "npm",
                        "package": "next",
                        "severity": "critical",
                        "manifest": "bun.lock" if number == 2 else "web/bun.lock",
                        "number": number,
                        "state": state,
                        "dismissed_comment": comments[number],
                    }
                )
                for number, state in states.items()
            )
        number = int(command[command.index("PATCH") + 1].rsplit("/", 1)[1])
        states[number] = next(
            argument.split("=", 1)[1]
            for argument in command
            if argument.startswith("state=")
        )
        return "{}"

    monkeypatch.setattr(subprocess, "check_output", github_response)
    sync_dependabot_alerts({})
    assert states == {1: "open", 2: "dismissed", 3: "open", 4: "dismissed"}
