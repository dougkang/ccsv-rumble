---

description: "Task list for the newspaper-style visual alignment"
---

# Tasks: Newspaper-Style Visual Alignment

**Input**: Design documents from `specs/003-newspaper-style-alignment/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/style-contract.md](./contracts/style-contract.md),
[quickstart.md](./quickstart.md)

**Tests**: included. The spec requires them by name (FR-091, FR-092, FR-093, FR-096). They are
where this feature's risk sits: a reviewer can't see contrast or type size in a diff.

**Organization**: grouped by user story. Most work in all three stories lands in one file,
`src/ccsv_rumble/render/templates/style.css`, so the stories can each be **tested** on their own
but can't be **edited** in parallel. See "Parallel Opportunities".

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2, US3 from spec.md
- All paths are relative to the repository root

## Read this before starting

- **The golden test fails from T003 until T024.** `tests/golden/week-01.html` embeds the inlined
  stylesheet, so any CSS edit breaks `test_matches_the_golden_file`. That's expected. Until T024,
  run the suite with
  `--deselect tests/unit/test_render_deterministic.py::test_matches_the_golden_file`.
  **Every other test must stay green after every task.**
- **Every `font-size` must be written in `rem` and be at least `0.72rem`** (data-model.md T1–T2).
  Don't write `px`, `em`, `%`, keywords, or the `font:` shorthand anywhere in the sheet. T006 rejects
  all of them.
- **Only four colors may appear in the sheet**, and only as declarations inside `:root`:
  `#111`, `#fff`, `#555`, `#f5c518`. Everywhere else, use `var(--ink)`, `var(--paper)`,
  `var(--muted)`. Never use `var(--select)`: it's reserved and unused (FR-066).
- **Markup changes are limited to the seven `class` additions** in style-contract.md §1. Don't
  change any tag, `id`, `scope`, `aria-labelledby`, `<caption>`, or text (FR-086).
- **Don't touch** `src/ccsv_rumble/render/html.py`, `validate.py`, or anything under `rank/`,
  `report/`, `article/`, `fetch/`, `archive/`, `publish.py`. This is a presentation change.

---

## Phase 1: Setup

**Purpose**: record the baseline that later tasks compare against.

- [ ] T001 Run `uv run pytest` from the repository root and confirm every test passes. `addopts`
  already includes `-q`, so adding another `-q` hides the summary line. Run without it. Expect **129
  passed** as of 2026-10-21 on this branch, and record the actual count for T026.
- [ ] T002 Capture the pre-restyle render into `build/before/week-01.html` using the command under
  "Prerequisites" in `specs/003-newspaper-style-alignment/quickstart.md`. `build/` is already in
  `.gitignore`, so don't commit it. T023 diffs against this file. It must be captured **before** T003
  touches the stylesheet or any template.

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: switch the sheet to the four-token, light-only, single-font base that every story
builds on. After this phase no reference to a removed token remains, so later tasks only add rules.

**⚠️ T003 and T004 must land in the same commit.** Removing dark mode breaks the existing
`test_stylesheet_supports_both_colour_schemes`, and FR-092 replaces it rather than deleting it.

