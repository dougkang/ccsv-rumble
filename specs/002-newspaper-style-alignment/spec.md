# Feature Specification: Newspaper-Style Visual Alignment

**Feature Branch**: `worktree-002-newspaper-style`

**Created**: 2026-10-20

**Status**: Draft — conflicts resolved, ready for planning

**Input**: User description: "write a spec that aligns the style of our pages to `~/dev/design-philosophy`"

**Source of authority**: `~/dev/design-philosophy/design-philosophy.md` (the written philosophy) and
`~/dev/design-philosophy/index.html` (its reference implementation). Both live outside this
repository today, which makes them unreviewable in a PR; FR-060 fixes that.

**Scope note**: this spec describes the *working-tree* state of
`src/ccsv_rumble/render/templates/style.css`, `page.html.j2`, and `index.html.j2` as read on
2026-10-20, which includes uncommitted edits not present in `origin/main`.

---

## Summary

The published pages currently use a warm off-white serif-adjacent system-font look with a dark
mode, a maroon accent, green/red movement colors, pill-shaped badges, and full row rules. The
design philosophy calls for something materially different: **newspaper meets nutrition label** —
Helvetica Neue only, three colors, near-zero lines, no rounded corners, and density achieved
through padding rather than rules.

This feature changes **presentation only**. No ranking number, no article sentence, and no HTML
tag or ARIA attribute changes. It is a stylesheet rewrite plus the addition of CSS classes to
existing elements.

---

## Clarifications

### Session 2026-10-20

Each of these resolves a genuine conflict between the design philosophy and this project's
constitution or subject matter. They were decided by derivation from the two documents, not by
preference, and each is a one-line decision a reviewer can flip.

- Q: The philosophy says "White `#fff` — background. Nothing else," but the current stylesheet
  ships a `prefers-color-scheme: dark` palette and a test asserts it. Keep dark mode? → **A: Drop
  it.** Light-only. The constitution (Principle IV) requires 4.5:1 contrast and 320px readability,
  never a dark scheme; light-only satisfies both. A dark palette cannot be expressed in three
  colors without inventing a fourth and fifth. `test_stylesheet_supports_both_colour_schemes` is a
  test assertion, not a principle — it is **replaced**, not deleted.
- Q: The philosophy's grays `#888` and `#aaa` are specified for muted text (masthead meta, nav,
  column headers). Adopt them? → **A: No — adopt the gray *semantics*, not those two values.**
  Measured against `#fff`: `#555` = 7.46:1 (passes), `#666` = 5.74:1 (passes), `#777` = 4.48:1
  (fails), `#888` = 3.54:1 (fails), `#aaa` = 2.32:1 (fails). Principle IV's 4.5:1 floor is
  mandatory and governance says the constitution supersedes other conventions. Muted **text** binds
  to `#555` only. `#ccc`/`#eee` are never text, and since the footer-rule decision below leaves
  every rule on the page at `#111`, they end up with no use on this surface at all (FR-062).
- Q: Does yellow `#f5c518` have any legitimate use on these pages? → **A: No. The surface ships
  with zero yellow.** The philosophy restricts yellow to "yours" or "selected" and says "never used
  decoratively." A static, read-only, single-viewer-agnostic page has no viewer identity and no
  selection state, so highlighting (say) rank 1 would be decorative by the philosophy's own
  definition. Yellow stays in the token list, documented and unused, so a future interactive
  surface inherits it correctly.
- Q: Should yellow or the existing maroon become the link color? → **A: Neither. Links are `#111`
  plus an underline.** Yellow on white is 1.63:1 — illegible as text. Yellow is a *fill behind
  black text* (`#111` on `#f5c518` = 11.58:1) or nothing. The philosophy already states that
  active/linked state is distinguished "by weight or an underline only."
- Q: Red `#c00`? → **A: Unused.** The philosophy admits red only for destructive actions. These
  pages have no actions at all.
- Q: Keep the green/red movement colors (`--up`/`--down`)? → **A: Drop both.** "Never use color to
  convey hierarchy — use weight." `_move_label()` in `render/html.py` already emits the literal text
  `up 3` / `down 2` / `even` / `new`, so removing the colors loses zero information and requires no
  template change. Directional moves render in `#111`; `even` and `new` render in `#555`, matching
  the philosophy's rule that absence reads as muted.
