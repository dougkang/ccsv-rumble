# Research — Draft Ranking (Week 0)

**Feature**: [`002-draft-ranking-week-0`](spec.md) · **Phase 0** · 2026-10-22

Eleven decisions. The first is the one the whole feature hinges on, and the design document says so
outright: FG% and FT% as makes and attempts is "a go/no-go question on the source, not a detail."

---

## D1 — Projection source

**Decision**: a **maintainer-curated local snapshot file** in a declared nine-category schema carrying
makes and attempts, read by an acquisition module behind a provider seam, and archived immutably with
its source identity and retrieval time.

**Rationale**:

- It is the only option that satisfies FR-010 without gambling on a third party's output format.
  Projection providers commonly publish `FG%` and `FT%` only, and FR-010 forbids inferring or
  defaulting the attempts — so a source that publishes percentages is not partially usable, it is
  rejected at ingest.
- It satisfies FR-012 and FR-015 cleanly: no network, so the snapshot trivially recomputes offline,
  and there is no terms-of-use exposure from automated retrieval.
- It is what the project already does, in substance. `rank/prior.py`'s own docstring reached this
  conclusion for 001: *"No licensed API offers them, and scraping a site to power a public page is
  both fragile and a terms question — so this reads an optional local CSV the maintainer populates by
  hand."* This decision keeps that judgment and fixes the two things wrong with its execution: the
  schema is too thin, and the file is never archived.
- FR-009 says projections come "from an external source", which this honours. The *origin* is
  external — a provider the maintainer has rights to read. What is removed is automated retrieval,
  not external provenance. The snapshot records which source and when, so provenance is auditable.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Automated retrieval from Hashtag Basketball / Dribble Grid | Terms-of-use exposure for a public page; output commonly percentage-only, which FR-010 rejects wholesale; and a scraped layout breaking mid-season takes the weekly page down |
| Derive attempts from a published percentage | Explicitly forbidden by FR-010. A rounded percentage cannot be re-aggregated, and the two categories it would corrupt are the two the category profile most depends on |
| Draft-slot prior (design doc §6 fallback 1) | Kept as the documented fallback, not the primary. It is a scalar with no category structure, so punt-build identification and the entire category profile are lost — and §3 exists precisely to avoid a scalar prior's units problem. "Strictly inferior, not co-equal" |
| Publish no ranking until week 2 (fallback 2) | The spec's resolved clarification is to publish week 0. This remains the final fallback if no compliant input can be produced at all |

**Consequence**: the existing `data/projections.csv` format is replaced, not extended. The file is
gitignored and the feature never shipped, so there is no migration burden — but the README's
documented format must change with it.

---

## D2 — Projected games played for the scored week

**Decision**: carry **per-player projected games for the target week inside the projection snapshot**,
rather than acquiring an NBA schedule separately.

**Rationale**: FR-017 forbids a league-average constant and requires the real schedule. Folding a
per-player, schedule-derived games count into the snapshot satisfies that — the value *is*
schedule-derived, at curation time — while keeping the computation pure (FR-021) and the project's
external dependencies at exactly one, which the design document §5 is careful about.

It also keeps FR-012 true without extra work: a snapshot that contains the games counts is sufficient
to recompute offline. A separate schedule source would have to be archived too, or replay would drift.

**Validation**: ingest must reject a snapshot whose games field is absent, and must record it per
player rather than per team, so a genuine 3-game/4-game split is preserved. Ingest does *not* attempt
to verify the counts against a real schedule — that would reintroduce the dependency this avoids.

**Alternatives considered**: a separate schedule input (second external dependency, second archive
kind, no benefit since the curator already needs the schedule); a games-per-week constant (forbidden
by FR-017, and the design document notes the 3-vs-4 game spread is large enough to matter across 18
teams).

---

## D3 — Active roster slot configuration — **NEEDS CLARIFICATION**

**Decision deferred.** FR-018 requires respecting active slot limits and position eligibility, and the
slot-filling rule cannot be declared without the real layout.

This is the plan's only open unknown, and it is **not blocked on provider access** — it is a league
setting the maintainer can read from the league's settings page in a browser. What is needed: the
active slot list with position eligibility, plus bench and injured-reserve counts (which contribute
nothing, per FR-024).