- [ ] T003 Rewrite the token base of `src/ccsv_rumble/render/templates/style.css`:
  - Replace the whole `:root` block **and** delete the entire `@media (prefers-color-scheme: dark)`
    block. Use one `:root` block containing exactly `color-scheme: light;`, `--ink: #111;`,
    `--paper: #fff;`, `--muted: #555;`, `--select: #f5c518;`, and
    `--font: "Helvetica Neue", Helvetica, Arial, sans-serif;`. Give each color one short trailing
    comment with its contrast on the paper token (`/* 18.9:1 on paper */`, `/* 7.5:1 on paper */`)
    and mark `--select` as `/* reserved: "yours"/"selected" only; unused on this surface */`,
    matching the sheet's existing comment style.
  - **No hex value may appear in any comment anywhere in the sheet.** T005 counts hex literals
    across the whole file, comments included. A comment like `/* 7.5:1 on #fff */` fails it.
    Refer to colors by token name in comments.
  - `body`: `background: var(--paper); color: var(--ink); font-family: var(--font);
    font-size: 1rem; line-height: 1.4;`. Replace the old `font:` shorthand. Leave `max-width`,
    `margin`, and `padding` alone for now (T011 owns them).
  - Remove every reference to the deleted tokens `--bg`, `--fg`, `--rule`, `--accent`, `--up`,
    `--down`. Specifically: delete `border-bottom` from the `th, td` rule; delete `border` and
    `border-radius` from `.badge`; delete `border-top` from `footer`. Set
    `.move-up, .move-down { color: var(--ink); }` and
    `.move-flat, .move-new { color: var(--muted); }`. Set `a { color: var(--ink);
    text-decoration: underline; }` and `a:focus-visible { outline: 2px solid var(--ink);
    outline-offset: 2px; }`. Set `.meta`, `caption`, and `thead th` to `color: var(--muted)`.
  - Update the header comment at the top of the file: name `docs/design-philosophy.md` as the
    governing style, keep the constitution Principle IV sentence, and update its contrast claim to
    "≥4.5:1 (light only)".
  - Done when `grep -c 'prefers-color-scheme\|--bg\|--fg\|--rule\|--accent\|--up\|--down'` on the
    file prints `0`.
- [ ] T004 In `tests/unit/test_accessibility.py`, replace
  `test_stylesheet_supports_both_colour_schemes` with `test_stylesheet_is_light_only` (FR-092). It
  asserts `"color-scheme: light"` is in `stylesheet()` and `"prefers-color-scheme"` is not. Write a
  docstring in the file's style giving the reason: the design philosophy says white background only,
  and a dark palette can't be expressed in its four colors.

**Checkpoint**: the suite (with the golden test deselected) is green. The page renders black on
white in Helvetica with no row rules. It looks unfinished, which is expected.

---

## Phase 3: User Story 1 — A league member reads the page on a phone (Priority: P1) 🎯 MVP

**Goal**: every piece of text is legible on a phone: contrast ≥4.5:1, nothing below 0.72rem,
no horizontal scroll of the page body at 320px, same rendering when the OS is in dark mode.

**Independent Test**: quickstart.md Scenarios 1, 5, and 8 (steps 2–3). All new tests in
`tests/unit/test_accessibility.py` pass; at 320px `document.documentElement.scrollWidth <= 320`.

### Tests for User Story 1

> These three tests already **pass** on the T003 sheet, because the old sizes were all ≥0.72rem and
> T003 fixed the palette. "Watch it fail first" therefore doesn't apply. T008 is the substitute:
> it proves each test fails when it should.

- [ ] T005 [US1] Add `test_palette_meets_contrast_floor` (FR-091) to
  `tests/unit/test_accessibility.py`:
  - Extract the `:root { ... }` block from `stylesheet()` with a regex. Parse every
    `--name: #hex;` declaration inside it.
  - Assert the set of hex values equals exactly `{"#111", "#fff", "#555", "#f5c518"}`, compared
    lowercase.
  - Assert each of those four values occurs **exactly once** in the whole sheet, so no literal is
    used outside `:root`.
  - Assert no other hex literal (`#[0-9a-fA-F]{3,6}\b`) occurs anywhere in the sheet.
  - Compute the WCAG 2.x contrast ratio in a module-level helper using only the standard library.
    Relative luminance: channel `c/255`, linearized as `c/12.92` if `≤0.04045`, else
    `((c+0.055)/1.055)**2.4`. `L = 0.2126R + 0.7152G + 0.0722B`. Ratio `(L1+0.05)/(L2+0.05)`.
    Expand 3-digit hex.
  - Assert `--ink` on `--paper`, `--muted` on `--paper`, and `--ink` on `--select` are each
    ≥4.5.
  - Expected values for reference: 18.88, 7.46, 11.58.
