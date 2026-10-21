# Implementation Plan: Newspaper-Style Visual Alignment

**Branch**: `worktree-002-newspaper-style` (feature `003-newspaper-style-alignment`; the branch
name predates the renumber) | **Date**: 2026-10-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-newspaper-style-alignment/spec.md`

## Summary

Restyle the two published pages to the vendored design philosophy
([docs/design-philosophy.md](../../docs/design-philosophy.md)): Helvetica Neue only, four color
tokens, four horizontal rules, no rounded corners, no dark mode, separation by padding rather than
lines.

The technical approach is deliberately narrow. **This is a stylesheet rewrite plus `class`
attributes on existing tags.** No Python logic changes, no new data on the page, no tag or ARIA
changes. That narrowness is what keeps `validate_page`, the accessibility suite, the failure-path
test, and the offline-replay test passing untouched — and it is why the risk concentrates in two
places only: contrast and type size. Both get a dedicated test (FR-091, FR-096).

One structural decision drives the rest: **the token set and the rule set are closed.** Adding a
fifth color or a fourth rule is a spec change, not an implementation detail, which is what makes
SC-021 and SC-024 mechanically checkable rather than matters of taste.

## Technical Context

**Language/Version**: Python 3.14 (pinned by `.python-version`), managed with `uv`

**Primary Dependencies**: Jinja2 (templating, already present). **No new runtime dependency** — the
constitution requires justifying one against a named requirement, and this feature has none.

**Storage**: N/A. This feature touches no archive, no snapshot, and no model.

**Testing**: pytest. Three new/replaced assertions in `tests/unit/test_accessibility.py`
(FR-091, FR-092, FR-093, FR-096) plus a regenerated `tests/golden/week-01.html`.

**Target Platform**: static HTML on GitHub Pages, read primarily on phones; must be readable from
320px wide upward.

**Project Type**: batch generator producing static HTML. Presentation-layer change only.

**Performance Goals**: N/A for rendering speed. The relevant budget is page weight
(`config.PAGE_WEIGHT_BUDGET_BYTES`), which this change only reduces: the stylesheet loses a
dark-mode block and seven color tokens and gains no assets.

**Constraints**: every text pair ≥4.5:1 (Principle IV); no text below 0.72rem and no prose below
1rem (FR-078a); no third-party fetch at page load; zero JavaScript; byte-identical rendering for a
fixed snapshot.

**Scale/Scope**: two templates (`page.html.j2`, `index.html.j2`), one stylesheet (81 lines today),
one test module, one golden file. 18 teams, ~20 weeks per season.

**Unknowns**: none. Phase 0 found no NEEDS CLARIFICATION — the spec's clarification round already
resolved every open question, and the stack is fully known. See [research.md](./research.md), which
records implementation decisions rather than research findings.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates derived from `.specify/memory/constitution.md` v2.0.0. Most of Principle I–III and V is
untouched by a presentation change; those rows record *why* they stay untouched, which is the thing
a reviewer actually needs to confirm.

| Gate | Design response | Status |
|---|---|---|
| **I.** Ranking is a pure function; own module, no I/O | Not touched. No file under `rank/` is modified. | ✅ n/a |
| **I.** Algorithm version bump on algorithm change | No algorithm change, so no bump. A restyle MUST NOT bump the algorithm version — doing so would falsely imply the numbers moved. | ✅ |
| **I.** Rendering deterministic, byte-identical | CSS and `class` attributes are static text in templates. No clock, no randomness, no set iteration introduced. Enforced by the unchanged golden-file and cross-process tests. | ✅ |
| **I.** Nondeterministic stage confined to acquisition | Not touched. No model call anywhere in this feature. | ✅ n/a |
| **I.** Regeneration MUST NOT invoke a nondeterministic stage | Not touched. Replay path unchanged; its test keeps its assertions (FR-095). | ✅ n/a |
| **II.** Publish gated on validation | `validate_page` is unchanged and MUST keep passing (FR-089). The restyle changes nothing it inspects: one `<h1>`, ≥1 table, scoped headers, `noindex`, no external refs, weight budget. | ✅ |
| **II.** All-or-nothing publish; no commit when output identical | Untouched. Note the one real operational consequence: the first run after merge changes every page's bytes, so it WILL produce a publish commit. That is correct, not a regression. | ✅ |
| **II.** Failure exits non-zero and notifies | Untouched. | ✅ n/a |
| **II.** Safe to re-run | Untouched; still idempotent. | ✅ n/a |
| **II.** "Complete" defined per feature; optional content cannot block publication | Unchanged. The restyle must additionally not *look* broken when the optional article is absent — covered as an edge case and by quickstart Scenario 6. | ✅ |
| **III.** Raw inputs archived, append-only, offline replay tested | Untouched. Archives hold data, not presentation; past snapshots replay into the *new* style, which is expected and is why pages record `entry_id` rather than a stylesheet version. | ✅ n/a |
| **IV.** Static output, no serve-time runtime | Still a build-time Jinja2 render to plain HTML with an inlined `<style>`. | ✅ |
| **IV.** Readable with JS disabled | Zero JavaScript before and after (FR-090). | ✅ |
| **IV.** Semantic markup: heading order, real tables, `<th scope>`, landmarks | **FR-086 forbids changing any tag, `scope`, `aria-labelledby`, `<caption>`, or landmark.** Changes are confined to the stylesheet and `class` attributes. SC-025 makes this diffable to zero. | ✅ |
| **IV.** Text ≥4.5:1 contrast | The load-bearing gate. The philosophy's `#888` (3.54:1) and `#aaa` (2.32:1) **fail** it, so muted text binds to `#555` (7.46:1) and `#ccc`/`#eee` leave the palette entirely. Asserted by a new test computing ratios from the declared tokens (FR-091). | ✅ with recorded deviation |
| **IV.** Readable from 320px, no body horizontal scroll | `overflow-x: auto` on the table container is retained (FR-082, FR-094) and matters more as the table densifies. Page padding reduces on narrow viewports. | ✅ |
| **IV.** Weight under budget; no third-party script/font/stylesheet at load | Helvetica Neue is a **local font stack**, not a web font — no `@font-face`, no `@import`, no URL (FR-068). The sheet shrinks. | ✅ |
| **IV.** Templates data-driven | No league fact is introduced into a template. Only `class` attributes. | ✅ |
| **V.** Secrets, scoped token, no PII, no analytics/tracking | Untouched. A CSS change adds no network call, no embed, and no new field to the page. | ✅ n/a |
| **Workflow** Cosmetic CSS changes need no new unit tests but MUST have golden files reviewed | Golden file regenerated and its diff explained in the PR (FR-087). This feature goes *beyond* the requirement by adding contrast and size tests, because that is where the risk is. | ✅ exceeds |
| **Workflow** Pre-merge gate 2: dry run against an archived snapshot passes validation | quickstart Scenario 9. | ✅ |