- Q: The philosophy says content "runs close to the viewport edges (2rem padding)" with "no
  wrappers with `max-width`." Remove the 48rem cap? → **A: Partially — the table and header run
  full width; the prose column keeps a measure cap.** The philosophy's own layout section carves out
  "unless the viewport is very wide," and its opening line is "every visual decision serves
  legibility first." Uncapped prose at 1920px is 200+ characters per line. The reference
  implementation is a stats app with no prose blocks; this page is an article. The cap is
  left-aligned, not centered — the philosophy forbids "centered containers with large side margins."
- Q: The philosophy's typography section specifies a 3px rule below section dividers; its
  lines-and-borders section permits only 1px rules and the reference implementation uses
  `border-bottom: 1px solid var(--black)`. Which wins? → **A: 1px.** The reference implementation
  and the lines section agree against a single sentence in the typography section.
- Q: The `.note` element (the projection / provisional caveat) is currently italic. The philosophy
  allows italic only for quoted opinion and loading/placeholder states. → **A: Drop the italic.**
  The caveat is editorial fact, not a quotation and not a placeholder. It renders as `#555` roman.
- Q: The philosophy specifies hover and selected states for rows. → **A: Not applicable; omit
  both.** Table rows here are not clickable and nothing is selectable. Adding `#eee` row hover would
  signal an affordance that does not exist. Hover applies to links only.
- Q: Adopt the philosophy's 0.78rem data text and 0.65rem (~10.4px) column headers? → **A: No —
  adopt the density *principle* with a size floor.** Those numbers exist to fit seven stat columns
  on a desktop stats table. This table has five columns, so the density allowance buys nothing here,
  and the constitution's rationale for Principle IV is explicit that the page "is read on phones by
  a congregation of varied ages and devices." Prose stays at 1rem, table data is at least 0.9rem,
  and column headers are at least 0.72rem. Note that a contrast test cannot catch this: `#555` at
  0.65rem passes 4.5:1 and is still too small, which is why FR-096 asserts sizes directly.
- Q: Keep the `#ccc` rule above the footer? → **A: No — zero rules in the footer.** The philosophy
  permits a `#ccc` rule only "below a section's last row, only when another section follows
  immediately with no gap," and the footer has a gap. Its own test applies: more vertical padding
  achieves the same separation. This also keeps the page's total rule count at exactly four
  (masthead, two section dividers, one table header).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A league member reads the page on a phone (Priority: P1)

A member opens the week's page on a phone in a church hallway. The masthead tells them what they
are looking at, the rankings table fits without pinching, and every number and label is legible at
arm's length in bright light.

**Why this priority**: this is the primary reading context for the entire product, and it is where
the philosophy's density rules carry the most risk — smaller type and tighter padding make a page
better on a laptop and can make it worse on a phone.

**Independent Test**: render a week page, load it at a 320px viewport, and confirm no horizontal
scrolling of the page body, the full ranking visible by vertical scroll alone, and every
foreground/background text pair at or above 4.5:1.

**Acceptance Scenarios**:

1. **Given** the rendered page at a 320px-wide viewport, **When** it is displayed, **Then** the
   page body does not scroll horizontally and the rankings table scrolls within its own container
   if it must.
2. **Given** the rendered page, **When** every text color is measured against the background it
   sits on, **Then** each pair is at or above 4.5:1.
3. **Given** the rendered page with the operating system set to dark mode, **When** it is displayed,
   **Then** it renders in the same white background and black ink as in light mode, with no inverted
   or washed-out region.
4. **Given** the rendered page, **When** it loads with no network access beyond the HTML itself,
   **Then** all text displays in Helvetica Neue, Helvetica, or Arial with no font fetch attempted
   and no layout shift.

---

### User Story 2 - The page reads as a newspaper page, not a dashboard (Priority: P1)

A reader's eye lands on the masthead, drops to the section it wants, and scans the table without
tripping over boxes, rules, pills, or color-coded cells. The structure is exposed by type weight
and whitespace.

**Why this priority**: this is the actual request. It is co-P1 with legibility because a page that
is legible but off-theme has not delivered the feature.

**Independent Test**: inspect the generated stylesheet and confirm the absence of every banned
primitive and the presence of exactly the permitted palette and line set.

**Acceptance Scenarios**:

1. **Given** the generated stylesheet, **When** it is inspected, **Then** it contains no
   `border-radius`, no `box-shadow`, no `gradient`, and no `font-style: italic`.