- [ ] T006 [US1] Add `test_every_font_size_meets_the_floor` (FR-096) to
  `tests/unit/test_accessibility.py`:
  - Find every `font-size:\s*([^;}]+)` match in `stylesheet()`. Assert at least one match.
  - Assert each value matches `^\d*\.?\d+rem$`, then assert `float(value[:-3]) >= 0.72`.
  - Separately assert the sheet contains no `font:` shorthand, using the regex
    `(?<![-\w])font\s*:`. The shorthand can hide a size from the check.
  - The docstring must say the check covers **every** declaration rather than named selectors on
    purpose, and why (research.md §2).
- [ ] T007 [US1] Add `test_single_font_stack` (FR-068) to `tests/unit/test_accessibility.py`. Every
  `font-family:\s*([^;}]+)` value, stripped, must be either `var(--font)` or the exact stack
  `"Helvetica Neue", Helvetica, Arial, sans-serif`. Assert `--font:` is declared exactly once.
- [ ] T008 [US1] Negative-check T005 and T006 (quickstart Scenario 1, "Negative check"). Temporarily
  set `--muted: #888;` in `style.css`, then run
  `uv run pytest tests/unit/test_accessibility.py`. T005 must fail, and its message should show the
  3.5:1 ratio. Revert. Then temporarily add `font-size: 0.65rem;` inside `caption { }`, run again,
  and T006 must fail. Revert. Run `git diff --stat src/` and confirm `style.css` shows only the
  intended T003 changes. Commit nothing from this task.

### Implementation for User Story 1

- [ ] T009 [US1] Set the body and data type scale in `src/ccsv_rumble/render/templates/style.css`
  (data-model.md §2):
  - `p, li { font-size: 1rem; }`
  - `tbody th, tbody td { font-size: 0.9rem; }`
  - `.meta { font-size: 0.9rem; }`
  - `caption { font-size: 0.9rem; color: var(--muted); }`
  - Every size in `rem`. Don't set heading, column-header, or badge sizes here (US2 owns those).
- [ ] T010 [US1] Make the caveat note roman in `src/ccsv_rumble/render/templates/style.css`:
  `.note { color: var(--muted); }`. Delete `font-style: italic`, so no `italic` remains anywhere in
  the file (FR-071).
- [ ] T011 [US1] Rework the page layout in `src/ccsv_rumble/render/templates/style.css`
  (data-model.md §5):
  - `body`: remove `max-width: 48rem` and `margin: 0 auto`. Set `margin: 0` and
    `padding: 1.5rem 2rem 3rem`.
  - Add `p, li { max-width: 40rem; }`. This is left-aligned, so no `margin: auto` (FR-081).
  - Keep the `table` rule's `width: 100%; display: block; overflow-x: auto; white-space: nowrap;`
    and its preceding comment exactly as they are. `test_wide_content_scrolls_inside_its_own_container`
    matches `overflow-x: auto` literally (FR-082).
  - In `@media (max-width: 420px)`, set `body { padding: 1rem 0.75rem 2rem; }`. Leave the
    `th, td` padding override for T018 to replace.
- [ ] T012 [US1] Validate US1. Run `uv run pytest --deselect
  tests/unit/test_render_deterministic.py::test_matches_the_golden_file` (all green), then
  quickstart.md Scenario 5 (320 / 768 / 1920px) and Scenario 8 steps 2–3 (emulated dark scheme
  shows no change; JS disabled shows no change). Render to `build/after/week-01.html` with the
  quickstart command.

**Checkpoint**: the page is legible and safe on a phone. It doesn't yet look like a newspaper:
headings and table header are unstyled, and there are no rules.

---

## Phase 4: User Story 2 — The page reads as a newspaper page, not a dashboard (Priority: P1)

**Goal**: the five heading levels, exactly four rules on a week page (three on the index), no pills,
no bullets, no rounded or shadowed anything.

**Independent Test**: quickstart.md Scenarios 2, 4, 6, 7, and 8 step 1. The rule count is exactly
4 on the week page and 3 on the index, and all five heading levels can be told apart in grayscale.

### Tests for User Story 2

