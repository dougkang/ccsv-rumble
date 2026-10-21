# Implementation Plan: Power Ranking Article Generator

**Branch**: `001-power-ranking-article` | **Date**: 2026-10-20 | **Spec**: [spec.md](./spec.md)

**Revised 2026-10-20** after `/speckit-clarify` added FR-037–053. Three structural consequences:
the site is multi-page, one run may process several weeks, and corrections must be acquired before
any ranking is computed.

**Input**: Feature specification from `/specs/001-power-ranking-article/spec.md`

## Summary

A weekly Python batch job that pulls the full 18-team category grid from the Yahoo Fantasy Sports
API, archives it immutably, computes power rankings with the all-play algorithm declared in
`docs/rankings-algorithm-v1.md`, derives notable events and movement significance, then asks
Claude to write a short article explaining the week. It renders a static per-week page plus an
index and pushes them to a separate, unlisted GitHub Pages repository.

`fetch` and `article` are the only stages that touch the network. `rank`, `report`, and `render`
are pure functions of their inputs, which is what makes Constitution Principle I testable. A replay
run skips `fetch` and `article` entirely and reads both from the archive.

### Run sequence

A run is no longer one pass over one week. The ordering below is load-bearing — steps 2 and 3 must
complete before any ranking is computed, because a correction to week 5 changes the recency-weighted
history that week 6's ranking is built from.

```
1. resolve target week; detect archived gaps                      (FR-037)
2. acquire correction window: re-fetch last N completed weeks     (FR-045)
3. acquire gap weeks                                              (FR-038)
4. archive — new entry for changed weeks, first entry for gaps    (FR-046)
5. for each gap week, ascending:                                  (FR-039)
       rank → report → article → validate → render → buffer
6. current week:
       rank (over corrected history) → report → article → validate → render → buffer
7. render index                                                   (FR-040)
8. diff buffer against published; if changed, ONE atomic push     (FR-042)
9. notify: weeks backfilled, corrections found, articles failed   (FR-030b, 043, 050)
```

Two consequences worth stating plainly:

- **Nothing publishes until every week is fully processed.** Step 8 is a single push, so rendered
  output for all weeks is buffered in memory or a staging directory first. A partial backfill is
  never visible.
- **One run may call Claude several times** — once per backfilled week plus once for the current
  week. A per-week article failure degrades only that week's page and the loop continues (FR-044).

## Technical Context

**Language/Version**: Python 3.14 (pinned by `.python-version`), managed with `uv`

**Primary Dependencies**: `httpx` (Yahoo REST + OAuth2 refresh), `anthropic` (article generation),
`Jinja2` (HTML templating). Four runtime dependencies total, each justified in
[research.md](./research.md) §7 against the constitution's dependency-restraint rule.

**Storage**: JSON files committed to this repository under `archive/`. Append-only, one directory
per league week, **with multiple numbered entries per week** so a correction lands beside the
original rather than replacing it (FR-046). No database — the dataset is ~18 teams × ~24 weeks.

**Testing**: `pytest`, with golden-file comparison for rendered HTML and fixture-based tests for
the ranking math.

**Target Platform**: Linux CI runner (GitHub Actions) for the weekly run; output is static files
served by GitHub Pages.

**Project Type**: CLI batch tool (single project)

**Performance Goals**: Not latency-sensitive — one run per week. The full run should complete well
within a CI job's default timeout; the Yahoo fetch is ~20 requests.

**Constraints**: **Each** rendered page under 500KB compressed (the budget is per page, not per
site); pages readable with JavaScript disabled; replay from archive must work with no network
access; no secret or member PII in output, logs, or archive; every page carries a `noindex`
directive and the site serves a crawler-disallowing `robots.txt` (FR-051); the publish repository
name must not be derivable from the league, church, or member names (FR-052).

**Scale/Scope**: 18 teams, 9 categories, ~24 weeks per season — so ~25 pages plus an index by
season's end. 153 category comparisons and 17 matchup replays per team per week. Trivial compute;
the index is a flat list of ~25 links and needs no pagination.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates derived from `.specify/memory/constitution.md` v2.0.0.

