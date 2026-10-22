# Implementation Plan: Draft Ranking (Week 0)

**Branch**: `plan-002-draft-ranking` | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-draft-ranking-week-0/spec.md`

**Design document**: [`docs/draft-rankings-algorithm-v1.md`](../../docs/draft-rankings-algorithm-v1.md), declared version `draft-v1`

## Summary

Publish a ranking in the window between the draft finishing and the first scored week, and keep that
same number alive all season as the forward-looking term of the in-season ranking.

The algorithm is already designed and deliberately shares the in-season all-play core: build each
team's *projected* nine-category week, run the existing all-play grid over it, shrink the result
toward even odds. No second scoring function.

The work is therefore not primarily algorithmic. It is **acquisition**: the project has no projection
input in the required shape, no archived projection snapshot, and no lifecycle gate to decide whether
a ranking is publishable at all. Three findings shape the plan:

1. **The existing projections file cannot satisfy the spec.** `rank/prior.py` reads
   `player_id,value` — one pre-aggregated scalar. FR-010 requires the nine categories with ratio
   categories as **makes and attempts**, and the design document calls that "a go/no-go question on
   the source, not a detail," because the category profile is the main reason this page is worth
   publishing at week 0.
2. **Projections are never archived, which breaks replay today.** They are read at rank time from a
   live file. Editing that file silently changes the output of replaying a past week — a Principle I
   violation that FR-011 and FR-012 exist to close.
3. **`rank/` performs filesystem I/O right now**, which Principle I forbids outright. See the
   Constitution Check.

## Technical Context

**Language/Version**: Python 3.14, pinned by `.python-version`, managed with `uv`

**Primary Dependencies**: no new runtime dependency. Reuses `httpx` (already present) only if a
networked projection source is ever adopted; the chosen source needs none. Dependency restraint
requires a new dependency be justified against a named requirement, and none is.

**Storage**: append-only file archive under `data/`, reusing `archive/store.py`. Two new archived
input kinds: a projection snapshot and draft results.

**Testing**: pytest. Offline by construction — the chosen projection source is a local file, so the
whole feature is testable without network.

**Target Platform**: GitHub Actions scheduled runner; also runnable locally

**Project Type**: single Python CLI batch generator

**Performance Goals**: not a factor. One run per week over 18 teams and ~180 rostered players; the
all-play grid is 18 × 17 × 9 comparisons, already implemented and fast.

**Constraints**: ranking and rendering must stay pure and offline; published page must stay under the
500KB budget and disclose no ranking-derived figure beyond rank and movement.

**Scale/Scope**: 18 teams, 9 categories, ~180 rostered players, one draft per season.

**NEEDS CLARIFICATION — the league's active roster slot configuration.** FR-018 requires respecting
active slot limits and position eligibility, and the slot-filling rule cannot be declared without the
real layout. This is a league setting the maintainer can read directly from the league's settings page
in a browser; it is not blocked on provider access. Everything else in this plan is decided. See
[research.md](research.md) D3.

## Constitution Check

*GATE: evaluated against constitution v2.1.0.*

| Principle | Assessment |
|---|---|
| **I. Deterministic rankings, reproducible pages** | **One pre-existing violation must be fixed by this feature** — see below. Otherwise satisfied: the draft computation is pure, carries its own declared version `draft-v1`, and both versions are recorded. The article is a nondeterministic acquisition stage, archived and replayed, which the principle permits. |
| **II. Never publish a broken page** | Satisfied and extended. Pre-draft publishes nothing *and exits zero* — a new, third outcome alongside "publish" and "fail", justified below. Projection failure or sub-threshold coverage publishes nothing, exits non-zero, notifies. Article failure degrades one section, not the run. |
| **III. Raw data archived and immutable** | Satisfied by new work. The projection snapshot and draft results are archived verbatim before use, with source identity and retrieval time, and are sufficient to recompute offline. This is what today's implementation lacks. |
| **IV. Static and accessible output** | Unaffected. No new rendering path: the week-0 page is the existing page with rank movement unavailable and a projection label. Tiers were rejected partly to avoid a second rendering path. |
| **V. Secrets out, member data minimal** | Satisfied. The projection source needs no credential. Draft results contain player and pick data, which is league data; no contact information is published. |

### Violation that must be fixed, not justified

**`src/ccsv_rumble/rank/prior.py:26` opens a file.** Principle I requires the ranking computation be
"free of I/O, network, and filesystem access", and the Technology constraints add that "Ranking and
rendering MUST have no network or push access, which is what makes Principle I testable."

`tests/unit/test_architecture.py` is the mechanism meant to enforce this, and it has a hole: it checks
the *import graph* against internal package names (`fetch`, `archive`, `publish`, …), so `import csv`
and `from pathlib import Path` pass unnoticed. Its own docstring says "A comment saying so decays; an
assertion does not" — the assertion is simply narrower than the rule.

This plan treats it as in scope rather than pre-existing-and-tolerated, because FR-021 restates the
purity requirement for exactly this computation and FR-011 moves the file read into acquisition
anyway. Two changes:

- Projection loading moves out of `rank/` into an acquisition stage. `rank/` receives parsed values.
- The architecture test is extended to fail on filesystem and network access in a pure package, not
  only on forbidden imports.

### Justified deviation: a third run outcome

Principle II is written as a binary — publish a complete page, or publish nothing and report failure.
FR-004 adds a third: pre-draft publishes nothing and **exits zero without notifying**.

This is not a weakening. An undrafted league is a normal state, not a fault, and reporting it as a
failure every week until draft night would train the maintainer to ignore the notification channel —
which Principle II depends on being trustworthy. The distinction is recorded explicitly:

| Outcome | Publishes | Exit | Notifies |
|---|---|---|---|
| Complete page | yes | 0 | on degradation only |
| **Pre-draft (new)** | **no** | **0** | **no** |
| Failure | no | non-zero | yes |

The risk is that a real acquisition failure gets misclassified as pre-draft and goes quiet. FR-008
covers it: an incomplete draft is treated as pre-draft *and the reason publication was withheld must
be recorded*. The lifecycle decision is logged every run, so "we published nothing" is always
attributable.

### Post-design re-check

Re-evaluated after Phase 1. The design did not introduce a new violation, and it closed one.

| Principle | Post-design finding |
|---|---|
| I | **Improved.** Phase 2 archives the projection snapshot, which makes week-0 replay reproducible for the first time — today editing `data/projections.csv` silently changes the result of replaying a past week. Phase 3 removes the filesystem access from `rank/` and widens the test that failed to catch it. |
| II | Unchanged, plus the third outcome justified above. Phase 7 adds a refusal path that publishes nothing rather than a thin ranking. |
| III | **Satisfied by new work.** Two new archived input kinds, verbatim before parsing, with unparseable inputs routed to `_quarantine/` rather than becoming incomplete entries. |
| IV | **Confirmed unchanged.** Rejecting tiers (research D11) is what keeps this true — there is no new rendering path, so the accessibility and weight guarantees carry over untouched. `render/` is not in the changed-files list. |
| V | Unchanged. The projection source needs no credential, so nothing new reaches the secret store. |

Two design choices are worth recording as deliberate constraint-respecting, since each had a tempting
alternative that would have breached something:

- **`CategoryLine` is reused for projected totals** rather than a new projected type. This is what
  lets the all-play grid and the existing zero-attempt rule run unchanged, satisfying FR-019's "a
  second scoring function MUST NOT be introduced" and FR-027 structurally rather than by discipline.
- **The per-player scalar used for slot filling never scores a team.** A scalar prior is precisely
  what the design document §3 argues against; confining it to choosing contributors keeps team scoring
  category-wise.

One residual risk, carried rather than resolved: `DRAFT_SHRINK = 0.6` has no data behind it and is
acknowledged as a judgment call by its own design document. Scenario 8 in
[quickstart.md](quickstart.md) makes its justification executable, and it is the first refit target
after a season of archived weeks.

## Project Structure

### Documentation (this feature)

```text
specs/002-draft-ranking-week-0/
├── plan.md              # This file
├── research.md          # Phase 0: the eleven decisions, with rejected alternatives
├── data-model.md        # Phase 1: entities, fields, validation, state transitions
├── quickstart.md        # Phase 1: how to validate the feature end to end
├── contracts/
│   ├── projection-source.md   # The provider seam and the required input shape
│   └── draft-results.md       # Pick-by-pick record, and behaviour when absent
├── checklists/
│   └── requirements.md  # Existing spec quality checklist
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source code

