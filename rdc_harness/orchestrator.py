"""Shader edit -> replay -> verify orchestrator (perception-agent design doc §4.2).

The loop that was explicitly called out as missing (doc3 §5 "orchestrator +
双层验证 + 报告 glue"). It is RenderDoc-agnostic: the RenderDoc-specific
operations (compile/inject/replay/verify) live behind two protocols so the
loop is fully unit-testable without a GPU, and can later be backed by the
MCP bridge or the raw RenderDoc controller API.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from .behavioral import score_from_report
from .models import VerificationReport


class ShaderCompileError(Exception):
    """Raised when shader source fails to compile (static check)."""


class ShaderBackend(Protocol):
    """RenderDoc-side operations needed by the loop (doc3 §4.3)."""

    def compile_shader(self, hlsl: str, stage: str) -> str:
        """Compile HLSL/GLSL source; return an opaque compiled-shader handle.

        Raises ShaderCompileError on failure. The handle is consumed verbatim
        by :meth:`inject_shader` (for RenderDoc it is a replacement shader
        resource id string).
        """
        ...

    def inject_shader(self, event_id: int, stage: str, compiled: str) -> None:
        """Replace the shader bound at event_id/stage with ``compiled``."""
        ...

    def replay(self, event_id: int) -> None:
        """Replay the capture up to event_id, applying replacements."""
        ...

    def run_l1(self) -> VerificationReport:
        """Run deterministic verification on the replayed frame."""
        ...

    def run_l2(self) -> VerificationReport:
        """Run behavioral verification (golden diff) on the replayed frame."""
        ...


class ShaderPatcher(Protocol):
    """Produces the next shader source given the failed L2 report + history.

    Contract: ``original`` is always the unmodified baseline source (not the
    previous round's output); ``feedback`` is the current round's L2 report;
    ``history`` is the full list of prior rounds (each ``{"round", "score",
    "l2"}``), including the current round, in order.
    """

    def patch(
        self,
        original: str,
        feedback: VerificationReport,
        history: Sequence[dict[str, Any]],
    ) -> str:
        ...


def iterate_shader_fix(
    *,
    original_hlsl: str,
    backend: ShaderBackend,
    patcher: ShaderPatcher,
    event_id: int,
    stage: str,
    max_round: int = 10,
    pass_threshold: float = 0.01,
) -> dict[str, Any]:
    """Run the full fix loop and return a structured result.

    Ordering follows doc3 §3.3 + §4.2:
        compile -> static check -> inject -> replay -> L1 -> (fail => needs_rebuild)
        -> L2 -> (score <= threshold => ok) -> patch -> repeat.

    ``pass_threshold`` defaults to the L2 WARN boundary (0.01): "ok" requires a
    clean PASS, not a WARN-band (1-5%) regression.
    """
    current = original_hlsl
    history: list[dict[str, Any]] = []

    for round_i in range(max_round):
        # Static check: compile before touching the capture.
        try:
            compiled = backend.compile_shader(current, stage)
        except ShaderCompileError as e:
            return {
                "status": "static_fail",
                "round": round_i,
                "source": current,
                "error": str(e),
                "history": history,
            }

        backend.inject_shader(event_id, stage, compiled)
        backend.replay(event_id)

        # L1 deterministic first — zero cost, blocks non-shader bugs.
        l1 = backend.run_l1()
        if not l1.all_pass():
            return {
                "status": "needs_rebuild",
                "round": round_i,
                "source": current,
                "l1": l1.to_dict(),
                "history": history,
            }

        # L2 behavioral.
        l2 = backend.run_l2()
        score = score_from_report(l2)
        history.append({"round": round_i, "score": score, "l2": l2.to_dict()})

        if score <= pass_threshold:
            return {
                "status": "ok",
                "round": round_i,
                "source": current,
                "score": score,
                "history": history,
            }

        current = patcher.patch(original_hlsl, l2, history)

    return {
        "status": "exhausted",
        "last_source": current,
        "history": history,
    }
