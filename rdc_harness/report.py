"""Before/after fix report (perception-agent design doc §4.1 ``report/``).

Produces a structured, diffable report a human (TA/engineer) can approve
without reopening RenderDoc — the "Report 给人，不给人 autonomy" principle.
"""

from __future__ import annotations

from typing import Any, Mapping


def build_fix_report(
    *,
    result: Mapping[str, Any],
    original_hlsl: str,
    final_hlsl: str | None = None,
    target_event_id: int | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """Assemble a structured fix report from an orchestrator result."""
    history = result.get("history", [])
    report: dict[str, Any] = {
        "status": result.get("status"),
        "target": {
            "event_id": target_event_id,
            "stage": stage,
        },
        "rounds": len(history),
        "best_score": min((h.get("score", 1.0) for h in history), default=1.0),
        "history": history,
        "final_source": final_hlsl or result.get("source") or result.get("last_source"),
    }
    if "l1" in result:
        report["l1_blocking"] = result["l1"]
    if "error" in result:
        report["error"] = result["error"]
    return report


def render_markdown(report: Mapping[str, Any], original_hlsl: str) -> str:
    """Render a fix report as human-readable markdown."""
    status = report.get("status", "?")
    target = report.get("target") or {}
    lines = [
        "# RenderDoc Shader Fix Report",
        "",
        f"- Status: **{status}**",
        f"- Target: event {target.get('event_id', '?')} ({target.get('stage', '?')})",
        f"- Rounds: {report.get('rounds', 0)}",
        f"- Best score: {report.get('best_score', 1.0):.4f} (0 = perfect)",
        "",
    ]
    if report.get("error"):
        lines.append(f"Error: {report['error']}")
        lines.append("")
    if report.get("l1_blocking"):
        lines.append("## Blocked by L1 deterministic checks")
        lines.append("```json")
        import json
        lines.append(json.dumps(report["l1_blocking"], indent=2))
        lines.append("```")
        lines.append("")

    for h in report.get("history", []):
        l2 = h.get("l2", {})
        lines.append(f"## Round {h.get('round')} — score {h.get('score', 1.0):.4f}")
        for check in l2.get("checks", []):
            lines.append(f"- [{check.get('status')}] {check.get('rule')}: {check.get('message', '')}")
        lines.append("")

    final = report.get("final_source")
    if final and final != original_hlsl:
        lines.append("## Final shader patch")
        lines.append("```diff")
        lines.append(diff_text(original_hlsl, final))
        lines.append("```")

    has_body = bool(
        report.get("history")
        or report.get("error")
        or report.get("l1_blocking")
        or (final and final != original_hlsl)
    )
    if not has_body:
        lines.append("No rounds captured — the loop did not run or produced no history.")

    return "\n".join(lines)


def diff_text(a: str, b: str) -> str:
    """Minimal line diff (prefix ``-``/``+``). Good enough for patch display."""
    import difflib
    return "".join(
        difflib.unified_diff(a.splitlines(True), b.splitlines(True), lineterm="")
    )
