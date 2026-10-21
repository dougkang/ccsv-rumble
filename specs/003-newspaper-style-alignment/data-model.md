# Phase 1: Data Model — Newspaper-Style Visual Alignment

**Feature**: `003-newspaper-style-alignment` | **Date**: 2026-10-20

This feature has no runtime entities, no persisted state, and no schema. Its "model" is the set of
**closed vocabularies** the stylesheet is built from. They are documented here with the same rigor a
data model would get, for one reason: every success criterion in the spec is phrased as a property
of these sets, so they are what the tests actually assert against.

A vocabulary being **closed** means adding a member is a spec amendment, not an implementation
choice. That is the whole enforcement mechanism — it converts "does this look right?" into "is this
value in the set?"

---

## 1. Color tokens (closed — exactly four)

| Token | Value | Role | Contrast | May be used for |
|---|---|---|---|---|
| `--ink` | `#111` | default ink | 18.88:1 on `--paper` | all body text, headings, every rule, link text |
| `--paper` | `#fff` | background | — | page background, nothing else |
| `--muted` | `#555` | secondary / unavailable | 7.46:1 on `--paper` | caveat note, column headers, caveat labels, footer meta, `move-flat`, `move-new` |
| `--select` | `#f5c518` | "yours" / "selected" | `--ink` on it = 11.58:1 | **nothing on this surface.** Reserved, declared, unused. |

**Invariants**

- **I1**: No color literal may appear in the sheet outside these four declarations. (SC-021)
- **I2**: Every text pair must be ≥4.5:1. Enumerated pairs: `--ink`/`--paper` 18.88:1,
  `--muted`/`--paper` 7.46:1, `--ink`/`--select` 11.58:1. (FR-091, SC-020)
- **I3**: `--select` may only ever be a *background* behind `--ink`. As a text or link color it is
  1.63:1 on white — illegible. (FR-066)
- **I4**: Banned values, explicitly: `#888` (3.54:1), `#aaa` (2.32:1), `#ccc` (1.61:1), `#eee`
  (1.16:1), `#c00` (red — no destructive action exists here), and the outgoing `--accent` maroon,
  `--up` green, and `--down` red. (FR-064, FR-065, FR-067)
- **I5**: No `prefers-color-scheme` block. `color-scheme: light` is declared so user-agent chrome
  does not invert. (FR-063)

**Why four and not six**: see [research.md](./research.md) §4. Removing the footer rule left `#ccc`
and `#eee` with nothing to color.

---

## 2. Type scale (closed — floors are hard)

| Role | Size | Weight | Case | Align | Letter-spacing |
|---|---|---|---|---|---|
| Masthead (`h1`) | 2.8rem | 900 | normal | left | `-0.04em` |
| Section divider (`h2.section-divider`) | 0.9rem | 700 | ALL CAPS | center | `0.2em` |
| Article headline (`h2.headline`) | 1.3rem | 800 | normal | left | normal |
| Sub-headline / team label (`strong`) | 1rem | 700 | normal | left | normal |
| Column header (`thead th`) | 0.72rem | 900 | ALL CAPS | right for numeric, else left | `0.05em` |
| Body / prose (`p`, `li`) | 1rem | 400 | normal | left | normal |
| Table data (`tbody td`, `tbody th`) | 0.9rem | 400 | normal | left, numeric right | normal |
| Caveat label (`.badge`) | 0.72rem | 900 | ALL CAPS | inline | `0.05em` |
| Footer meta (`.meta`) | 0.9rem | 400 | normal | left | normal |

**Invariants**

- **T1**: Every `font-size` in the sheet is ≥0.72rem. No exceptions, asserted over all declarations
  rather than per selector. (FR-096, research.md §2)
- **T2**: Every `font-size` is declared in `rem`. `px`, `em`, `pt`, and keywords are forbidden — a
  mixed unit would evade T1's check while rendering below the floor.
- **T3**: Prose is ≥1rem; table data ≥0.9rem. (FR-078a)
- **T4**: One font stack only: `"Helvetica Neue", Helvetica, Arial, sans-serif`. No second stack, no
  `@font-face`, no `@import`, no icon font. (FR-068, SC-021)
