# Taste Score — the standard

A deterministic, anti-gaming quality score that turns "taste" into one comparable
number a fleet of agents can optimize overnight. **Taste = what the artifact can do,
how truthfully it's documented, and whether the claims are provable — not vibes.**

Scorer: `scripts/taste_score.py` (run `python3 scripts/taste_score.py`, `--json` for a leaderboard).

## Why this shape

Taste is subjective, so it's useless as a competition metric unless you operationalize
it into **objective predicates** — file exists / symbol present / test green / git clean /
doc current. Every check is a binary gate, so:

- **Any agent lands the same number** (no judgment call, no "I think this is nice").
- **It's hard to inflate.** You can't fake a green test, a present `@mcp.tool`, a tracked
  artifact, or a named-dead-import removal. A score only goes up by adding real value.
- **It leaves headroom.** The baseline is ~81/100; a project that merely "has" the features
  but hasn't proven them can't reach 100. Reaching 100 requires closing genuinely-open work
  (live-GPU validation, A/B diff, API Inspector, CI, a benchmark).

## Dimensions & weights (sum 1.0)

| # | Dimension | Weight | What it rewards |
|---|-----------|--------|-----------------|
| 1 | TRUTH & EVIDENCE | 0.22 | Admitting gaps, separating verified-vs-open, real measured numbers, no overclaim. |
| 2 | CAPABILITY PARITY | 0.22 | Human 90% loop coverage, closed shader-edit/replay loop, beyond-GUI features. |
| 3 | CRAFT & HEALTH | 0.20 | Green suite (≥150 tests), py_compile + Py3.6-boundary gate, no dead code/tracked .pyc. |
| 4 | DOCS & ONBOARDING | 0.14 | README/AGENTS current, stale mirrors flagged, harness skills, 说人话 shape. |
| 5 | FOOTPRINT & DISTRIBUTION | 0.12 | Token discipline (caps), export path-not-bytes contract, bounded responses, wheel scope. |
| 6 | VOICE & CONTENT | 0.10 | Real content packs, real figures, inference marked-not-asserted. |

~36 checks total; the exact rubric lives in `scripts/taste_score.py::DIMENSIONS`.

## Baseline — RenderDocMCP (2026-09-01): **81.02 / 100**

The 7 failures are the honest next tasks (each is a P1 roadmap item):

- **TRUTH** — no live-GPU validation closed; no benchmark artifact.
- **CAPABILITY** — no A/B two-capture diff tool; no API Inspector.
- **CRAFT** — no CI config (`.github/workflows`).
- **DOCS** — `AGENTS.md` does not name `debug_trace_export` (that bullet is still pending approval).
- **FOOTPRINT** — no quantified perf/benchmark doc.

## Anti-gaming rules (enforced by construction)

1. Binary predicates — you score 0 or 1 per check, never "partial credit by vibes."
2. A check passes only if the artifact **exists and is verifiable** (green test / tracked file / current doc). Deleting a test or doc to move a *different* ratio doesn't help — it only removes evidence.
3. Truth checks **punish** absolute claims with no qualifying measurement, and **reward** admitting a gap. Honest "not yet supported" is a point; silent overclaim is not.
4. The manifest (`owns_capture` etc.) declares a repo's scope, so an agent is never pushed to duplicate work owned by a sibling repo.

## How a fleet competes overnight

Reuse your existing orchestration skills (`gated-agent-pipelines`, `cron-pipeline-state-machine`,
`kanban-orchestrator`/`worker`, `autonomous-campaign-governance`). One round:

1. **Score baseline** → `python3 scripts/taste_score.py --json` (gate the campaign on it).
2. **Assign work** → the cabal picks the lowest-scoring dimension (or the cheapest correct win) and hands it to an agent. Each agent works on its **own branch**, scoped to ONE dimension to avoid merge fights.
3. **Hard gate** → the agent must keep the score **monotone in the right direction** and leave every existing gate green (`scripts/test_all.py`, suite, py_compile). No cosmetic renames, no test deletions, no doc deletions to inflate a ratio.
4. **Score + commit** → the agent runs the scorer; commits only if the **target dimension rose** AND **no other dimension fell**. Otherwise reverts (failed rounds never commit).
5. **Rollback rule** → any merged round that regresses a dimension on the next full run is reverted by the overseer (`kanban-cron-overseer`).
6. **Leaderboard** → the overseer aggregates `--json` scores nightly, posts a ranked table, and repeats.

**Winning = raising the total without lowering any dimension and without flipping a gate red.** The
score is the metric; the gates are the constitution.

## Applying it to another project

Give the project a manifest (tools file, tool names, capture ownership, doc names) and point the
scorer at it:

```
python3 scripts/taste_score.py /path/to/project
# or: edit DEFAULT_MANIFEST (or a --manifest file) to match the repo's scope
```

The 6 dimensions are generic; only the manifest is repo-specific. Flip `owns_capture` (and the
tool lists) per project. Register this as a skill (`taste-score`) to reuse it across the portfolio.
