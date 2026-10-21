<!-- Vendored copy. Origin: ~/dev/design-philosophy/design-philosophy.md, taken 2026-10-20.
     This copy is the authority this project's stylesheet is judged against (spec 003, FR-060).
     Project-specific amendments, where the project constitution supersedes the philosophy, are
     recorded at the end of this file under "Project amendments (ccsv-rumble-page)".
-->

# UI Design Philosophy

The theme is **newspaper meets nutrition label**. Clean, easy to read — even though the data density is high. Helvetica Neue only, no exceptions. Every visual decision serves legibility first.

---

## Color

Three colors only.

- **Black `#111`** — text, borders, primary buttons, structural lines. The default ink.
- **White `#fff`** — background. Nothing else.
- **Yellow `#f5c518`** — the single accent. Used exclusively to mean "yours" or "selected": your matchup header, highlighted/selected rows, active pills, slot-picker hover. Never used decoratively.

Red `#c00` appears only on destructive actions (the drop button). It is not a design color; it is a warning.

Grays (`#555`, `#888`, `#aaa`, `#ccc`, `#eee`) are used for muted state only: bench rows, inactive nav links, placeholder text, disabled controls. If something is gray, it is secondary or unavailable.

**Rule:** if you're reaching for a new color, ask whether yellow, black, or gray already communicates what you need. They almost always do.

---

## Typography

**One font: Helvetica Neue. No other choices.**

No icon fonts, no display fonts, no web fonts. Weight and size alone create hierarchy.

### Heading levels

There are five distinct levels. Each has a specific job; they are not interchangeable.

**1. Masthead** — the page title ("NBA Sim League 2023")
Large, heavy, left-aligned, negative letter-spacing. This is the newspaper's nameplate. It dominates the top of the page and is separated from everything below by a thick black rule. Only one instance per page. Weight: 800–900. Size: ~3rem.

**2. Section divider** — "GAMES", "STANDINGS", "PLAYERS" as page section breaks
Centered. ALL CAPS. Bold. Thick black rule below (3px). Generous letter-spacing (~2px). This is how a newspaper announces a new section. The rule runs the full width of the content area. Nothing decorative — just the word and the line.

**3. Matchup headline** — "Top Seeds 450, Playmakers 524"
Left-aligned. Bold (~800). Larger than body text but smaller than the masthead. No decoration, no background, no border. Reads like a sports article's headline — factual, punchy, the score is right there. This is the "article title" level.

**4. Sub-headline / team label** — "Top Seeds", "Playmakers" (column header of a table)
Bold, normal case, black. Left-aligned. Same size as or slightly larger than body text. No decoration — the bold weight does the work. This is a label, not a heading; it introduces a data block.

**5. Column header** — "FP  PTS  REB  AST  STL  BLK  TO"
Very small (~0.65rem). ALL CAPS. Heavy (900). Muted gray. Right-aligned for numeric columns. Tight letter-spacing. These are workhorse labels — they must be legible but invisible to the eye scanning for data.

### Rules

- Never use italic except for: quoted opinions, loading/placeholder states.
- Never use color to convey hierarchy — use weight.
- ALL CAPS is reserved for navigation links, section dividers, and column headers. Nowhere else.
- Negative or tight letter-spacing only on the masthead. Everything else: normal or slightly positive.

---

## Lines and borders

**Use as few lines as possible.** Whitespace separates rows — not rules. A line should only appear when it marks a structural boundary that whitespace alone cannot communicate.

Lines in use:

- **1px solid `#111`** — the single line below the masthead. One per page.
- **1px solid `#111`** — below the column header row in a table. Separates labels from data.
- **1px solid `#ccc`** — below a section's last row, only when another section follows immediately with no gap.

What is absent by default:

- No row separators in table bodies. Rows are distinguished by padding alone.
- No card or panel borders. Matchup blocks, standings blocks, and detail panels have no surrounding box.
- No box shadows. No gradients. No border-radius anywhere — every element is a rectangle.
- No borders on nav items, buttons-as-pills, or interactive rows unless they are true `<button>` elements that need affordance.

**Rule:** before adding a line, ask whether more vertical padding achieves the same separation. It almost always does.

---

## Shape

No border-radius anywhere. Every element is a rectangle.

Interactive `<button>` elements use a **1px solid `#111`** border to signal clickability. Inputs use the same. Everything else is borderless.

---

## Data density

The UI is for people who want to see a lot of information at once. Whitespace is not a decorative goal — it is a separator.