**Interim**: the slot layout is declared in `config.py` as league shape, alongside the existing
`TEAM_COUNT = 18` and `CATEGORY_COUNT = 9`. Once the real configuration is known it is a constant
change, not a design change. Implementation of Phase 4 should not begin until it is filled in, because
the slot-filling rule is what Phase 4 tests.

---

## D4 — Which rostered players count, and the tiebreak

**Decision**: fill active slots **greedily by each player's projected scalar value, subject to position
eligibility**, iterating slots in declared order, breaking ties by `(value desc, player_id asc)`.

**Rationale**: this is the design document §4's recommendation, and determinism is what FR-018 and
FR-022 actually require — not optimality. Greedy assignment is *not* guaranteed optimal when position
eligibility is constrained; a player who could fill two slots may be placed in the one that blocks a
better overall assignment. That is accepted and declared rather than hidden, because the alternative
is a matching algorithm whose benefit at 18 teams is marginal and whose behaviour is harder to explain
when someone disputes a rank.

**A nuance worth stating, because it looks like a contradiction.** §3 argues at length against a
scalar prior. This decision uses a per-player scalar anyway — but only to *choose contributors*, never
to *score teams*. Team scoring stays category-wise through the all-play grid. The scalar picks who
plays; it never decides who is better.

**Alternatives considered**: summing the whole roster (explicitly forbidden by FR-018 — it credits
bench depth the format cannot deploy); optimal assignment via maximum-weight matching (defensible but
unexplainable to a disputing member, and the declared-rule requirement is satisfied without it).

---

## D5 — Coverage thresholds

**Decision**: declared in `config.py` —

- `DRAFT_MIN_TEAM_COVERAGE = 0.80` — per team, the fraction of its **active slots** filled by players
  that have a projection. At a ten-slot lineup this permits two gaps.
- `DRAFT_MIN_LEAGUE_COVERAGE = 0.95` — across all teams' active slots.

Either falling below its threshold means publish nothing, exit non-zero, notify (FR-026, FR-038).

**Rationale**: the two thresholds catch different failures and both are needed. The per-team floor
catches one team being unrankable while the other seventeen are fine — the spec's named edge case.
The league-wide floor catches a systemic source problem that spreads thinly enough to clear every
per-team check. With ~180 active slots, `0.95` allows nine gaps league-wide; per-team `0.80` allows up
to two each, so the league floor binds first on a diffuse failure and the team floor binds first on a
concentrated one.

**Both numbers are judgment calls**, in the same register as the design document's own `0.65/0.35` and
`s`. They are declared so that changing them is a visible, versioned act.

---

## D6 — Is the unprojected-player count publishable?

**Decision**: **yes, as prose**, and it is recorded in the internal report regardless.

**Rationale**: this resolves an apparent conflict between two documents. The design document §7 says
the count "MUST ... surface the count on the page", calling it "a legitimate confidence caveat, and
hiding it is the kind of quiet degradation Principle II exists to prevent." FR-028 says the page must
show only rank and movement "as numbers **originating from the draft ranking computation**."

They do not actually conflict. The unprojected count does not originate from the computation — it is
an **input-coverage fact** about which rostered players the source covered, knowable before any
scoring happens. So FR-028 does not reach it, and FR-032's allowance for publishing a standing "as
prose or as a league-data fact" is the closest existing precedent.

**Published as prose, not as a table column**, to keep the rendering path unchanged and to avoid a
figure that a reader could mistake for a ranking output.

---

## D7 — Lifecycle state detection

**Decision**: a pure function over the snapshot, in a new top-level `lifecycle.py`:

| State | Condition |
|---|---|
| **pre-draft** | any team's roster has fewer than the league's required roster size, or no rosters exist |
| **post-draft** | all 18 rosters complete **and** zero scored weeks have completed |
| **in-season** | at least one scored week has completed |

**Rationale**: FR-002 requires the state be determined every run, and FR-008 requires an incomplete
draft be treated as pre-draft *with the reason recorded*. Making this a pure function of the snapshot
keeps it testable offline and keeps the decision out of the acquisition layer, where it would be
entangled with network failure.

"Scored week completed" must be supplied by acquisition rather than inferred in the pure layer — the
snapshot carries a count of completed scored weeks. Discovery on the sibling feature found a usable
signal: a team's record reads `0-0-0` until a matchup completes, so "completed" is observable rather
than guessed from the calendar. Deriving it from the date would be wrong, since a week in progress
looks finished to a clock.

