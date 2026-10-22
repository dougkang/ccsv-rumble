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

## D3 — Active roster slot configuration — **RESOLVED**

**Supplied by the maintainer, 2026-10-22**: `2G, 3FC, 1 Util, 4 B, 2 IL`.

```python
ACTIVE_SLOTS: Final[tuple[str, ...]] = ("G", "G", "FC", "FC", "FC", "UTIL")   # 6
BENCH_SLOTS: Final[int] = 4
IL_SLOTS: Final[int] = 2
DRAFT_ROSTER_SIZE: Final[int] = 10     # active + bench; IL excluded — see D7
MAX_ROSTER_SIZE: Final[int] = 12
```

**Six active slots, not ten.** Every number downstream of this changes, and two consequences are large
enough to call out.

**Eligibility collapses to three classes.** This is not Yahoo's usual
`PG/SG/G/SF/PF/F/C/C/UTIL` layout. There are only three kinds of slot, so a player's eligibility is
one of:

| Slot | Accepts |
|---|---|
| `G` | a player eligible at PG or SG |
| `FC` | a player eligible at SF, PF, or C |
| `UTIL` | anyone |

So the only distinction the assembler needs is guard / forward-centre / both. A dual-eligible player
(a SG-SF, say) belongs to both classes, which is where greedy assignment can misplace someone — see
D4.

**Each active slot is 1/6th of a team's week.** At ten slots a single missing projection is 10% of
production; at six it is **17%**. The coverage thresholds in D5 were written against a ten-slot
assumption and are re-derived there.

League-wide active slots: `18 × 6 = 108`.

---

## D4 — Which rostered players count, and the tiebreak

**Decision**: fill active slots **greedily by each player's projected scalar value, subject to position
eligibility**, iterating slots **narrowest eligibility first** — `G, G, FC, FC, FC, UTIL` — breaking
ties by `(value desc, player_id asc)`.

**Rationale**: this is the design document §4's recommendation, and determinism is what FR-018 and
FR-022 actually require — not optimality. Greedy assignment is *not* guaranteed optimal when position
eligibility is constrained; a player who could fill two slots may be placed in the one that blocks a
better overall assignment. That is accepted and declared rather than hidden, because the alternative
is a matching algorithm whose benefit at 18 teams is marginal and whose behaviour is harder to explain
when someone disputes a rank.

**Slot order is load-bearing, now that D3 is known.** With only three slot classes and `UTIL`
accepting anyone, filling the *constrained* slots before the open one removes most of the blocking
problem: a dual-eligible guard-forward is placed where he is actually needed, and `UTIL` mops up the
best remaining player of either class. Filling `UTIL` first would be strictly worse — it could consume
the best guard and leave a `G` slot unfillable while an eligible forward sits on the bench.

The residual suboptimality is narrow and worth stating precisely: with 2 `G` and 3 `FC`, a team
carrying exactly two guards where one is dual-eligible can still see that player consumed by `FC`
before `G` is filled, if his value ranks him there first. Slots are therefore filled in the declared
order above and **each slot takes the best *eligible* player not yet assigned**, rather than players
being assigned to their best slot — which is what keeps the rule reproducible from the declared order
alone.

**A nuance worth stating, because it looks like a contradiction.** §3 argues at length against a
scalar prior. This decision uses a per-player scalar anyway — but only to *choose contributors*, never
to *score teams*. Team scoring stays category-wise through the all-play grid. The scalar picks who
plays; it never decides who is better.

**Alternatives considered**: summing the whole roster (explicitly forbidden by FR-018 — it credits
bench depth the format cannot deploy); optimal assignment via maximum-weight matching (defensible but
unexplainable to a disputing member, and the declared-rule requirement is satisfied without it).

---

## D5 — Coverage thresholds

**Re-derived after D3 resolved to six active slots, not ten.**

**Decision**: declared in `config.py` —

- `DRAFT_MIN_TEAM_COVERAGE = 0.80` — per team, the fraction of its **six active slots** fillable by a
  projected player. At six slots this permits **one** unfillable slot (5/6 = 0.833 passes, 4/6 = 0.667
  fails), where the original ten-slot reasoning permitted two.