- Table cells use tight padding (0.28–0.3rem vertical, 0.25–0.5rem horizontal)
- Data fonts are small (0.78rem) to fit more columns
- Multiple stat columns are always visible — no progressive disclosure for stats
- Bench rows are muted (gray) so the eye goes to starters first
- Inactive stats show `–` not `0` to signal absence vs. zero performance
- Integer display for scores and totals; one decimal for averages

**Rule:** prefer showing data over hiding it. A dense table beats an accordion. But rows breathe through padding, not lines.

---

## Interactive states

Every interactive element has exactly two states beyond default: hover and selected/active.

- **Hover on rows**: `#eee` light gray background — just enough to show clickability
- **Selected / active**: `#f5c518` yellow background — the same yellow as "yours"
- **Primary button** (submit, add): black fill, white text, darkens to `#333` on hover
- **Secondary button** (pager, slot, add/drop): transparent, black border, yellow on hover
- **Destructive button** (drop): red border + red text, fills red on hover

Disabled states use `#aaa` borders and text. Pending/in-flight states use italic + 75% opacity.

**Rule:** yellow = selected or mine. Never use yellow as a primary button color — it's a selection indicator, not a CTA color.

---

## Layout

The app is a single page with scroll-based sections. The nav is sticky and highlights the current section. Nav items are plain text — no borders, no pills, no backgrounds. The active item is distinguished by weight or an underline only.

Within sections:

- Matchups: `grid-template-columns: repeat(auto-fit, minmax(580px, 1fr))` — side by side when space allows. No card border around each matchup.
- Standings: `1fr 1fr` — table left, activity/opinion right
- Players: `1fr 1fr` — list left, detail right (master-detail)

No centered containers with large side margins. Content runs close to the viewport edges (2rem padding). No wrappers with `max-width` and `margin: auto` unless the viewport is very wide.

---

## What this is not

- Not a dashboard product (no cards, no KPI tiles, no progress bars)
- Not a consumer app (no rounded corners, no drop shadows, no illustrations)
- Not minimal/blank (data fills the space — emptiness is a loading state, not an aesthetic)
- Not heavily gridded — lines are earned, not sprinkled

The reference point is a well-formatted sports statistics page: every pixel is occupied by information, the structure is exposed rather than hidden, and the design earns trust through density and clarity rather than beauty.

---

## Project amendments (ccsv-rumble-page)

Where this philosophy and the project constitution (`.specify/memory/constitution.md`) conflict,
the constitution wins. Every such deviation is recorded here rather than left as an undocumented
divergence. Derivations are in `specs/003-newspaper-style-alignment/spec.md`.

1. **Muted gray is `#555`, not `#888` or `#aaa`.** Measured on `#fff`: `#555` = 7.46:1,
   `#888` = 3.54:1, `#aaa` = 2.32:1. Principle IV requires 4.5:1 for text. The gray *semantics*
   (gray = secondary or unavailable) are adopted unchanged; only the values move. `#ccc` and `#eee`
   are never text; since every rule on these pages is `#111`, they end up with no use at all here.
2. **No dark mode.** The philosophy's "White `#fff` — background. Nothing else" is taken literally.
   A dark palette cannot be expressed in three colors.
3. **Minimum rendered text size.** The philosophy's 0.78rem data text and 0.65rem column headers
   are sized for a seven-stat-column desktop table. This project's table has five columns and is
   read on phones by a congregation of varied ages, so the density allowance is not needed:
   prose is 1rem, table data is at least 0.9rem, column headers at least 0.72rem. The density
   *principle* — separation by padding, not lines — is adopted in full.
4. **Prose keeps a measure cap.** The masthead, section dividers, and the table's scroll container
   run full width; prose stops at a readable measure (`max-width: 40rem`), left-aligned (never
   centered). This uses the philosophy's own "unless the viewport is very wide" allowance and serves
   its first sentence: legibility first. The table's *columns* size to their content, not to
   the width: the `display: block` wrapper that keeps a phone from scrolling the page sideways
   also shrink-wraps the grid inside it. For a five-column table that is the more legible result
   anyway.
5. **Yellow is unused on this surface.** Yellow means "yours" or "selected" and is "never used
   decoratively." A static page with no viewer identity and no selection state has no legitimate
   place for it. The token is kept, documented and unused, so a future interactive surface inherits
   it correctly.
6. **Section dividers use a 1px rule, not 3px.** The philosophy's typography section says 3px; its
   lines section and its reference `index.html` both say 1px. The implementation wins.
7. **No footer rule, no list markers.** The footer is separated by padding alone — the philosophy's
   `#ccc` line is permitted only when another section follows with no gap. Lists keep their
   `<ul>`/`<li>` markup for semantics but render without markers, as rows separated by padding.