```text
src/ccsv_rumble/
├── config.py                  # + DRAFT_ALGORITHM_VERSION, DRAFT_SHRINK, slot layout,
│                              #   coverage thresholds, slot-filling tiebreak
├── models.py                  # + PlayerProjection, ProjectionSnapshot, DraftResults,
│                              #   ProjectedTeamWeek, LifecycleState; DraftRankingEntry
│                              #   fields on the internal report
├── lifecycle.py               # NEW — pure: classify pre-draft / post-draft / in-season
├── fetch/
│   ├── projections.py         # NEW — acquisition: load, validate, reject percentage-only
│   └── draft.py               # NEW — acquisition: pick-by-pick draft results
├── archive/
│   └── store.py               # + projection snapshot and draft-results entries
├── rank/
│   ├── prior.py               # CHANGED — pure only; file reading removed
│   ├── projected.py           # NEW — pure: assemble the projected 18 × 9 grid
│   └── draft_score.py         # NEW — pure: all-play over projections, then shrink
├── article/
│   └── prompt.py              # + draft recap prompt over report + draft results
└── pipeline.py                # + lifecycle gate, projection acquisition, draft-ranking path

tests/
├── unit/
│   ├── test_architecture.py   # CHANGED — also forbid filesystem/network in pure packages
│   ├── test_lifecycle.py      # NEW
│   ├── test_projected_grid.py # NEW — slot filling, zero games, missing projections
│   ├── test_draft_score.py    # NEW — shrink, ties, zero attempts
│   └── test_projection_ingest.py  # NEW — percentage-only rejection (FR-010)
└── integration/
    ├── test_pre_draft_publishes_nothing.py   # NEW — exits zero, no notification
    ├── test_week0_page.py                    # NEW — 18 teams, movement unavailable
    └── test_coverage_threshold_refuses.py    # NEW — below threshold publishes nothing
```