- `DRAFT_MIN_LEAGUE_COVERAGE = 0.95` — across all 108 active slots, so at most five gaps league-wide.

Either floor breached means publish nothing, exit non-zero, notify (FR-026, FR-038).

**What "coverage" counts, precisely.** It is over **active slots fillable**, not over rostered players.
An unprojected player has no scalar value, so slot filling never selects him — he simply isn't a
contributor, and a team with six projected players has full coverage however many unprojected players
sit on its bench or IL. The floor therefore measures the thing that matters: *can this team field a
complete projected lineup?*

This is deliberately a different number from FR-025's unprojected count, which counts **all** rostered
players lacking a projection and exists as a confidence caveat (D6). The two can diverge sharply — a
team with 6 projected starters and 4 unprojected bench players has 100% coverage and an unprojected
count of 4. Conflating them would refuse to publish a perfectly rankable league.

**Rationale for the numbers**: the two floors catch different failures and both are needed. The
per-team floor catches one team being unrankable while the other seventeen are fine — the spec's named
edge case. The league-wide floor catches a systemic source problem spread thinly enough to clear every
per-team check. At six slots one gap is already 17% of a team's projected production, so tolerating two
would mean ranking a team a third of whose week is unknown.

Note the floors can disagree, and that is intended: eighteen teams each missing one slot passes every
per-team check at 0.833 but lands league-wide at 0.833, well under 0.95, and is refused. A gap on every
single team is a source problem, not eighteen coincidences.

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
| **pre-draft** | any team holds fewer than `DRAFT_ROSTER_SIZE` (= 10) players, or no rosters exist |
| **post-draft** | all 18 rosters at 10+ **and** zero scored weeks have completed |
| **in-season** | at least one scored week has completed |

### The roster-size constant must exclude IL, and getting it wrong fails silently

**`DRAFT_ROSTER_SIZE` is 10 — active (6) plus bench (4) — not the 12-slot maximum.** The two IL slots
start **empty** and fill only when someone is actually injured. A healthy, fully drafted league
therefore carries 10 players per team, not 12.

This matters far more than it looks, because of how it interacts with FR-004. Had the completeness
check used `MAX_ROSTER_SIZE = 12`, every team would read as incomplete forever, the run would classify
as **pre-draft**, and pre-draft is the one outcome that publishes nothing, **exits zero, and does not
notify**. The generator would sit there every week reporting success and producing no page, with no
alarm anywhere — the exact silent-failure mode the constitution's "loud and safe rather than silent
and destructive" framing exists to prevent, arrived at through two individually reasonable decisions.

Three guards, because one constant should not be the only thing standing between the project and a
silent year:

1. **The reason string is mandatory, not decorative** (FR-008). "2 of 18 rosters below 10" is
   debuggable; "pre-draft" is not. This is already required and is the first thing to check if no page
   appears.
2. **Assert the constant against reality in a test** — a post-draft fixture built from real roster
   sizes must classify as `POST_DRAFT`. A fixture that classifies as pre-draft when the league has
   plainly drafted is the failure, and it is cheap to catch.
3. **Treat a *persistent* pre-draft classification as suspicious.** Pre-draft is normal in October and
   abnormal in December. Worth a log line noting how long the state has persisted, so a stuck gate is
   visible without a notification that would undo FR-004's intent.

A roster can also legitimately dip below 10 mid-season between a drop and an add. That is `in_season`
rather than pre-draft, because the in-season branch is reached on completed scored weeks and never
re-tests draft completeness — the ordering of the three checks matters, and completeness is only
consulted when no scored week has finished.

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
| `DRAFT_MIN_TEAM_COVERAGE` | `0.80` | D5 — one unfillable slot of six |
| `DRAFT_MIN_LEAGUE_COVERAGE` | `0.95` | D5 — five gaps of 108 |
| `ACTIVE_SLOTS` | `("G","G","FC","FC","FC","UTIL")` | D3 |
| `BENCH_SLOTS` | `4` | D3 |
| `IL_SLOTS` | `2` | D3 |
| `DRAFT_ROSTER_SIZE` | `10` | D3/D7 — active + bench, **excludes IL** |
| `MAX_ROSTER_SIZE` | `12` | D3 |

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
