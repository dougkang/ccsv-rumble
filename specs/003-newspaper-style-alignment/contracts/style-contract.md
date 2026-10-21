# Contract: Templates ↔ Stylesheet

**Feature**: `003-newspaper-style-alignment` | **Date**: 2026-10-21

This feature has no API, CLI, or data-source surface; those contracts are unchanged from
[001's contracts](../../001-power-ranking-article/contracts/). The one interface it does define is
between the two Jinja templates and `style.css`: which classes the markup emits, and what the sheet
promises about each. Either side may change only within these terms. The values behind them (sizes,
tokens, rules) live in [data-model.md](../data-model.md) and are not repeated here.

---

## 1. Markup obligations (templates → sheet)

### `page.html.j2`

| Element | Required markup | Change from today |
|---|---|---|
| Masthead | `<header>` containing exactly one `<h1>` | none |
| Season/week line | `<p class="meta">` | none |
| Caveat labels | `<span class="badge">` (`published late`, `draft-based projection`, `provisional`) | none |
| Caveat note | `<p class="note">` | none |
| "Standings" heading | `<h2 id="standings-heading" class="section-divider">` | **add class** |
| Rankings table | `<table>` with `<caption>`, `<thead>` of 5 `<th scope="col">`, one `<th scope="row">` per team | none |
| Movement cell | `<td class="move {{ move_class(team) }}">` | none |
| Article headline | `<h2 id="writeup-heading" class="headline">` | **add class** |
| Team lead-in | `<strong>{{ team_name }}.</strong>` inside `<p>` | none |
| "Around the league" heading | `<h2 id="events-heading" class="section-divider">` | **add class** |
| Events list | `<ul class="plain-list">` | **add class** |
| Footer | `<footer>` with link `<p>` and `<p class="meta">` | none |

### `index.html.j2`

| Element | Required markup | Change from today |
|---|---|---|
| Masthead | `<header>` + one `<h1>` + `<p class="meta">` | none |
| "Latest" heading | `<h2 id="latest-heading" class="section-divider">` | **add class** |
| "Every week" heading | `<h2 id="archive-heading" class="section-divider">` | **add class** |
| Week list | `<ul class="plain-list">` | **add class** |

**Seven `class` additions, plus one filter on each template's `<style>` line, and nothing else.**
Any other markup diff breaks this contract: a changed tag, `id`, `scope`, `aria-labelledby`,
`<caption>`, landmark, or heading level (FR-086).

**Amendment (2026-10-21, found during implementation): `{{ stylesheet }}` →
`{{ stylesheet | safe }}` in both templates.** The environment autoescapes, and a `<style>`
element doesn't decode entities. The quoted `"Helvetica Neue"` therefore shipped as
`&#34;Helvetica Neue&#34;`, an invalid `font-family`, and every page fell back to Times. FR-068
could not be met without this change. The bug predates this feature: 001's golden file already
contained an escaped `&gt;`, but only inside a comment, so it never broke anything. Every test that
reads `stylesheet()` passed; the headless-browser probe caught it. The stylesheet is a
repository file, not data, so marking it safe opens no injection path. The filter changes only
bytes inside `<style>`, so the Scenario 3 body comparison is unaffected.
`test_stylesheet_ships_unescaped` now asserts that the shipped `<style>` equals `stylesheet()`
exactly, and that the sheet contains no `<`.

### Numeric-column marking

Right-aligning the numeric columns (Rank, Move) needs no new class. The sheet targets them by
existing structure: `tbody th` (the rank row header), `td.move`, and the matching `thead th` by
position. Positional selectors are acceptable here, unlike for headings ([research.md](../research.md)
§5), because the column order is fixed by 001's rankings-table contract. Reordering those columns
would already be a spec change.

---

## 2. Sheet obligations (sheet → templates)

The sheet MUST:

1. **Style only the classes in §1**, plus element selectors. A class the sheet styles but no
   template emits is dead code. A class a template emits but the sheet ignores means a styling
   decision was skipped.
2. **Declare exactly the four color tokens** in `:root` and refer to colors only through them
   (data-model.md §1).
3. **Declare every `font-size` in `rem`, all ≥0.72rem** (data-model.md §2, T1–T2).
4. **Produce exactly the rule inventory** in data-model.md §3: four on a week page, three on the
   index.
5. **Keep `overflow-x: auto`** on the table (the existing test matches that exact text).
6. **Contain none of:** `prefers-color-scheme`, `border-radius`, `box-shadow`, `gradient`, `italic`,
   `@font-face`, `@import`, `url(`.
7. **Make `h2.section-divider` and `h2.headline` distinguishable without color**: centered, ALL
   CAPS, ruled vs. left-aligned, normal case, unruled, heavier.
8. **Render a page correctly when an optional section is absent.** No rule or gap may depend on
   the article section being present (via `+` or `~` sibling selectors, for example).

---

## 3. What enforces this contract

| Term | Enforced by |
|---|---|
| No tag/ARIA/`scope` change | existing `test_accessibility.py` structure tests + golden diff review |
| Four tokens, contrast ≥4.5:1 | new contrast test (FR-091) |
| Light-only | replacement for `test_stylesheet_supports_both_colour_schemes` (FR-092) |
| Banned primitives (§2.6) | new banned-primitives test (FR-093) |
| `rem` only, ≥0.72rem | new size-floor test (FR-096) |
| `overflow-x: auto` | existing `test_wide_content_scrolls_inside_its_own_container` |
| Exact rule count, absent-section rendering, divider vs. headline | [quickstart.md](../quickstart.md) Scenarios 4, 6, 8 (visual) |
| Unused/missing classes (§2.1) | golden diff review; no automated check (see below) |

§2.1 is the only term without a test. Cross-referencing selectors against emitted classes would need
a CSS parser, and research.md §2 already turned down that dependency. With seven classes it can be
checked by eye in review. If the vocabulary grows, this is the first thing worth automating.