2. **Given** the generated stylesheet, **When** its color values are enumerated, **Then** every one
   is drawn from the declared token set and no other color literal appears.
3. **Given** the generated stylesheet, **When** its font declarations are enumerated, **Then**
   every one resolves to the single Helvetica Neue stack and no `@font-face`, `@import`, or
   third-party URL appears.
4. **Given** the rendered page, **When** the horizontal rules are counted, **Then** there is one
   below the masthead, one below each section divider, one below the table's header row, and no
   rule between table body rows.
5. **Given** the rendered page, **When** the five philosophy heading levels are located, **Then**
   each is present at most once per role and visually distinct from the others by weight, size,
   case, and alignment alone — never by color.

---

### User Story 3 - A maintainer merges the restyle without breaking the guarantees (Priority: P2)

The maintainer reviews the diff and can see that the determinism, accessibility, and
never-publish-broken guarantees still hold, with a regenerated golden file whose every change is
explained.

**Why this priority**: the constitution's pre-merge gates make this mandatory, but it delivers
nothing to readers directly.

**Independent Test**: run the full suite, then run a dry run against an archived snapshot and
confirm validation passes.

**Acceptance Scenarios**:

1. **Given** the restyled templates, **When** the same archived snapshot is rendered twice,
   **Then** the output is byte-identical.
2. **Given** the restyled templates, **When** `validate_page` runs, **Then** it passes — exactly one
   `<h1>`, at least one table, scoped headers present, the `noindex` directive intact, no
   third-party reference, and the page under the weight budget.
3. **Given** the restyled templates, **When** the golden file is regenerated, **Then** every line
   of the diff is attributable to a requirement in this spec and the PR description explains it.

---

### Edge Cases

- **Helvetica Neue is absent** (Android, most Windows): the stack falls back to Arial. Accepted —
  metric-compatible enough that no layout breaks, and the alternative is a web font, which Principle
  IV forbids fetching at page load.
- **A very long team or manager name** in a dense table with tight horizontal padding: the table's
  own `overflow-x: auto` absorbs it. The page body must still not scroll.
- **The article section is absent** (its generation failed; see 001 FR-029): the page must not leave
  a dangling section divider, an orphaned rule, or a double gap where it would have been.
- **No events this week**: the single fallback sentence must sit at body level, not look like a
  placeholder, and must not be italic.
- **The index page with zero published weeks**: the "nothing published yet" sentence inherits the
  same stylesheet and must still look like a newspaper page with one line of copy, not an empty
  state.
- **A projection or provisional week** carries one or more caveat labels in the masthead area. With
  pills and badges gone, these must remain distinguishable from the surrounding meta line by case
  and weight alone.
- **Very wide viewport (1920px+)**: the table and masthead stretch; the prose column stops at its
  measure, left-aligned, leaving whitespace on the right rather than centering.
- **Print / print-to-PDF**: black-on-white with no backgrounds to drop out is already the best
  possible print case. No print stylesheet is required and none is added.

---

## Requirements *(mandatory)*

### Functional Requirements

Numbering continues above feature 001's range (which ends at FR-053) so that code comments citing
an FR stay unambiguous.

**Source of authority**

- **FR-060**: The repository MUST contain its own copy of the design philosophy at
  `docs/design-philosophy.md`, so that the authority this stylesheet is judged against is
  reviewable in a PR and survives changes to the author's home directory. The copy MUST record the
  date and origin it was taken from. *Satisfied: added alongside this spec, vendored from
  `~/dev/design-philosophy/design-philosophy.md` on 2026-10-20.*
- **FR-061**: Where this project's constitution and the design philosophy conflict, the
  constitution MUST win, and the deviation MUST be recorded in `docs/design-philosophy.md` as a
  project-specific amendment rather than left as an undocumented divergence. *Satisfied: the six
  deviations in this spec's clarifications are recorded under "Project amendments
  (ccsv-rumble-page)" in that file.*

**Palette**

- **FR-062**: The stylesheet MUST define exactly these color tokens and MUST NOT introduce any
  other color literal: `#111` (ink — text, rules, borders), `#fff` (background), `#555` (muted
  text), and `#f5c518` (yellow, reserved and unused on this surface). With the footer rule removed
  (FR-073), every rule on the page is `#111`, so `#ccc` and `#eee` have no remaining use and MUST
  NOT appear.
- **FR-063**: The stylesheet MUST NOT declare a `prefers-color-scheme: dark` block and MUST declare
  `color-scheme: light` so that form controls, scrollbars, and user-agent chrome do not invert.