### Recorded deviations from the design philosophy

The constitution supersedes the philosophy where they conflict (governance: "Where it conflicts
with a habit, a tutorial, or an agent's default behavior, this document wins"). Three deviations
are recorded in `docs/design-philosophy.md` under "Project amendments" and derived in the spec's
clarification round:

1. **Muted gray is `#555`, not `#888`/`#aaa`** — Principle IV's 4.5:1 floor.
2. **No dark mode** — follows the philosophy literally; also unexpressible in three colors.
3. **Size floors above the philosophy's own sizes** — Principle IV's stated rationale is phones and
   varied ages; a five-column table has no density pressure to relieve.

**No constitution violations. Complexity Tracking section omitted.**

The gate most likely to erode later is the palette one, and it is worth saying why the mitigation is
structural rather than diligence-based: **the contrast test enumerates the declared tokens and
asserts every text pair, so adding a fifth color to the sheet fails the test rather than requiring
someone to notice.** A reviewer cannot forget to check contrast because the check is not theirs to
perform.

## Project Structure

### Documentation (this feature)

```text
specs/003-newspaper-style-alignment/
├── spec.md              # Feature specification (FR-060..FR-096, SC-020..SC-029)
├── plan.md              # This file
├── research.md          # Phase 0: implementation decisions (no unknowns to research)
├── data-model.md        # Phase 1: the closed token, class, and rule model
├── quickstart.md        # Phase 1: 10 validation scenarios
└── contracts/
    └── style-contract.md  # Phase 1: the template↔stylesheet class contract
```

### Source Code (repository root)

```text
src/ccsv_rumble/
└── render/
    ├── html.py                      # UNCHANGED (see note below)
    ├── validate.py                  # UNCHANGED
    └── templates/
        ├── style.css                # REWRITTEN — the bulk of this feature
        ├── page.html.j2             # MODIFIED — class attributes only
        ├── index.html.j2            # MODIFIED — class attributes only
        └── robots.txt               # UNCHANGED

docs/
└── design-philosophy.md             # ADDED (FR-060/FR-061, landed with the spec)

tests/
├── unit/
│   ├── test_accessibility.py        # MODIFIED — FR-091/092/093/096
│   └── test_render_deterministic.py # UNCHANGED assertions
├── integration/                     # UNCHANGED
└── golden/
    └── week-01.html                 # REGENERATED
```

**Note on `html.py`**: it is listed unchanged on purpose. `_move_label()` already emits the text
`up 3` / `down 2` / `even` / `new`, and `_move_class()` already emits `move-up` / `move-down` /
`move-flat` / `move-new`. Dropping the green/red colors is done by *restyling* those classes, not
by touching Python. `move-up`/`move-down` become `#111`; `move-flat`/`move-new` become `#555`. The
class names stay even though two pairs now share a color, because the names describe the data, not
the paint.

## Implementation sequence

Ordered so that each step leaves the suite green except where a failure is the point.

1. **Write the new `style.css`** against the token and rule model in
   [data-model.md](./data-model.md). The sheet is the feature; everything else follows from it.
2. **Add the three new tests** (contrast, light-only, banned primitives, size floors). Run them
   against the new sheet. These must pass before any template edit, because they are what proves
   the sheet is correct independent of markup.
3. **Replace `test_stylesheet_supports_both_colour_schemes`** with the light-only assertion
   (FR-092). Deleting it without a replacement would silently drop a Principle IV check.
4. **Add `class` attributes** to the three `<h2>`s and the lists per
   [contracts/style-contract.md](./contracts/style-contract.md). The accessibility suite must stay
   green throughout — if a tag or `scope` count moves, step 4 has overreached.
5. **Regenerate the golden file** and read the diff line by line. Every line must be a `class`
   attribute or inlined CSS; a change to any data value means something in steps 1–4 was wrong.
6. **Run the full suite plus a dry run from the archive** (quickstart Scenarios 9 and 10).
7. **Visual check at 320px, 768px, and 1920px**, plus a grayscale pass for SC-029.

Step 2 before step 4 is the part worth preserving under time pressure: the sheet is testable on its
own, and proving it in isolation is what keeps a contrast or size regression from hiding behind a
markup diff.

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1. All gates still pass; no new violations; Complexity Tracking remains
omitted.

Phase 1 surfaced four decisions that strengthened compliance beyond the initial check, all recorded
in [research.md](./research.md):

1. **The size-floor test asserts that *every* `font-size` in the sheet is ≥0.72rem**, rather than
   checking named selectors. A per-selector assertion silently misses the selector someone adds
   next week; a blanket assertion cannot. This requires every `font-size` to be declared in `rem`,
   which is now a contract term rather than a convention (research.md §2).
2. **The palette is four tokens, not six.** Removing the footer rule left `#ccc` and `#eee` with no
   use, so they leave the sheet entirely. A smaller closed set is a stronger invariant: SC-021
   becomes "zero color literals outside four tokens."
3. **The prose measure cap needs no new class.** All prose on both pages is in `<p>` and `<li>`, so
   the cap applies to those elements directly — one less `class` attribute, one less way for the
   markup and the sheet to drift (research.md §3).
4. **Rule count is now exact, not a maximum.** Four on a week page, three on the index. An exact
   count catches a *missing* rule as well as an extra one; "at most four" catches only extras.

### Interaction with `002-draft-ranking-week-0`

Checked, because both features are in flight and both touch the published page. `002-draft` states
it "reuses `001`'s archive, report, rendering, validation, publish, notification" and adds only a
ranking source plus two acquisition stages. Its page-facing requirement — that the page state the
ranking reflects draft projections — is served by the **existing** `is_projection` badge and note in
`page.html.j2`, both of which this feature already restyles (FR-077 covers the `draft-based
projection` label; FR-071 covers the note). **No new page element, label, or string is introduced by
that feature**, so the two can merge in either order.

The one ordering consequence: whichever merges second regenerates the golden file on top of the
other's diff. That is a mechanical conflict in `tests/golden/week-01.html`, resolved by
regenerating rather than by hand-merging — worth noting in the PR so a reviewer does not try to
read a merged golden diff.

### The risk this plan carries

The honest one is that **a reviewer cannot see contrast or type size in a diff**, and this change
touches every visual property at once. A `font-size: 0.72rem` and a `font-size: 0.62rem` look
equally plausible in a pull request. That is the entire reason FR-091 and FR-096 exist, and why
step 2 runs before step 4: by the time anyone reads the markup diff, the sheet's numbers have
already been machine-checked. If exactly one thing from this plan survives review pressure, it
should be those two tests — not any individual styling decision.