- [ ] T013 [US2] Add `test_no_banned_primitives` (FR-093) to `tests/unit/test_accessibility.py`.
  Lowercase `stylesheet()` and assert none of these substrings occur: `border-radius`,
  `box-shadow`, `gradient`, `italic`, `@font-face`, `@import`, `url(`. Report every offender in one
  failure message, not just the first. This passes after T010. T008's revert must not have
  reintroduced anything.

### Implementation for User Story 2

- [ ] T014 [P] [US2] Add classes in `src/ccsv_rumble/render/templates/page.html.j2`. **Exactly
  four attribute additions, nothing else on those lines changes:**
  - `<h2 id="standings-heading">` → `<h2 id="standings-heading" class="section-divider">`
  - `<h2 id="writeup-heading">` → `<h2 id="writeup-heading" class="headline">`
  - `<h2 id="events-heading">` → `<h2 id="events-heading" class="section-divider">`
  - the events `<ul>` → `<ul class="plain-list">`
- [ ] T015 [P] [US2] Add classes in `src/ccsv_rumble/render/templates/index.html.j2`. **Exactly
  three attribute additions:**
  - `<h2 id="latest-heading">` → add `class="section-divider"`
  - `<h2 id="archive-heading">` → add `class="section-divider"`
  - the week-list `<ul>` → add `class="plain-list"`