| Gate | Design response | Status |
|---|---|---|
| **I.** Ranking computation is a pure function of snapshot + declared algorithm version; own module, no I/O | `rank/` imports nothing from `fetch/`, `archive`, or `publish`. Constants in `config.py`, version string `v1` recorded in every result. | ✅ |
| **I.** Rendering deterministic, byte-identical for identical snapshot | `render/` is pure; sorted iteration everywhere; `generated_at` injected as an explicit parameter. Enforced by golden-file test. | ✅ |
| **I.** Nondeterministic stage confined to acquisition, output archived | Claude call lives in `article/generate.py`, invoked only by the acquire phase; its output is written to the snapshot before render runs. | ✅ |
| **I.** Regeneration MUST NOT invoke a nondeterministic stage | `--from-archive` wires a reader in place of both `fetch` and `article`. Enforced by a test asserting no client is constructed. | ✅ |
| **II.** Publish gated on validation; no push on failure; previous page stays live | `publish` runs only after report validation and HTML validation pass. Any exception short-circuits before the push. | ✅ |
| **II.** All-or-nothing publish | Single commit containing every generated file, pushed once. | ✅ |
| **II.** Failure exits non-zero and notifies through a configured channel | Non-zero exit; notification channel decided in [research.md](./research.md) §3. | ✅ |
| **II.** Safe to re-run; no corruption on duplicate runs | Archive writes are keyed by league week and refuse to overwrite; publish is a no-op when content is unchanged. | ✅ |
| **II.** No commit when output identical to published | Content compared before commit. | ✅ |
| **II.** "Complete" defined per feature; optional content cannot block publication | Spec FR-029 defines rankings-only as complete; `article` is explicitly optional in the render contract. | ✅ |
| **III.** Raw acquired inputs archived before transformation | Raw Yahoo JSON written verbatim, pre-parse. | ✅ |
| **III.** Archive includes model-generated output | Article text + validation outcome archived alongside the raw fetch. | ✅ |
| **III.** Append-only; offline replay exercised by tests | Writes refuse to clobber; a replay test runs with network access patched out. | ✅ |
| **IV.** Static output, no serve-time runtime | Jinja2 renders at build time to plain HTML/CSS. | ✅ |
| **IV.** Readable with JS disabled; semantic tables; 4.5:1 contrast; <500KB; no third-party fetch | Zero JavaScript in v1. Rankings are a real `<table>` with `<th scope>`. Fonts and CSS inlined/local. | ✅ |
| **IV.** Templates data-driven | Templates read the publishable report; no league facts hardcoded. | ✅ |
| **V.** No credentials in repo, archive, or output; scoped push token; rotatable | All secrets from environment. Push token scoped to the publish repo only. Archive scrubbing asserted by test. | ✅ |
| **V.** Output limited to league-relevant info; no PII; no analytics | Publishable report carries team names, manager display names, stats. No contact info. No analytics or embeds. | ✅ |
| **Spec FR-013/015** Article stage never sees the internal report | `article/generate.py` accepts only `PublishableReport`; the internal report is not importable from that package path. | ✅ |
| **Spec FR-032** No ranking-derived number published except rank and movement | `PublishableReport` carries no numeric metric fields at all — enforced by its schema, not by template discipline. | ✅ |
| **II.** All-or-nothing publish, now spanning multiple weeks (FR-042) | Every week's output is buffered and diffed before a single commit and push. A failed week aborts before the push, so no partial backfill is ever visible. | ✅ |
| **III.** Append-only archive under corrections (FR-046) | Each week directory holds numbered entries; the writer creates a new entry and never opens an existing one for write. | ✅ |
| **I.** Replay reproduces the page that was published, not a corrected version (FR-049) | Each rendered page records the `entry_id` it was built from; replay resolves that exact entry rather than the week's latest. | ✅ |
| **IV.** Page weight budget under a multi-page site | Budget asserted per page in the render validation step. The index is a flat link list. | ✅ |
| **IV.** Static output includes crawler directives (FR-051) | `robots.txt` and the `noindex` meta tag are build-time static output — no serve-time behavior. | ✅ |
| **V.** Unlisted URL is not treated as access control | Spec records this explicitly; the no-PII rules (FR-024) remain the actual protection and are unchanged. | ✅ |

**No violations. Complexity Tracking section omitted.**

One gate deserves emphasis because it is the easiest to erode later: **FR-032 is enforced by the
shape of the data structure, not by remembering to leave numbers out of a template.** If a power
score cannot be represented in `PublishableReport`, it cannot leak into the page or the article.

## Project Structure

### Documentation (this feature)

