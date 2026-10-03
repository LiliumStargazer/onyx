"""Typed vulnerability reports and native Dependabot alerts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Finding(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: str = Field(min_length=1)
    ecosystem: str = Field(min_length=1)
    package: str = Field(min_length=1)
    severity: Literal["critical", "high", "moderate", "low", "unknown"]
    manifest: str = Field(min_length=1)
    version: str = ""
    title: str = ""

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
