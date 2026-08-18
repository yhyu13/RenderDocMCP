# JOURNEY — RenderDoc Agent Verification & Fix Harness

> Project history in two-column form. **Me** = the human driving; **You** = Kilo (the agent).
> Started 2026-08-18. This journey spans two repos: the three spec documents live in
> `renderdoc-skill/`, and the implementation landed in this repo, `RenderDocMCP/rdc_harness/`.

## The spec documents (requirements)

- `renderdoc-agent-interview-guide.md` — token funnel, MCP-vs-Skill split, anomaly rules, SAM chunking, semi-transparent particles.
- `renderdoc-AI-Agent-token高效指南.md` — Layer1/Layer2/Resource summaries, auto-red-flags, early-stop.
- `renderdoc-perception-agent-design.md` — L1 deterministic + L2 behavioral verification, shader edit/replay loop, fix report.

## Two-column log

| Me | You |
|---|---|
| Handed the 3 spec docs and asked: do `renderdoc-skill/` and `RenderDocMCP/` meet them? Then (1) plan the gap closure + double-check best practice, (2) execute + build, (3) self-critic + improve. "Long task, set goals." | Read all 3 docs and both repos end-to-end. Gap analysis: both repos expose only MCP **data-access** tools; all 3 docs converge on a missing **orchestrator + double-layer (L1/L2) verification + report** glue, plus an auto-red-flags rule engine (Doc2 §10.2, Doc1 §2.2, Doc3 §3). |
| — | Proposed the plan: build a pure-Python, RenderDoc-agnostic `rdc_harness/` in `RenderDocMCP`. Rationale: `renderdoc` module isn't installed here → the logic must be GPU-free and unit-testable; Doc3 §3.3 mandates "deterministic checks before model" (zero-model rules). RenderDoc I/O sits behind `ShaderBackend`/`ShaderPatcher` protocols. |
| — | Built `rdc_harness/` (`models` / `rules` / `behavioral` / `summarize` / `orchestrator` / `report`) + 5 test files. Fixed two test-fixture bugs (bottleneck fixture was actually 57% pixel-shader; orchestrator returns the *final* patched source, not the original). 40 tests green. |
| — | Self-critic round 1: added numpy fast path to `pixel_diff`/`psnr` (with pure-Python fallback + parity test), fixed `score_from_report` no-signal→1.0 so "unverifiable" can't read as "converged", removed unused imports. 40 tests + end-to-end demo. |
| Critic #1 (P0/P1/P2): wheel `packages` excludes `rdc_harness`; no process-placement note (must not import from RenderDoc's Python 3.6 extension); `rt_hash` copies the buffer; `run_behavioral` no short-circuit on hash mismatch; `rule_bandwidth` + `check_min_lod` false-PASS on missing data; `report.py` untested; orchestrator boundary untested; no test runner/CLI. | Fixed all: added `rdc_harness` to wheel packages, `__init__` process note, zero-copy `rt_hash`, hash-mismatch short-circuit, bandwidth/min_lod guards (this caught a real `None`-append bug in `run_deterministic`), `test_report.py`, `max_round=0` + history-content tests, `ShaderPatcher.patch` contract, `__main__.py` CLI with `utf-8-sig` BOM handling, `test_cli.py`. 57 tests green. |
| Accepted `/review uncommitted`. | Ran the review: spawned 6 parallel track sub-agents (security / performance / business logic / deploy safety / duplication / dead code) → 9 findings (5 WARNING + 4 SUGGESTION). Recommendation: NEEDS CHANGES. |
| Critic #2: confirmed all 9 findings, added one more (`rule_setpass_rt` missing-data shape), gave a recommended fix order. | Implemented in order: `OverflowError` catch in `_num`; `pass_threshold` default 0.05→0.01 (WARN boundary); SKIP emission for the 8 frame-level rules + non-vacuous `all_pass()`; single-pass `_compute_stats` (int16 diff + int32 squares — no float64, no duplicate full passes, no `bytes()` copies); status-based `threshold_verdict`; `_result` dedup (imported from `rules`); removed unused imports. 63 tests green. |
| Critic #3: verified 8/8 fixes against source; flagged "why 1.0 by default" in `score_from_report` as worth a comment. | Pointed out the `score_from_report` docstring already documents it ("no pixel-diff evidence → 1.0 so the orchestrator never mistakes 'unverifiable' for 'converged'"); kept the *semantic* sentinel question deferred to P3. |
| Acknowledged ("Critic closed.") and asked to dump this `JOURNEY.md`. | Wrote it to both repos. |

## Final state

- **Deliverable**: `rdc_harness/` — a RenderDoc-agnostic, GPU-free, unit-tested verification + shader-fix orchestrator core, plus a `RenderDocShaderBackend` seam and a CLI.
- **Coverage**: Doc1 (token funnel + MCP/Skill split + anomaly rules), Doc2 (Layer1/Layer2 summaries + `auto_red_flags`), Doc3 (L1 deterministic + L2 behavioral + shader edit/replay loop + fix report).
- **Tests**: 63/63 pass (`python -m unittest discover -s tests`), `py_compile` clean.
- **Deferred (P3)**: `check_binding_completeness` docstring drift; `score_from_report` no-signal sentinel *semantics*; `rule_setpass_rt` missing-data shape.
- **Future work**: register MCP-server tools (`run_deterministic_checks`, `iterate_shader_fix`) and fill in the real `RenderDocShaderBackend` bodies — blocked on deciding the compile/inject/replay tool shapes and requires a `renderdoc`/RenderDoc environment.
