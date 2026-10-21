# Specification Quality Checklist: Power Ranking Article Generator

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-17
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-10-17

**Failing: "No [NEEDS CLARIFICATION] markers remain"** — 2 markers open, both deliberate. Each
has multiple reasonable readings with materially different scope, and neither has a safe default:

- **FR-032** (Q1): `docs/rankings-algorithm-v1.md` §5 mandates publishing per-team component
  metrics for auditability; the feature request says never reveal the algorithm. Direct conflict.
  The instruction supersedes the doc, but the resulting scope must be confirmed — and the
  algorithm doc updated to match, or `/speckit-plan` inherits a contradiction.
- **FR-033** (Q2): whether model-written prose about named congregation members publishes
  unattended. The ratified architecture is fully unattended; this is a decision the user should
  make knowingly rather than inherit.

**Note on "No implementation details"**: the spec refers to "a language model" as a capability.
This is retained deliberately — it is part of the user's stated approach, not a technology
choice. No provider, model, or hosting decision appears in the spec; those are left to
`/speckit-plan`.

**Prerequisite recorded, not resolved**: Constitution Principle I requires byte-identical HTML
for identical inputs, which a live model call cannot satisfy as literally written. The spec's
Assumptions section records the amendment as a prerequisite to implementation. Not actioned
here — amending the constitution is out of scope for `/speckit-specify`.

### Validation iteration 2 — 2026-10-18 — ALL ITEMS PASS

Both clarifications answered; cadence revised from daily to weekly.

- **Q1 → Option A (strict).** FR-032–034 replace the open marker. No number derived from the
  ranking computation is published except rank and rank movement. FR-014 was amended so the
  publishable report may carry *qualitative* descriptors (e.g. an "easiest schedule" flag)
  without the underlying figures, and SC-010 was added to make the constraint measurable.
- **Q2 → Option A (unattended).** FR-035–036 replace the open marker. Automated validation is
  the sole safeguard, stated explicitly so it is not weakened at plan time.
- **Cadence → weekly.** Applied throughout the spec (US1, US3, SC-005, SC-006) and recorded as
  an assumption. This also fits the algorithm better than daily did: category totals are only
  meaningful at week boundaries, so a daily run would have recomputed rankings from partial
  mid-week data.

**Downstream doc updated**: `docs/rankings-algorithm-v1.md` §3 and §5 were revised to match
strict disclosure. §5 previously required publishing per-team component metrics; it now
specifies those insights are computed internally and surface as prose only, with a dated note
recording the supersession.

**Second constitution prerequisite added**: the constitution's preamble, Scheduling, and
Timekeeping sections all describe a once-a-day job and are now factually wrong. Recorded in the
spec's Assumptions alongside the Principle I amendment. Not actioned here.

### Validation iteration 3 — 2026-10-20 (`/speckit-clarify`) — ALL ITEMS PASS

Four clarifications integrated; 16/16 → **16/16 items passing** (no state changes, no regressions).

**Stale text corrected before questioning.** Two Assumptions were factually wrong and were fixed
independently of any clarification: the data source was still described as undecided
(`TODO(DATA_SOURCE)`) despite being resolved to Yahoo in `research.md` §1, and two constitution
amendments were listed as unmet prerequisites despite both landing in constitution v2.0.0 on
2026-10-18.

**Clarifications integrated** — FR-037 through FR-053 added, plus FR-030a/030b:

- **Missed weeks → auto-backfill and publish retroactively.** FR-037–044. Carries a structural
  consequence: retroactive publication requires per-week addresses, so the site becomes multi-page
  (FR-040). Recorded as an assumption and flagged for `plan.md`.
- **Upstream corrections → bounded re-check, correct forward only.** FR-045–050. Creates a
  deliberate archive/page divergence, made explicit in a note so it is not implemented as a
  contradiction. SC-005 extended to cover replay when later corrections exist.
- **Discoverability → unlisted and not indexed.** FR-051–053. A note records that this is obscurity
  rather than access control, which makes FR-024's no-PII rule *more* load-bearing. Also narrows
  the open `TODO(PUBLISH_TARGET)` decision with a naming constraint.
- **Rankings-only page → silent omission.** FR-030a. Consequence captured in FR-030b: the page
  gives readers no signal, so the notification channel becomes the only one, promoting FR-030/043/
  050 from conveniences to reliability requirements.

**Two items re-examined rather than assumed still-passing:**

- *"Success criteria are technology-agnostic"* — SC-011 initially named `robots.txt` and `noindex`
  literally, which made a success criterion mechanism-shaped. Reworded to the outcome ("instructs
  every search engine not to index it") while FR-051 retains the mechanism, where naming a web
  standard is appropriate.
- *"No implementation details"* — the spec now names the Yahoo Fantasy Sports API. Judged
  **compliant**: it appears only in Assumptions as a resolved external dependency, and the
  checklist's own "Dependencies and assumptions identified" item cannot be satisfied by a spec that
  refuses to name its data source. No client library, endpoint, or language choice appears in the
  requirements.

**Downstream impact — RESOLVED 2026-10-20** by a follow-up `/speckit-plan` run. All six stale
items addressed:

| Artifact | What changed | Status |
|---|---|---|
| `plan.md` structure | Render emits per-week pages + index + `robots.txt`; publish stages all weeks then pushes once | ✅ |
| `plan.md` §Technical Context | Per-page weight budget, crawler directives, URL constraint; archive holds numbered entries | ✅ |
| `plan.md` §Run sequence | **New section.** Corrections acquired before any ranking; ascending backfill; single push | ✅ |
| `plan.md` Constitution Check | 7 gate rows added for FR-042/046/049/051 and the multi-page budget | ✅ |
| `data-model.md` §1 | `Snapshot` gains `entry_id`, `acquired_at`, `supersedes`; `latest_entry` vs `entry(week, id)` accessors distinguished | ✅ |
| `data-model.md` §8 | Per-week and per-run transition diagrams; STAGED replaces PUBLISHED per week | ✅ |
| `data-model.md` §9 | **New entity** `PublishedPage` carrying `entry_id` + `has_article` | ✅ |
| `contracts/cli.md` | `run` gains `--no-backfill`/`--recheck-weeks`; `replay` gains `--entry`/`--latest`; exit code `5` added | ✅ |
| `contracts/data-source.md` | Historical re-fetch documented, with the normalized-comparison requirement | ✅ |
| `research.md` §9 | **New.** `RECHECK_WEEKS=3`, `/week-NN.html` addressing, repo-naming constraint | ✅ |
| `quickstart.md` | Scenarios 11–13 added (multi-week backfill, correction forward-only, discoverability) | ✅ |

**Two implementation traps recorded during the refresh**, both places where the new requirements
would otherwise be implemented as contradictions:

1. **Correction vs. backfill are different code paths.** Backfill publishes a *missing* week;
   correction never republishes an *existing* one. Collapsing "changed upstream" and "absent from
   archive" into one branch implements FR-038 and FR-048 as mutually exclusive.
2. **Correction detection must compare normalized data, not raw bytes.** Yahoo responses carry
   volatile per-request fields, so a byte comparison reports a correction every run and appends a
   junk archive entry each time.
