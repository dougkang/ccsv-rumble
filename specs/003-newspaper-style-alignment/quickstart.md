# Quickstart: Validating the Newspaper-Style Restyle

**Feature**: `003-newspaper-style-alignment` | **Date**: 2026-10-21

Ten scenarios that show the restyle is correct and broke nothing. Scenarios 1–3 and 10 are
automated. Scenarios 4–8 need a browser and take a few minutes once. Scenario 9 is the
constitution's pre-merge dry-run gate.

The terms being checked are defined in [data-model.md](./data-model.md) (tokens, type scale, rules,
classes, layout) and [contracts/style-contract.md](./contracts/style-contract.md) (markup and sheet
obligations). This guide says how to check them; it doesn't restate them.

## Prerequisites

```bash
uv sync                       # Python 3.14 per .python-version
mkdir -p build/before build/after
```

Before changing any template, capture the **pre-restyle** render. Scenario 3 diffs against it.

```bash
uv run python -c "
import sys; sys.path[:0] = ['src', '.']
from tests.unit.test_render_deterministic import render_fixture_page
open('build/before/week-01.html', 'w').write(render_fixture_page())"
```

Run the same command with `build/after/` once the restyle is in place. `build/` is scratch output
and is not committed.

---

## Scenario 1: The stylesheet passes on its own (FR-091, 092, 093, 096)

```bash
uv run pytest tests/unit/test_accessibility.py -q
```

**Expected**: all green, including the four new or replaced tests: contrast from parsed tokens,
light-only, banned primitives, and size floor. Run this **before** editing templates (plan.md,
step 2). Passing here proves the sheet without any markup changes.

**Negative check, once**: temporarily set `--muted` to `#888`. The contrast test must fail and
report 3.54:1. Then add `font-size: 0.65rem` anywhere. The size test must fail no matter which
selector it's under. Revert both. This confirms the tests check what they claim to (SC-020,
SC-024a).

## Scenario 2: The palette is closed (SC-021)

```bash
grep -oiE '#[0-9a-f]{3,6}\b' src/ccsv_rumble/render/templates/style.css | sort -u
```

**Expected**: exactly `#111`, `#555`, `#f5c518`, `#fff`, each appearing once inside `:root`.
Any fifth value, or a token value repeated outside `:root`, is a contract violation.

## Scenario 3: Structure is unchanged (SC-025, FR-086)

```bash
for f in before after; do
  sed -E 's/ class="[^"]*"//g' build/$f/week-01.html \
    | sed -n '/<body>/,$p' > build/$f/body.html
done
diff build/before/body.html build/after/body.html && echo "structure identical"
```

**Expected**: `structure identical`. Once `class` attributes are removed and the `<head>` (which
holds the inlined CSS) is dropped, the body is byte-identical. Any remaining diff is a tag,
attribute, or text change that FR-086 forbids.

## Scenario 4: Exact rule count (SC-024)

Open `build/after/week-01.html` in a browser. In devtools, run:

```js
[...new Set([...document.querySelectorAll('*')].filter(e => {
  const s = getComputedStyle(e);
  return ['Top','Right','Bottom','Left'].some(side =>
    parseFloat(s[`border${side}Width`]) > 0 && s[`border${side}Style`] !== 'none');
}).map(e => e.closest('thead') || e))]
  .map(e => e.tagName + (e.className ? '.' + e.className : ''))
```

The header-row rule is drawn on each `thead th` cell, which is the form that renders reliably
inside the `display: block` table wrapper. The query maps every bordered cell to its `<thead>`
and dedupes by **element**, so five cells drawing one line count as **one rule**. The two section
dividers are different elements and stay as two entries.

**Expected** (week page): exactly four entries: `HEADER`, `H2.section-divider`,
`H2.section-divider`, `THEAD`. No `TD`, `TR`, `TBODY`, `FOOTER`, or `SECTION` entry. Render the
index with `render_index(season="2026-27", weeks=[1, 2, 3])` and expect **three**: `HEADER` plus
two `H2.section-divider`.

## Scenario 5: 320px, no body scroll (SC-023, FR-082)

In devtools responsive mode at **320 × 640**:

