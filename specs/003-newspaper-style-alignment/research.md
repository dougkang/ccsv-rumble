# Phase 0: Research — Newspaper-Style Visual Alignment

**Feature**: `003-newspaper-style-alignment` | **Date**: 2026-10-20

## Scope note: there were no unknowns

The plan's Technical Context contains zero `NEEDS CLARIFICATION` markers, and that is not an
oversight. The stack is fully determined (Python 3.14, Jinja2, pytest, static HTML), no new
dependency is involved, and the spec's clarification round already resolved all twelve open design
questions by derivation from the two governing documents. Manufacturing research tasks here — "best
practices for CSS color tokens", "patterns for Jinja2 class attributes" — would produce text nobody
needs to make a decision from.

What this document records instead is the set of **implementation decisions** that the spec
deliberately left to planning: how to make its requirements mechanically checkable. Four of them
materially changed the design, which is why they are written down rather than discovered during
implementation.

---

## 1. How to assert the contrast floor (FR-091)

**Decision**: compute WCAG 2.x relative-luminance contrast ratios in the test, from the hex values
parsed out of the stylesheet's `:root` block, and assert every (text token × background) pair that
the sheet can actually produce.

**Rationale**: the alternative — hardcoding "we checked, `#555` is 7.46:1" in a comment — is a
claim, not a check. It stays true only until someone edits a token. Parsing the declared tokens
means the test fails when the palette changes, which is exactly when a human needs to look.

The pairs that exist on this surface are small and enumerable: `#111` on `#fff` (18.88:1), `#555` on
`#fff` (7.46:1), and `#111` on `#f5c518` (11.58:1, for the reserved yellow should it ever be used).
Each passes 4.5:1. The formula is ~12 lines of standard library Python; no dependency is needed, and
adding one for this would fail the constitution's dependency-restraint rule.

**Alternatives considered**:

- *An external accessibility linter (axe, pa11y)*: requires Node and a headless browser — a heavy
  new toolchain for one assertion, and it checks rendered pages rather than the token contract, so
  it would not catch an unused-but-wrong token before someone reaches for it.
- *Hardcoded expected ratios per pair*: brittle in the wrong direction. It fails when someone
  deliberately changes a token and passes when they add a new one.
- *Asserting only the pairs currently used in the sheet*: weaker than it looks, because the whole
  point is to catch the next pair someone introduces.

---

## 2. How to assert the size floor (FR-096) — the decision that changed shape

**Decision**: assert that **every** `font-size` declaration anywhere in the stylesheet is ≥0.72rem,
with no per-selector exceptions, and require every `font-size` to be declared in `rem` units so a
single regex can read them all.

**Rationale**: the spec's original wording ("parsing the declared `font-size` values out of the
stylesheet") admits a test that checks the column-header selector and passes while a `0.62rem`
sits under a selector the test never names. That is a test that reports safety it has not verified.
A blanket assertion over all matches cannot miss a selector, because it does not know about
selectors at all — it reads the whole sheet. That makes it strictly more robust *and* simpler,
which is unusual enough to be worth the explicit note.

The cost of the blanket form is that it forbids any legitimately smaller `font-size`. On this
surface there is none: the smallest thing on either page is a column header or a caveat label, both
floored at 0.72rem by FR-078a. If a future element genuinely needs to be smaller, the test failing
is the correct outcome — it forces the exception to be argued in a spec amendment rather than
slipped into a sheet.

**Mixed units are the trap this closes.** `font-size: 10px` and `font-size: 0.65em` would both
evade a `rem`-only regex while rendering below the floor. Hence the contract term: `rem` only, which
also happens to be the right unit for respecting a reader's browser font-size setting — relevant for
a page read by a congregation of varied ages.

**Alternatives considered**:

- *Per-selector assertions*: rejected above — misses what it does not name.
- *Rendering the page in a headless browser and reading computed styles*: catches cascade and
  inheritance effects a regex cannot, but needs a browser in CI for one assertion. Deferred; if
  cascade bugs ever appear in practice, this is the upgrade path.
- *A CSS parser dependency (`tinycss2`)*: more correct parsing than a regex, but a new runtime-adjacent
  dependency for a 4-token, ~70-line sheet does not clear the dependency-restraint bar.

---

## 3. How to cap the prose measure without a new class

**Decision**: apply the measure cap to `p` and `li` directly. No `.prose` class, no wrapper element.

**Rationale**: every piece of prose on both pages is already inside a `<p>` or an `<li>` — the
article intro, the per-team notes, the outro, the caveat note, the events list, the empty-state
sentences, the footer meta line, and the index's week list. A bare element selector therefore has
exactly the right reach, and it means the markup carries one less `class` attribute that could drift
out of sync with the sheet. It also keeps FR-086's "classes only, no tags" promise cheaper to honor:
fewer template edits, smaller golden diff.

The cap is left-aligned within a full-width content area, not a centered container — the philosophy
explicitly forbids "centered containers with large side margins," and tables and the masthead still
run the full width.

**Alternatives considered**:

- *A `.prose` class on each prose element*: more explicit, but it is explicitness about something no
  reader of the sheet is confused by, bought with ~8 template edits.
- *A `max-width` on `main`*: would cap the table too, defeating the full-width-table requirement
  (FR-080) and making the `overflow-x` container fire sooner than it needs to.
- *`ch` units for the measure*: arguably the more principled unit for line length, but it makes the
  cap depend on the font's zero-glyph width, which is exactly the kind of implicit coupling that
  makes a sheet hard to reason about later.

---

## 4. The palette shrank from six tokens to four

**Decision**: the sheet declares `#111`, `#fff`, `#555`, and `#f5c518` (reserved, unused). `#ccc`
and `#eee` do not appear.

**Rationale**: this fell out of resolving the spec's own internal contradiction. FR-073 originally
permitted a `#ccc` rule above the footer while SC-024 capped the page at four rules — and a week
page with masthead, two section dividers, a table header, and a footer rule has five. Removing the
footer rule (the philosophy permits that line only when another section follows "immediately with no
gap," which a footer does not) resolved the contradiction, and in doing so left `#ccc` and `#eee`
with nothing to color: every remaining rule is `#111`, and neither value may be used for text.

A four-token closed set is a materially stronger invariant than a six-token one, because SC-021
("zero color literals outside the declared tokens") now excludes the two values most likely to be
reached for by reflex when something needs to look subtle.

**Alternatives considered**:

- *Keep `#ccc`/`#eee` declared but unused, as yellow is*: yellow earns its place because the
  philosophy assigns it a specific future meaning ("yours"/"selected") that a later interactive
  surface will need. `#ccc` carries no such reserved meaning — it is just a light gray, and keeping
  it is an invitation rather than a provision.
- *Keep the footer rule and relax SC-024 to five*: possible, but it spends the page's line budget on
  the one boundary where whitespace works best, against the philosophy's explicit test ("before
  adding a line, ask whether more vertical padding achieves the same separation").

---

## 5. Three `<h2>`s, three different jobs — the class split

**Decision**: `<h2 class="section-divider">` on "Standings" and "Around the league";
`<h2 class="headline">` on the article headline. Tag, `id`, and `aria-labelledby` wiring all
unchanged.

**Rationale**: the philosophy's heading levels 2 and 3 are different roles — a centered ALL-CAPS
section break with a rule below, versus a left-aligned bold article headline with no decoration —
and `page.html.j2` currently renders all three as structurally identical `<h2>` elements. Since the
heading *level* is semantically correct in all three cases (they are all second-level sections of
the page), the distinction belongs in presentation, not in markup depth. Changing one of them to an
`<h3>` to get different styling would corrupt the heading outline that
`test_heading_levels_are_not_skipped` guards, and would misrepresent the document structure to a
screen reader.

**Alternatives considered**:

- *Structural CSS selectors (`section:first-of-type h2`, `h2 + p`)*: no template edit at all, which
  is tempting. Rejected because it ties presentation to section order — reordering sections or
  inserting one silently restyles headings, and the breakage would appear only in a visual check.
- *Changing the article headline to `<h3>`*: breaks heading order and lies about structure.

---

## 6. Font stack and the Helvetica Neue fallback

**Decision**: `"Helvetica Neue", Helvetica, Arial, sans-serif`, taken verbatim from the philosophy's
reference implementation. No `@font-face`, no `@import`, no web font.

**Rationale**: Principle IV forbids depending on a third-party font fetched at page load, so a
locally-installed stack is the only compliant way to honor "Helvetica Neue only." On Apple devices
the first entry hits. On Android and most Windows machines it falls through to Arial, which is
metrically close enough that no layout assumption breaks. Accepting a fallback is strictly better
than the alternatives: a web font violates Principle IV, and self-hosting a font file adds weight to
a page whose budget exists precisely to stay light on phones.

**Alternatives considered**:

- *Self-hosting a Helvetica-like open font (Inter, Helvetica Now)*: no third-party *fetch*, so it
  would clear Principle IV on a technicality, but it adds 20–100KB to every page load for a
  typographic difference most readers will not notice, and it is not Helvetica Neue either.
- *`system-ui` first*: what the page does today. Rejected — it is precisely the templated-default
  look the philosophy exists to replace, and it renders differently on every platform.

---

## Summary of decisions

| # | Decision | Changes the spec? |
|---|---|---|
| 1 | Contrast computed from parsed tokens, all pairs asserted | No — implements FR-091 |
| 2 | **Every** `font-size` ≥0.72rem, `rem` units mandatory | Tightens FR-096; adds a contract term |
| 3 | Measure cap on `p`/`li`, no new class | No — implements FR-081 |
| 4 | Four tokens, not six; no footer rule | Already folded into FR-062/FR-073 |
| 5 | `.section-divider` vs `.headline` on `<h2>` | No — implements FR-070 |
| 6 | Local Helvetica stack, Arial fallback accepted | No — implements FR-068 |

**Output**: no unresolved unknowns. Proceed to Phase 1.