- **FR-064**: Muted text MUST use `#555` (7.46:1 on `#fff`). `#888` (3.54:1), `#aaa` (2.32:1),
  `#ccc` (1.61:1), and `#eee` (1.16:1) MUST NOT be used for text at any size.
- **FR-065**: Color MUST NOT be the sole carrier of any meaning. Movement direction MUST be
  conveyed by its existing text label; `up`/`down` render in `#111`, `even`/`new` in `#555`.
- **FR-066**: Yellow MUST NOT appear as a text color, a link color, or a decorative fill. If a
  future surface uses it, it MUST be a background behind `#111` text.
- **FR-067**: Red MUST NOT appear on these pages.

**Typography**

- **FR-068**: Every element MUST render in `"Helvetica Neue", Helvetica, Arial, sans-serif`. The
  stylesheet MUST contain no second font stack, no `@font-face`, no `@import`, and no icon font.
- **FR-069**: Hierarchy MUST be created by weight, size, case, and alignment only — never by color.
- **FR-070**: The page MUST implement the philosophy's five heading levels, mapped to this page's
  existing markup without changing a single tag:
  1. **Masthead** — the existing `<h1>`. ~2.8rem, weight 900, left-aligned, letter-spacing
     `-0.04em`, line-height 1. Exactly one per page.
  2. **Section divider** — the `<h2>` for each page section ("Standings", "Around the league").
     Centered, ALL CAPS, bold, letter-spacing ~0.2em, 1px `#111` rule below running the full content
     width.
  3. **Article headline** — the `<h2>` carrying `article.headline`. Left-aligned, weight ~800,
     larger than body text, no rule, no background, no border. This is the same tag as level 2 and
     MUST be distinguished by class, not by tag.
  4. **Sub-headline / label** — the per-team lead-in currently rendered as
     `<strong>{{ team_name }}.</strong>`. Bold, normal case, `#111`, body size.
  5. **Column header** — `thead th`. 0.72rem (the floor in FR-078a, not the philosophy's 0.65rem),
     ALL CAPS, weight 900, `#555`; right-aligned for the numeric columns (Rank, Move), left-aligned
     otherwise.
- **FR-071**: Italic MUST NOT appear anywhere in the generated CSS or HTML. The `.note` caveat MUST
  render as roman `#555`.
- **FR-072**: ALL CAPS MUST be limited to section dividers, column headers, and the caveat labels
  described in FR-077. Negative letter-spacing MUST be limited to the masthead.

**Lines, shape, and surfaces**

- **FR-073**: The page MUST contain only these rules: 1px `#111` below the masthead; 1px `#111`
  below each section divider; and 1px `#111` below the table's header row. No other border MUST
  appear — in particular, the footer MUST be separated by vertical padding alone. On a week page
  this totals exactly four rules (masthead, "Standings", "Around the league", table header); on the
  index page, three.
- **FR-074**: Table body rows MUST NOT have separators. Row separation MUST come from vertical
  padding alone.
- **FR-075**: `border-radius`, `box-shadow`, and gradients MUST NOT appear anywhere. Every element
  is a rectangle.
- **FR-076**: No card, panel, or container border MUST surround any section, table, or note.
- **FR-077**: The `badge` element (`published late`, `draft-based projection`, `provisional`) MUST
  lose its pill border and radius and MUST adopt the column-header primitive: 0.72rem, ALL CAPS,
  weight 900, `#555`, no border, no fill.

**Density and layout**

- **FR-078**: Table cells MUST use tight padding — 0.28–0.3rem vertical, 0.25–0.5rem horizontal —
  so that rows are separated by padding rather than rules.
- **FR-078a**: Rendered text MUST respect these floors, which supersede the philosophy's own sizes
  (see the size clarification above): prose and table data at 1rem and 0.9rem respectively or
  larger, column headers and caveat labels at 0.72rem or larger. Nothing on either page MUST render
  below 0.72rem.
- **FR-079**: Numeric columns MUST use `font-variant-numeric: tabular-nums` so ranks and movement
  align down the column.
- **FR-080**: The masthead, section dividers, and tables MUST span the full content width with
  ~2rem horizontal page padding, reduced on narrow viewports.
- **FR-081**: Prose blocks (article intro, team notes, outro, notes, fallback sentences) MUST be
  capped at a readable measure and MUST be left-aligned within the full-width content area, not
  centered.
- **FR-082**: The rankings table MUST retain `overflow-x: auto` on its own container so the page
  body never scrolls horizontally at 320px.
- **FR-083**: Hover and selected states MUST NOT be applied to table rows. Hover MUST apply only to
  links.
- **FR-084**: Links MUST render as `#111` with an underline, and MUST keep a visible
  `:focus-visible` outline in `#111`.
- **FR-085**: `index.html.j2` MUST share the same stylesheet and MUST follow the same heading-level
  mapping: masthead `<h1>` and section-divider `<h2>`s for "Latest" and "Every week". The week list
  MUST keep its `<ul>`/`<li>` markup (FR-086) and MUST render with its list markers removed
  (`list-style: none`, no left padding), so that each week reads as a left-aligned row of links
  separated by padding rather than as a bulleted list. The same treatment applies to the events list
  on the week page.

**Guarantees that MUST survive unchanged**

- **FR-086**: No HTML tag, `scope` attribute, `aria-labelledby`, `<caption>`, landmark element, or
  heading level MUST be added, removed, or reordered. Changes MUST be confined to the stylesheet
  plus `class` attributes.
- **FR-087**: Rendering MUST remain deterministic and byte-identical for a fixed snapshot. The
  golden file MUST be regenerated and the diff explained in the PR per pre-merge gate 3.
- **FR-088**: The page MUST continue to fetch no third-party script, font, or stylesheet at load,
  and the stylesheet MUST remain inlined.
- **FR-089**: `validate_page` MUST continue to pass unchanged, including the single-`<h1>`,
  table-present, scoped-header, `noindex`, no-external-reference, and page-weight checks.
- **FR-090**: JavaScript MUST NOT be introduced. The page MUST remain fully readable with
  JavaScript disabled.

### Testing Requirements

The constitution asks for tests where the risk is. The risk in this change is contrast and
palette drift, so that is where the new assertions go.

- **FR-091**: A test MUST assert that every foreground/background text pair in the declared palette
  meets 4.5:1, computed from the token values rather than hardcoded as a comment. This is the single
  most valuable new test in this feature: the entire failure mode of adopting this philosophy is a
  gray that looks fine on the author's monitor and fails for a reader.
- **FR-092**: `test_stylesheet_supports_both_colour_schemes` MUST be replaced by a test asserting
  light-only rendering: `color-scheme: light` present, no `prefers-color-scheme` block, and the
  palette limited to the FR-062 token set.
- **FR-093**: A test MUST assert the absence of the banned primitives: `border-radius`,
  `box-shadow`, `gradient`, `italic`, `@font-face`, `@import`.
- **FR-094**: `test_wide_content_scrolls_inside_its_own_container` MUST continue to pass.
- **FR-095**: The golden-file test, the failure-path test, and the offline-replay test MUST all
  continue to pass with no change to their assertions.
- **FR-096**: A test MUST assert the FR-078a size floors by parsing the declared `font-size` values
  out of the stylesheet, since a contrast test passes at any size and cannot catch type that is
  legible-but-too-small.

### Known Breakage Inventory

Everything below is a known, intended break. A planner should treat this as the work list.

| Location | Current state | Required change |
| --- | --- | --- |
| `render/templates/style.css` | 11 color tokens, dark-mode block | 4 tokens, light-only (FR-062, FR-063) |
| `style.css` — `body` font | `ui-sans-serif, system-ui, …` | Helvetica Neue stack (FR-068) |
| `style.css` — `body` width | `max-width: 48rem; margin: 0 auto` | full-width content, capped prose measure (FR-080, FR-081) |
| `style.css` — `.badge` | `border-radius: 999px` + border | column-header primitive (FR-077) |
| `style.css` — `th, td` | `border-bottom` on every cell | 1px `#111` under `thead` only (FR-073, FR-074) |
| `style.css` — `.note` | `font-style: italic` | roman `#555` (FR-071) |
| `style.css` — `.move-up` / `.move-down` | green / red | tokens removed (FR-065) |
| `style.css` — `a` | `color: var(--accent)` maroon | `#111` + underline (FR-084) |
| `style.css` — `footer` | `border-top: 1px solid var(--rule)` | no rule; padding only (FR-073) |
| `style.css` — `ul` | `padding-left: 1.1rem`, markers shown | `list-style: none`, no left padding (FR-085) |
| `style.css` — sizes | 0.78–0.9rem muted text | FR-078a floors (≥1rem prose, ≥0.9rem data, ≥0.72rem labels) |
| `docs/design-philosophy.md` | absent | vendored copy + project amendments (FR-060, FR-061) |
| `page.html.j2` | `<h2>` undifferentiated | classes separating divider from headline (FR-070) |
| `index.html.j2` | inherits old look | same mapping (FR-085) |
| `tests/unit/test_accessibility.py` | asserts dark mode | replaced per FR-092, extended per FR-091, FR-093 |
| `tests/golden/week-01.html` | byte-compared | regenerated, diff explained (FR-087) |

### Key Entities

- **Design token**: a named color, font stack, or spacing value declared once in `:root` and
  referenced everywhere. The complete token set is closed by FR-062 and FR-068 — adding one is a
  spec change, not an implementation detail.
- **Heading level**: one of the five roles in FR-070. A role, not a tag; two roles share the `<h2>`
  tag and are separated by class.
- **Rule**: a 1px horizontal line marking a structural boundary. The complete set is closed by
  FR-073.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-020**: Every text color/background pair on both published pages measures at or above 4.5:1,
  verified by an automated test rather than by eye.
- **SC-021**: The generated stylesheet contains zero color literals outside the six declared
  tokens, zero font stacks outside the one declared stack, and zero occurrences of
  `border-radius`, `box-shadow`, gradient, or italic.
- **SC-022**: The page renders identically under light and dark operating-system settings.
- **SC-023**: At a 320px viewport the page body has zero horizontal scroll and the complete
  18-team ranking is reachable by vertical scrolling alone.
- **SC-024**: A rendered week page contains exactly four horizontal rules and the index page
  exactly three, with zero table-body row separators and zero footer rules.
- **SC-024a**: No text on either page renders below 0.72rem, and no prose below 1rem.
- **SC-025**: The HTML tag sequence, `scope` attribute count, landmark set, and `aria-labelledby`
  count are unchanged from before the restyle — diffable to zero.
- **SC-026**: A second render of the same archived snapshot is byte-identical to the first, and the
  only golden-file changes are `class` attributes and the inlined stylesheet.
- **SC-027**: Page weight stays under the configured budget, and `robots.txt` plus the `noindex`
  directive are untouched.
- **SC-028**: Zero third-party scripts, fonts, or stylesheets are fetched at page load, and the
  page is fully readable with JavaScript disabled.
- **SC-029**: A reader can distinguish all five heading levels from one another in a grayscale
  screenshot — proving hierarchy is carried by weight, size, case, and alignment rather than color.

---

## Out of Scope

- Any change to ranking numbers, movement classification, event derivation, or article prose.
- Any change to the HTML structure, ARIA attributes, or `scope` attributes (FR-086 forbids it).
- New page sections, new data on the page, or new columns in the rankings table.
- The sticky nav, matchup grids, master-detail panels, player tables, add/drop buttons, and
  interactive states described in the philosophy. They belong to the reference application; this
  surface has no navigation between sections, no selection, and no actions. Their *rules* are
  adopted where they bear on this page's primitives; their *components* are not ported.
- A dark theme, now or later, unless the philosophy itself is amended.
- A print stylesheet.
- Any web font, icon font, or SVG icon set.

---

## Assumptions

- The design philosophy is the intended visual direction for all of this author's surfaces, and
  consistency with it outranks the current page's existing look.
- The philosophy's reference `index.html` is authoritative where its prose and its implementation
  disagree (invoked once, for the 1px vs 3px divider rule).
- Helvetica Neue falling back to Arial on non-Apple platforms is acceptable, since the alternative
  violates Principle IV.
- Nobody depends on the current maroon accent, the green/red movement colors, or dark mode. No
  external consumer styles or scrapes these pages; they are `noindex` and unlisted.
- Removing the footer rule entirely (rather than keeping a `#ccc` line) is the correct reading of
  the philosophy's lines section, which permits that line only when another section follows
  "immediately with no gap." If a reviewer wants the footer visually detached, the fix is more
  padding, not a rule.
- The philosophy's density numbers are deliberately *not* adopted verbatim; see the size
  clarification and FR-078a. This is the one place where this spec makes the page less dense than
  the philosophy specifies, and it is the deviation most likely to be challenged in review. The
  grounds are Principle IV's stated rationale (phones, varied ages) plus the fact that a
  five-column table has no density pressure to relieve.