- `document.documentElement.scrollWidth <= 320` → `true`.
- All 18 rows are reachable by scrolling down. If the table is wider than the viewport, it scrolls
  horizontally **inside itself** and the page doesn't.
- Repeat at 768px and 1920px. At 1920px, prose stops at its measure and is **left-aligned**, while
  the masthead, section-divider rules, and the table's scroll container stretch the full width.
  The table's columns size to their content (FR-080 as amended, FR-081).

## Scenario 6: Optional article absent (edge case, constitution II)

```bash
uv run ccsv-rumble dry-run --from-archive --week <N> --no-article --out build/after
```

Without an archive (see Scenario 9), use the fixture render, which passes no `article`. That's
the case `build/after/week-01.html` already covers.

**Expected**: "Standings" is followed directly by "Around the league". There's no stray rule, no
double gap, and no orphaned headline styling. The rule count is still four.

## Scenario 7: Caveat labels without pills (FR-077, FR-071)

Render a projection week, which is what `002-draft-ranking-week-0` publishes:

```bash
uv run python -c "
import sys; sys.path[:0] = ['src', '.']
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.render.html import render_page
from ccsv_rumble.report import internal, publishable
from tests.conftest import make_snapshot
s = make_snapshot(1); r = build_ranking([s])
i = internal.build(season='2026-27', week=1, entry_id='entry-001', ranking=r, events=derive_events(s))
p = publishable.build(internal=i, history=[s], is_projection=True)
open('build/after/projection.html', 'w').write(render_page(report=p, entry_id='entry-001', generated_at='2026-10-27').html)"
```

**Expected**: `DRAFT-BASED PROJECTION` appears as small, heavy, all-caps `#555` text with no
border, no fill, and no rounded corners. The caveat note under it is roman (not italic) `#555`.
Both can be told apart from the meta line by case and weight alone.

## Scenario 8: Hierarchy without color, and no dark mode (SC-029, SC-022)

1. Apply devtools **Rendering → Emulate vision deficiency → Achromatopsia**, or take a screenshot
   and desaturate it. All five heading levels must still be distinguishable: masthead, section
   divider, headline, team lead-in, and column header.
2. Toggle **Rendering → Emulate CSS prefers-color-scheme: dark**. **Expected**: the page doesn't
   change at all. It stays white with black ink and no inverted regions.
3. With **Disable JavaScript** on, reload. **Expected**: identical (FR-090).

## Scenario 9: Pre-merge dry run from the archive (constitution gate 2)

```bash
git pull origin main           # archives are committed to main by the weekly workflow
uv run ccsv-rumble dry-run --from-archive --week <latest archived week>
```

**Expected**: exit 0, `validate_page` passes, and no network or model call is made. Open the
output and repeat Scenarios 4 and 5 on a real week, which has real team-name lengths.

**If no archive exists yet** (true on 2026-10-21, because no weekly run has committed one): the
replay path is still covered by the integration tests in Scenario 10. Record in the PR that gate 2
ran against fixtures rather than a real archive, and run this scenario against the first archived
week before the restyle's first live publish.

## Scenario 10: Full suite and golden-file review (FR-087, FR-095, constitution gates 1 and 3)

```bash
uv run ruff check src/ tests/
rm tests/golden/week-01.html
uv run pytest -q                              # the golden test recreates the file
git diff --stat -- tests/golden/week-01.html
git diff -- tests/golden/week-01.html
```

**Expected**:

- Ruff is clean and every test passes. The golden, cross-process determinism, failure-path, and
  offline-replay tests all pass with unchanged assertions.
- The golden diff contains **only** `<style>` content and the seven `class` additions listed in
  contracts/style-contract.md §1. Any changed number, name, or sentence means the restyle reached
  past presentation. Stop and find out why.
- Copy a one-paragraph summary of that diff into the PR description (pre-merge gate 3). If
  `002-draft-ranking-week-0` merges first, regenerate the golden file instead of hand-merging it.
  See plan.md, "Interaction with `002-draft-ranking-week-0`".

---

## Done when

- [ ] Scenarios 1–3 and 10 pass and their output is pasted into the PR
- [ ] Scenarios 4–8 checked by eye and noted in the PR
- [ ] Scenario 9 run against a real archive, or its fixture fallback recorded in the PR
- [ ] Golden diff explained in the PR description