**Alternatives considered**: inferring from the archive's week entries alone (an archived week is not
necessarily a *final* one, so this conflates acquired with scored); inferring from the date (fails
exactly in the window this feature targets).

---

## D8 — Declared constants

**Decision**: added to `config.py`, never written as literals at use sites (design document §7).

| Constant | Value | Source |
|---|---|---|
| `DRAFT_ALGORITHM_VERSION` | `"draft-v1"` | design document, FR-001 |
| `DRAFT_SHRINK` | `0.6` | design document §4, with a worked example |
| `DRAFT_MIN_TEAM_COVERAGE` | `0.80` | D5 |
| `DRAFT_MIN_LEAGUE_COVERAGE` | `0.95` | D5 |
| `ACTIVE_SLOTS` | *pending* | D3 |

`EMW_WEIGHT` and `CAW_WEIGHT` are **reused, not redeclared** — this is what keeps the two algorithms
agreeing about what "good" means, and redeclaring them would let them silently diverge.

`DRAFT_SHRINK = 0.6` is verifiable rather than arbitrary: the design document works an example where a
team whose point projections sweep five categories scores `AllPlay_proj ≈ .895` unshrunk, which would
outrank a *proven* dominant team at `.804`. Shrunk it lands at `.737`, below the proven team — the
correct ordering. Phase 5 should assert that example as a test, so the constant's justification is
executable.

---

## D9 — Fixing the purity violation

**Decision**: move projection loading out of `rank/` into `fetch/projections.py`, and widen
`tests/unit/test_architecture.py` to fail on filesystem and network access inside a pure package.

**Rationale**: `rank/prior.py:26` calls `path.open()`. Principle I requires the ranking computation be
free of filesystem access, and the architecture test — the designated enforcement mechanism — only
inspects the import graph against internal package names, so `csv` and `pathlib` pass unnoticed.

FR-021 restates purity for this computation and FR-011 moves the read into acquisition anyway, so the
fix is on the critical path rather than opportunistic cleanup. Widening the test is the part that
matters: without it the same violation returns, and the test's own docstring makes the point —
"A comment saying so decays; an assertion does not."

**Scope of the widened assertion**: forbid `open`, `pathlib.Path` I/O methods, and any network module
in `rank/`, `render/`, `report/`. Keep it an AST check over names rather than a runtime sandbox, which
is proportionate and consistent with how the test already works.

---

## D10 — Draft results, and what happens without them

**Decision**: acquire pick-by-pick draft results from the league provider, archive them immutably, and
when they are unavailable **publish the ranking and omit the article entirely** (FR-049).

**Rationale**: the recap is the one thing that genuinely needs the draft board; the ranking needs only
rosters. FR-049 already specifies the split, and it matters operationally right now: league-data
acquisition is the subject of the sibling feature `004-browser-session-provider`, whose own gates are
unresolved. So the realistic first shipment of week 0 is **rankings-only**, with the recap following
once draft results can be read.

This is a feature of the design rather than a compromise — FR-048 and FR-049 were written so the page
is complete without the article, and the omission is reported through the notification channel rather
than shown on the page.

---

## D11 — Ordering versus tiers

**Decision**: **1–18 ordering**, no tiers.

**Rationale**: settled by the spec's assumptions, and the design document §6 recommends the same while
presenting it as an open product call. The reasoning is that strict disclosure already hides the
scalar, so the only false precision a reader can see is the ordering itself — and a rendering path
that appears once a season is a poor trade for an 18-person audience. Keeping one rendering path is
also what lets this feature claim no change to `render/`.

If tiers were ever adopted, their boundaries would have to be declared constants, not eyeballed per
run.

---

## Resolved from the spec, recorded for completeness

- **Week 0 is published, not merely computed** — resolved 2026-10-20 in the spec.
- **The week-0 article is a league-wide draft recap** — resolved 2026-10-20.
- **Constitution version**: the spec cites v2.0.0; the governing version is now **v2.1.0**. The
  amendment added credential-renewal rules and touches nothing this feature relies on. The spec's
  reference to "the amended Principle I under which an archived, replayed acquisition stage is
  permitted" remains accurate.