- **T5**: `font-style: italic` appears nowhere. (FR-071)
- **T6**: Negative letter-spacing appears only on the masthead. ALL CAPS appears only on section
  dividers, column headers, and caveat labels. (FR-072)
- **T7**: Hierarchy is carried by size, weight, case, and alignment only — never color. Verifiable
  by reading the table above: no two roles differ *only* by color. (FR-069, SC-029)

---

## 3. Rule inventory (closed — exactly four per week page)

| # | Where | Spec | Present on |
|---|---|---|---|
| 1 | below the masthead | 1px solid `--ink` | both pages |
| 2 | below `h2.section-divider` — "Standings" | 1px solid `--ink` | week page |
| 3 | below `h2.section-divider` — "Around the league" | 1px solid `--ink` | week page |
| 4 | below the table's `thead` row | 1px solid `--ink` | week page |

Index page: masthead + "Latest" + "Every week" = **three**.

**Invariants**

- **R1**: A week page has exactly four rules; the index exactly three. Exact, not maximum — an exact
  count catches a missing rule as well as a stray one. (SC-024)
- **R2**: Zero borders on `tbody` rows and cells. Row separation is vertical padding alone.
  (FR-074)
- **R3**: Zero rules in the footer. Separation is padding. (FR-073)
- **R4**: Zero card, panel, or section borders. (FR-076)
- **R5**: `border-radius`, `box-shadow`, and gradients appear nowhere. (FR-075, SC-021)
- **R6**: `h2.headline` carries no rule — it is an article headline, not a section break. (FR-070)

---

## 4. Class vocabulary (closed)

Every class the stylesheet styles, and where it comes from. Classes marked **new** are the only
markup additions this feature makes; FR-086 forbids everything else.

| Class | On | Status | Emitted by |
|---|---|---|---|
| `section-divider` | `h2` ("Standings", "Around the league", "Latest", "Every week") | **new** | template literal |
| `headline` | `h2` (article headline) | **new** | template literal |
| `plain-list` | `ul` (events list, week list) | **new** | template literal |
| `meta` | `p` (season/week line, footer timestamp) | existing | template literal |
| `note` | `p` (projection / provisional caveat) | existing | template literal |
| `badge` | `span` (`published late`, `draft-based projection`, `provisional`) | existing | template literal |
| `move` | `td` (movement cell) | existing | template literal |
| `move-up`, `move-down`, `move-flat`, `move-new` | `td.move` | existing | `html.py:_move_class()` |

**Invariants**

- **C1**: The four `move-*` classes keep their names and keep being emitted by `_move_class()`
  unchanged. `move-up`/`move-down` resolve to `--ink`; `move-flat`/`move-new` to `--muted`. Two
  pairs sharing a color is intentional — the names describe the *data*, not the paint, and renaming
  them would be a Python change this feature does not make.
- **C2**: No class is added beyond the three marked new. (FR-086, SC-025)
- **C3**: No tag, `id`, `scope`, `aria-labelledby`, `<caption>`, or landmark changes. (FR-086)

---

## 5. Layout model

| Region | Width | Horizontal padding |
|---|---|---|
| masthead, section dividers, table | full content width | 2rem (0.75rem below 420px) |
| prose (`p`, `li`) | capped at a measure, **left**-aligned | inherits |

**Invariants**

- **L1**: No centered container, no `margin: auto` on a `max-width` wrapper. (FR-080, FR-081)
- **L2**: The table keeps `overflow-x: auto` on its own container; the page body never scrolls
  horizontally at 320px. (FR-082, FR-094, SC-023)
- **L3**: No hover or selected state on table rows — they are not interactive. Hover applies to
  links only. (FR-083)
- **L4**: Links are `--ink` + underline, with a visible `:focus-visible` outline in `--ink`.
  (FR-084)
- **L5**: Lists keep `<ul>`/`<li>` markup and render without markers (`list-style: none`, no left
  padding). (FR-085)

---

## 6. What has no model here

Stated so a reader does not look for it: this feature defines no entity, stores nothing, transforms
no data, and adds no field to `PublishableReport`, `PublishedPage`, or any snapshot. The published
HTML's *content* is byte-for-byte the same facts as before; only its presentation changes. That is
why [plan.md](./plan.md)'s constitution check marks Principles I, III, and V as not-applicable
rather than as satisfied-by-design.