```text
specs/001-power-ranking-article/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── cli.md           # Command-line contract
│   ├── data-source.md   # Yahoo provider interface + required fields
│   └── article-io.md    # Article stage input/output contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/ccsv_rumble/
├── __init__.py
├── cli.py                   # Entry point: run / dry-run / replay modes
├── config.py                # ALL declared constants (algorithm weights, budgets, timezone)
├── models.py                # Snapshot, Ranking, Event, reports (typed, no behavior)
├── schedule.py              # Gap detection + correction window → the list of weeks to process
├── fetch/
│   ├── provider.py          # Provider protocol — the seam for a provider swap
│   └── yahoo.py             # Yahoo implementation (OAuth2 refresh, scoreboard by week)
├── archive/
│   ├── store.py             # Numbered entries per week; never opens an entry for write
│   ├── diff.py              # Detects whether a re-fetched week differs from its latest entry
│   └── scrub.py             # Credential scrubbing before any write
├── rank/                    # PURE — no imports from fetch/, archive/, publish/
│   ├── allplay.py           # EMW + CAW, tie handling, ratio categories
│   ├── score.py             # PowerScore composite, shrinkage, recency weighting
│   ├── significance.py      # Significant vs within-noise classification
│   └── events.py            # Notable event derivation from snapshot deltas
├── report/
│   ├── internal.py          # Full detail — archived, never published
│   └── publishable.py       # Redacted view — the only article/render input
├── article/
│   ├── generate.py          # Claude call (acquisition stage)
│   └── validate.py          # PURE — traceability, disclosure, tone checks
├── render/
│   ├── html.py              # PURE — deterministic render of one week's page
│   ├── index.py             # PURE — the current-week view + per-week link list
│   └── templates/
│       ├── page.html.j2     # One week. Carries noindex; omits article section when absent
│       ├── index.html.j2    # Current week + archive links
│       ├── robots.txt       # Static, disallow all
│       └── style.css
└── publish.py               # Clone, stage ALL weeks, compare, single commit, single push

tests/
├── unit/                    # Ranking math, significance, validation, scrubbing
├── integration/             # Replay-from-archive, failure paths, no-op publish
├── fixtures/                # Hand-built snapshots incl. ties and zero-attempt weeks
└── golden/                  # Expected HTML output

archive/                      # Committed, append-only
└── 2026-27/
    └── week-01/
        ├── entry-001/        # First acquisition
        │   ├── raw-yahoo.json    # Verbatim, pre-parse
        │   ├── snapshot.json     # Normalized
        │   ├── internal.json     # Full ranking detail
        │   ├── publishable.json  # Redacted
        │   └── article.json      # Text + validation outcome
        └── entry-002/        # A later correction to the same week (FR-046)
            └── ...
```

The `entry-NNN` level is the whole mechanism behind FR-046 through FR-049: corrections append a
new entry, the published page names the entry it used, and replay resolves that name. Without it,
"append-only archive" and "re-check for corrections" are in direct conflict.

**Structure Decision**: Single project, stage-per-package. The package boundaries are the
enforcement mechanism for Principle I rather than a stylistic choice — `rank/` and `render/`
importing nothing from `fetch/`, `archive/`, or `publish.py` is what makes "pure function of the
snapshot" an architectural property instead of a convention. That import rule is worth asserting
in a test.

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1 and again after the 2026-10-20 clarifications. All gates still pass.

**From the clarification round**, one decision carries the weight: the `entry-NNN` archive level.
"Corrections are added as new entries; history is not rewritten" (Principle III) and "re-check
recent weeks for corrections" (FR-045) are contradictory under a one-snapshot-per-week layout —
the only way to satisfy both is for a week to hold multiple entries and for each published page to
name the one it used. That single structural choice is what makes FR-046 through FR-049 coherent
rather than mutually exclusive.

Three design decisions from the original pass strengthened compliance beyond the initial check:

1. **Structured output for the article** (research.md §4) makes FR-022 traceability mechanical:
   Claude returns per-team `attributed_event_ids`, which `article/validate.py` checks against the
   report by set membership rather than by parsing prose for fabricated claims.
2. **`PublishableReport` carries no numeric metric fields**, so FR-032 is a type-level guarantee.
3. **Archive scrubbing runs on the write path**, not as a review step, so Principle V's
   "logs and archived snapshots MUST be scrubbed" cannot be forgotten per-call-site.

No new violations. Complexity Tracking remains omitted.

### One risk the clarifications introduced

A run that backfills several weeks now does more work before its single push, and each backfilled
week makes its own model call. The failure surface is wider: a five-week outage means one run doing
six weeks of ranking and six article calls, all buffered, with nothing published until the end. The
mitigations are already in the design — per-week article failures degrade rather than abort
(FR-044), and the push is atomic (FR-042) — but the **integration test for a multi-week backfill
with one failing article in the middle** is the single most valuable test in the suite, because it
exercises the interaction of three rules at once. It is called out in `quickstart.md` Scenario 11.