- [ ] T016 [US2] Style the masthead in `src/ccsv_rumble/render/templates/style.css` (heading level
  1, rule #1):
  - `header { border-bottom: 1px solid var(--ink); padding-bottom: 0.9rem; }`
  - `h1 { font-size: 2.8rem; font-weight: 900; letter-spacing: -0.04em; line-height: 1;
    margin: 0 0 0.25rem; }`
  - This is the **only** negative `letter-spacing` in the sheet (FR-072).
  - Replace the existing `h1` rule rather than adding a second one.
- [ ] T017 [US2] Style the heading roles in `src/ccsv_rumble/render/templates/style.css` (levels
  2–4, rules #2–#3). Replace the existing bare `h2` rule:
  - `h2.section-divider { font-size: 0.9rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.2em; text-align: center; border-bottom: 1px solid var(--ink);
    padding-bottom: 0.5rem; margin: 2rem 0 1rem; }`
  - `h2.headline { font-size: 1.3rem; font-weight: 800; text-align: left; margin: 1.5rem 0 0.75rem; }`
    with no border, background, or `text-transform` (FR-070 level 3).
  - `strong { font-weight: 700; }` (level 4).
  - Use no sibling combinators (`+`, `~`) anywhere. Spacing must not depend on whether the
    optional article section is present (style-contract.md §2.8).
- [ ] T018 [US2] Style the table in `src/ccsv_rumble/render/templates/style.css` (level 5,
  rule #4, FR-073/074/078/079):
  - `th, td { padding: 0.3rem 0.5rem; text-align: left; }` with **no border**.
  - `thead th { font-size: 0.72rem; font-weight: 900; text-transform: uppercase;
    letter-spacing: 0.05em; color: var(--muted); border-bottom: 1px solid var(--ink); }`
  - Right-align the numeric columns (Rank is first, Move is last, fixed by 001's table contract):
    `thead th:first-child, thead th:last-child, tbody th, td.move { text-align: right; }`
  - `tbody th, .move { font-variant-numeric: tabular-nums; }`. Keep `tbody th { width: 3rem; }`.
  - In the `@media (max-width: 420px)` block, replace the `th, td` padding with
    `padding: 0.28rem 0.25rem;`.
  - Add no `:hover` rule on `tr`, `td`, or `th` (FR-083).
- [ ] T019 [US2] Restyle the caveat label in `src/ccsv_rumble/render/templates/style.css`
  (FR-077): `.badge { display: inline; font-size: 0.72rem; font-weight: 900;
  text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-left: 0.5rem; }`.
  It has no `border`, `background`, `padding`, or `border-radius`.
- [ ] T020 [US2] Style lists and footer in `src/ccsv_rumble/render/templates/style.css`
  (FR-073, FR-085):
  - Replace the bare `ul` rule with `.plain-list { list-style: none; padding-left: 0; }`.
  - Keep `li { margin: 0.3rem 0; }`.
  - `footer { margin-top: 2.5rem; padding-top: 1rem; }` with **no border**.
- [ ] T021 [US2] Validate US2. Run the suite with the golden test deselected (all green). Re-render
  `build/after/week-01.html`. Then run quickstart.md:
  - Scenario 2: exactly 4 hex values.
  - Scenario 4: exactly **4 distinct rules** on the week page (`HEADER`, two
    `H2.section-divider`, `THEAD`) and 3 on the index. Render the index with
    `render_index(season="2026-27", weeks=[1, 2, 3])`. The query collapses the five bordered
    `thead th` cells into one `THEAD` entry, so they count as one rule. That's correct: don't move
    the border off the cells.
  - Scenario 6: no article.
  - Scenario 7: projection page.
  - Scenario 8 step 1: grayscale.

  If Scenario 4 shows a count of distinct rules other than 4 or 3, stop and fix it before moving
  on.

**Checkpoint**: both P1 stories are complete. The page is legible and on-theme.

---

## Phase 5: User Story 3 — A maintainer merges without breaking the guarantees (Priority: P2)

**Goal**: show that determinism, accessibility, and never-publish-broken still hold, with a golden
diff whose every line is explained.

**Independent Test**: quickstart.md Scenarios 3, 9, and 10. Structure is identical once classes are
stripped, the full suite including the golden test is green, and a dry run validates.

- [ ] T022 [US3] Confirm `src/ccsv_rumble/render/html.py` and `validate.py` are unchanged:
  `git diff --quiet origin/main -- src/ccsv_rumble/render/html.py src/ccsv_rumble/render/validate.py`
  exits 0. If not, revert whatever changed. This feature must not touch them (plan.md, note on
  `html.py`).
- [ ] T023 [US3] Run quickstart.md Scenario 3 against `build/before/week-01.html` (from T002) and
  a fresh `build/after/week-01.html`. Expected output is `structure identical` (SC-025). Any
  diff means T014 or T015 changed more than a `class` attribute. Fix the template, don't
  explain it away.
- [ ] T024 [US3] Regenerate the golden file (quickstart.md Scenario 10). Run
  `rm tests/golden/week-01.html`, then `uv run pytest`, which recreates it. Then read
  `git diff -- tests/golden/week-01.html` line by line. The diff may contain **only** the inlined
  `<style>` content and the four `class` additions from T014. The index isn't in the golden file.
  Any changed team name, number, sentence, or tag is a bug from an earlier task.
- [ ] T025 [US3] Run `uv run ruff check src/ tests/`. It must be clean.
- [ ] T026 [US3] Run the full suite with **nothing deselected**: `uv run pytest`. Expected:
  all pass, with the T001 count **plus 4**. T004 replaces a test (net 0); T005, T006, T007, and
  T013 each add one.
- [ ] T027 [US3] Run the pre-merge dry run (quickstart.md Scenario 9):
  - `git pull origin main`, then
    `uv run ccsv-rumble dry-run --from-archive --week <latest archived week>`. It must exit 0 with
    validation passing.
  - If `archive/` doesn't exist yet (true as of 2026-10-21), skip the command and note the
    fixture fallback for T028.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T028 Draft the PR description in `build/pr-body.md` (gitignored scratch, to paste into the
  PR). It must contain:
  - a one-paragraph summary of the T024 golden diff (constitution pre-merge gate 3);
  - the T026 test count;
  - Scenario 9's result, or the statement that gate 2 ran against fixtures because no archive
    existed yet and must be rerun on the first archived week before the restyle's first live
    publish;
  - a "Recorded deviations from the design philosophy" section listing the three in plan.md;
  - a note that if `002-draft-ranking-week-0` merges first, the golden file must be
    **regenerated** (T024), not hand-merged;
  - a note that the first scheduled run after merge will produce a publish commit, because every
    page's bytes change. That's expected and not a regression.

  It contains **no** "Constitution exception" heading, because there is none.
- [ ] T029 [P] Add two rows to the documentation table in `README.md`, after the
  `specs/001-power-ranking-article/` row and in the same format: one linking
  `docs/design-philosophy.md` ("Visual style: newspaper meets nutrition label, with project
  amendments") and one linking `specs/003-newspaper-style-alignment/` ("Spec, plan, research, data
  model, contracts, tasks").
- [ ] T030 [P] Check that `docs/design-philosophy.md`'s "Project amendments" section matches what
  shipped:
  - muted `#555`;
  - size floors (1rem prose, 0.9rem data, 0.72rem labels);
  - prose measure. Amendment 4 names no value, so add "(`max-width: 40rem`)".

  Edit only to correct mismatches.
- [ ] T031 Mark every completed task `- [x]` in
  `specs/003-newspaper-style-alignment/tasks.md` and commit.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001–T002)**: none. **T002 must run before any edit to `style.css` or a template.**
- **Foundational (T003–T004)**: after Setup. Blocks every story. Commit T003 and T004 together.
- **US1 (T005–T012)**: after Foundational.
- **US2 (T013–T021)**: after Foundational. In logic it's independent of US1. In practice T016–T020
  edit the same file as T009–T011, so run US2 **after** US1 unless one person does both in one
  editing session.
- **US3 (T022–T027)**: after US1 **and** US2. It validates the finished page, and T024 can't
  regenerate a golden file that's still changing.
- **Polish (T028–T031)**: after US3. T028 needs the T024, T026, and T027 results.

### Within each story

- Tests before implementation (T005–T007 before T009; T013 before T016). These tests pass on
  arrival, so T008 provides the "proves it can fail" check instead.
- T012 and T021 are the story checkpoints. Don't start the next phase while either is red.

### Story dependency graph

```text
T001 → T002 → [T003 + T004] ─┬─→ US1 (T005…T012) ─┐
                             └─→ US2 (T013…T021) ─┴─→ US3 (T022…T027) → Polish (T028…T031)
                                  (same file as US1: run sequentially in practice)
```

### Parallel opportunities

Only four tasks are truly parallel, because one stylesheet carries nearly all the work:

- **T014 ∥ T015**: two different templates with no shared dependency.
- **T029 ∥ T030**: README and the vendored doc.
- T005, T006, T007, and T013 all edit `tests/unit/test_accessibility.py`, so they're **not**
  marked [P]. Writing them in one sitting is the fast path.

## Parallel Example: User Story 2

```bash
# Once T013 is written, both template edits can go together:
Task: "T014 Add 4 class attributes in src/ccsv_rumble/render/templates/page.html.j2"
Task: "T015 Add 3 class attributes in src/ccsv_rumble/render/templates/index.html.j2"
# Then the style.css tasks T016 → T020 run in sequence (same file).
```

---

## Implementation Strategy

### MVP: US1, but don't ship it alone

US1 is the MVP in the speckit sense: on its own it delivers the most important outcome, a page that
is legible and safe on a phone, and it can be tested independently. But US1 by itself publishes a
page that has lost its old styling without gaining the new one: no rules, plain headings. That
looks broken to readers rather than finished. **Recommendation: merge US1 + US2 + US3 as one PR.**
The whole feature is ~30 small tasks in four files, and splitting the merge only adds an awkward
intermediate page to the live site.

### Incremental validation, single delivery

1. Setup + Foundational → suite green (golden deselected)
2. US1 → T012 checkpoint: legible and light-only at 320px
3. US2 → T021 checkpoint: exactly 4 / 3 rules, five distinct heading levels
4. US3 → golden regenerated and explained, full suite green, dry run (or fixture fallback recorded)
5. Polish → PR body, README, amendments in sync → open the PR

---

## Notes

- If exactly one thing from this list survives time pressure, make it **T005 + T006 + T008**. They
  machine-check the two properties a reviewer can't see in a diff (plan.md, "The risk this plan
  carries").
- Commit after each phase at least. T003 and T004 must share a commit.
- No task bumps `ALGORITHM_VERSION`. A restyle must not imply the numbers moved (plan.md, gate I).