**Structure Decision**: the existing five-stage separation is kept exactly — acquisition in `fetch/`
and `archive/`, pure computation in `rank/`, presentation in `report/` and `render/`, side effects in
`publish/` and `notify/`. This feature adds modules inside those existing boundaries and introduces
no second pipeline, which is what the spec's final assumption requires. `lifecycle.py` sits at the top
level beside `config.py` because it is consumed by `pipeline.py` and is pure, belonging to neither
acquisition nor ranking.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Third run outcome (pre-draft: no publish, exit zero, no notify) | FR-004. An undrafted league is a normal state; weekly failure notifications for it would erode trust in the only channel Principle II has | Treating pre-draft as a failure trains the maintainer to ignore notifications, which silently defeats Principle II's reporting requirement |
| Two declared algorithm versions recorded per run | `draft-v1` changes in-season `PowerScore`, so both must be traceable from one archived report | Citing one version cannot explain a rank that depends on both |
| Second declared constant set (`DRAFT_SHRINK`, coverage thresholds, slot layout) | FR-020, FR-026, FR-018 each require a declared documented constant | Literals at use sites are explicitly called a bug by the design document §7 |

No other deviation. In particular: no new runtime dependency, no second scoring function (FR-019),
no new rendering path, and no change to the publish or validation stages.

## Phase sequencing

Ordered so that each phase is independently verifiable and the riskiest input question is settled
first.

| Phase | Work | Gate |
|---|---|---|
| **0** | Confirm the league's roster slot layout; declare the projection schema | Slot layout known; schema written to `contracts/projection-source.md` |
| **1** | `lifecycle.py` + pre-draft behaviour | A pre-draft run publishes nothing, exits zero, does not notify |
| **2** | Projection ingest and archiving, with percentage-only rejection | A percentage-only file is refused at ingest; a valid snapshot is archived with source and retrieval time |
| **3** | Purity fix: move loading out of `rank/`, widen the architecture test | The widened test fails on the old code and passes on the new |
| **4** | Projected grid: slot filling, zero games, unprojected counts | Unit tests over fixtures, including a team with missing projections |
| **5** | `draft_score.py`: all-play reuse + shrink, both versions recorded | `s = 0.6` reproduces the design document's worked example |
| **6** | Week-0 page: 18 teams, movement unavailable, projection label | Rendered page passes the existing disclosure gate |
| **7** | Coverage threshold refusal | Below threshold publishes nothing, exits non-zero, notifies |
| **8** | Draft recap article, archived and replayed | Repeat run makes no model call; failure still publishes rankings |
| **9** | In-season role: prior recomputed from current rosters | Two snapshots differing by one star rank in the expected direction |

Phases 1–7 deliver User Story 1, the viable minimum. Phase 8 is User Story 2. Phase 9 is User Story 3.
User Story 4 is verified throughout by the replay test, which Phase 2 makes possible for the first
time.
