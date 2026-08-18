"""Structured data models for the RenderDoc verification harness.

Design principle (perception-agent design doc §7):
    "结构化 artifact > 自然语言" — every check and report is a typed,
    JSON-serializable object, not a free-text string, so the LLM/agent
    never loses context and a human can diff reports deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Severity of an anomaly or failed check."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CheckStatus(str, Enum):
    """Outcome of a single verification check."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"  # data required by the rule was not available


@dataclass
class CheckResult:
    """A single deterministic/behavioral check result.

    Every rule emits ``expected`` vs ``actual`` so failures are
    self-contained evidence (eventId/stage/resourceId where relevant).
    """

    rule: str
    status: CheckStatus
    severity: Severity
    message: str
    expected: Any = None
    actual: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "evidence": self.evidence,
        }


@dataclass
class VerificationReport:
    """A layer's worth of check results (L1 deterministic or L2 behavioral)."""

    layer: str
    checks: list[CheckResult] = field(default_factory=list)

    def all_pass(self) -> bool:
        """True only when at least one check ran (non-SKIP) and none failed.

        An empty or all-SKIP report means nothing was actually verified, so it
        must not vacuously pass (the deterministic layer gates the fix loop).
        """
        non_skip = [c for c in self.checks if c.status is not CheckStatus.SKIP]
        return bool(non_skip) and all(c.status is not CheckStatus.FAIL for c in non_skip)

    def passed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is CheckStatus.PASS]

    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is CheckStatus.FAIL]

    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is CheckStatus.WARN]

    def skipped(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is CheckStatus.SKIP]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "pass": len(self.passed()),
            "fail": len(self.failed()),
            "warn": len(self.warnings()),
            "skip": len(self.skipped()),
            "total": len(self.checks),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class Anomaly:
    """An auto-detected red flag surfaced by the local rule engine (Doc2 §10.2)."""

    rule: str
    severity: Severity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence,
        }
