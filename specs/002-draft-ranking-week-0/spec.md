# Feature Specification: Draft Ranking (Week 0)

**Feature Branch**: `main` (no feature branch created — no `before_specify` git hook is registered)

**Created**: 2026-10-20

**Status**: **US1, US3 and US4 implemented and reachable from the scheduled job**
(78 of 90 tasks; 309 tests green). Only US2 — the draft recap — remains, blocked on
draft-results acquisition under `004`.

The roster gap found during implementation is **closed**: rosters are now acquired from
`data/rosters.csv`, captured with `tools/yahoo_roster_capture.js` (research D12), and
`build_plan` targets week 0 before any week completes. The week-0 page therefore publishes
through the weekly run rather than only via `--week 0`, which is what SC-001 actually asks.

**Planned, no open questions.** See [`plan.md`](plan.md),
[`research.md`](research.md), [`data-model.md`](data-model.md), [`contracts/`](contracts/),
[`quickstart.md`](quickstart.md).

Roster configuration supplied 2026-10-22: `2G, 3FC, 1 Util, 4 B, 2 IL` — six active slots, four
bench, two injured-list, so a draft fills 10 of 12 roster spots (research D3, D7).

**Input**: User description: "create a spec that implements draft raking algorithm for week 0"

**Design document**: [`docs/draft-rankings-algorithm-v1.md`](../../docs/draft-rankings-algorithm-v1.md) (declared version `draft-v1`)

**Depends on**: [`001-power-ranking-article`](../001-power-ranking-article/spec.md) — this feature adds a
ranking source and two acquisition stages to that pipeline; it does not replace its report, rendering,
validation, or publish stages.

## Clarifications

### Session 2026-10-20

- Q: Is a week-0 page published publicly, or is the draft ranking computed only to feed the in-season
  prior? → A: **Publish the week-0 page** — all 18 teams ordered, labeled as projection-based, with
  rank movement shown as unavailable because no previous ranking exists.
- Q: If a week-0 page is published, does it carry a generated write-up? → A: **A league-wide draft
  recap article** — a narrative covering the draft itself alongside the rankings table, rather than a
  static explainer or per-team blurbs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - League member sees where their team stands right after the draft (Priority: P1)

A member opens the page in the window between the draft finishing and the first games being scored.
They see all 18 teams ordered, and a plain statement that this is based on draft projections rather
than games played.

**Why this priority**: This is the feature in its minimum form. It is also the moment the page has the
largest audience it will get all season — the day after a draft is when people most want to argue
about their team — and currently the page has nothing to show until a week of games has been scored.
The ranking table is the durable value; the recap in User Story 2 is commentary layered on top.

**Independent Test**: Run the generator against a post-draft snapshot with no completed scored weeks
and confirm the page shows a complete 18-team ordering, carries the projection-based label, and
contains no figure originating from the ranking computation — with no article present and no language
model involved at any point.

**Acceptance Scenarios**:

1. **Given** a snapshot with all 18 rosters filled and no completed scored week, **When** a run
   executes, **Then** the page shows all 18 teams in rank order.
2. **Given** that same snapshot, **When** the page is rendered, **Then** rank movement is shown as
   unavailable rather than as zero, because no previous ranking exists.
3. **Given** that same snapshot, **When** the page is rendered, **Then** it states that the ranking
   reflects draft projections rather than played games, without describing the method.
4. **Given** a run in which article generation fails, **When** the page is published, **Then** the
   ranking table is still present and complete.

---

### User Story 2 - League member reads the draft recap (Priority: P2)

A member reads a single league-wide article published with the week-0 rankings. It covers how the
draft actually went — notable picks, runs on a position, who walked away with the deepest roster —
and reads as commentary on the draft, not as an explanation of a ranking formula.

**Why this priority**: This is what makes the week-0 page worth opening rather than glancing at, on
the highest-traffic day of the season. It is deliberately second because the page is viable without
it: if the article never ships, or fails on a given run, the rankings table still publishes.

**Independent Test**: Generate the article from an archived week-0 internal report plus draft results,
and confirm it references concrete draft facts, names no forbidden method vocabulary, and passes the
tone screen — testable without publishing anything.

**Acceptance Scenarios**:

1. **Given** a week-0 internal report and the archived draft results, **When** the article is
   generated, **Then** it is a single league-wide piece rather than one article per team.
2. **Given** a generated article, **When** it is screened, **Then** it contains no term that would
   disclose the ranking method and no disparaging language directed at an identifiable member.
3. **Given** an already-generated and archived article, **When** the run is repeated, **Then** the
   archived article is replayed and no new model call is made.
4. **Given** article generation that fails or produces output failing a screen, **When** the run
   continues, **Then** the page publishes with the ranking table and no article section, and the
   maintainer is notified.

---

### User Story 3 - Rankings react to roster changes all season (Priority: P3)

A member loses a star player to a long-term injury, or wins a lopsided trade. The next published
ranking reflects that, rather than waiting several weeks for played results to accumulate.

**Why this priority**: The roster-based prior is the only forward-looking term in the in-season
ranking. Without it the ranking is purely backward-looking and cannot respond to a roster that has
materially changed. Valuable, but the league survives a week without it.

**Independent Test**: Take two snapshots of the same league week differing only in one team's roster
(a star removed), compute the ranking for each, and confirm the affected team's rank responds in the
expected direction while no other input has changed.

**Acceptance Scenarios**:

1. **Given** two otherwise identical in-season snapshots differing only by one team losing its
   highest-projected player, **When** both are ranked, **Then** that team ranks no higher in the
   second than in the first.
2. **Given** an in-season run, **When** the ranking is computed, **Then** the roster-based prior is
   recomputed from current rosters rather than reused from the draft.

---

### User Story 4 - Maintainer reproduces a past draft ranking (Priority: P4)

A member disputes a ranking weeks later. The maintainer re-runs that day's inputs offline and gets the
identical ordering, and can see the full decomposition in the internal report.

**Why this priority**: Required by Constitution Principles I and III, and the reason disputes end in a
disagreement rather than a loss of trust. It is a maintainer capability, not a member-facing one.

**Independent Test**: Replay an archived post-draft snapshot with no network access and confirm the
ordering and rendered page match what was originally published.

**Acceptance Scenarios**:

1. **Given** archived projection, roster, and draft-result snapshots, **When** the ranking is replayed
   offline, **Then** the ordering is identical to the one originally published.
2. **Given** a projection source that has since revised its numbers, **When** a past ranking is
   replayed, **Then** the archived snapshot is used and the result does not change.

---

### Edge Cases

- **The league has not drafted.** No rosters exist, so no ranking is computable. The run must publish
  nothing and still be considered successful — an undrafted league is a normal state, not a failure.
- **The draft is partially complete** (some teams short, or a draft in progress). Ranking a half-built
  league would be actively misleading.
- **A rostered player has no projection** — an undrafted free agent, a two-way contract, a rookie the
  source does not cover, or a name that fails to match.
- **Most of a team's roster has no projection**, making its ranking meaningless while the other 17 are
  fine.
- **A player is projected for zero games** in the scored week.
- **A team is projected for zero attempts** in a ratio category.
- **The projection source publishes percentages only**, with no makes and attempts.
- **The projection source is unreachable**, rate-limits, or returns malformed data.
- **The projection source revises its numbers** between the draft and the first scored week, or after
  a page has already been published.
- **Two teams tie** on the computed score.
- **The season has already started when the generator first runs**, so there is no true week 0.
- **A roster changes between the draft and the first scored week** (immediate waiver activity).
- **Draft results are unavailable or incomplete** while rosters are known — the ranking is computable
  but the recap has no pick-by-pick material to work from.
- **The recap's most interesting observation is unkind.** The genuinely funny draft story is often
  someone's mistake, and the audience is a congregation that includes that person.
- **The recap would be more accurate if it explained the ranking**, which strict disclosure forbids.

## Requirements *(mandatory)*

### Functional Requirements

**Part 1 — Lifecycle and eligibility**

- **FR-001**: System MUST compute the draft ranking using the algorithm declared in
  `docs/draft-rankings-algorithm-v1.md`, recording that algorithm's declared version alongside the
  results, separately from and in addition to the in-season algorithm version.
- **FR-002**: System MUST determine which lifecycle state the league is in for every run:
  **pre-draft** (rosters do not exist or are incomplete), **post-draft** (rosters complete, no scored
  week finished), or **in-season** (at least one scored week finished).
- **FR-003**: In the pre-draft state the system MUST NOT publish any ranking, and MUST NOT publish a
  page containing an empty or placeholder ranking section.
- **FR-004**: In the pre-draft state the run MUST complete successfully and exit zero. An undrafted
  league MUST NOT be reported as a failure, and MUST NOT trigger a failure notification.
- **FR-005**: In the post-draft state the system MUST rank all 18 teams.
- **FR-006**: System MUST record rank movement as unavailable rather than zero for the first published
  ranking of a season, consistent with `001` FR-005.
- **FR-007**: Once at least one scored week has completed, the headline ranking MUST come from the
  in-season algorithm, and the draft ranking MUST continue only in the role defined in Part 5.
- **FR-008**: System MUST treat an incomplete draft as pre-draft for publication purposes, and MUST
  record why publication was withheld.

**Part 2 — Projection acquisition and archiving**

- **FR-009**: System MUST acquire per-player, per-game projections covering all nine scoring
  categories from an external source.
- **FR-010**: System MUST require ratio categories as **makes and attempts**. A source that supplies
  only percentages MUST be rejected at ingest with an explicit error, rather than having makes and
  attempts inferred, derived, or defaulted.
- **FR-011**: System MUST archive each projection snapshot immutably before using it, and MUST record
  the source identity and retrieval time with it.
- **FR-012**: The archived projection snapshot MUST be sufficient to recompute that run's ranking
  offline with no network access.
- **FR-013**: System MUST NOT retroactively alter an already-published ranking when the projection
  source revises its numbers. Corrections apply forward only, consistent with `001`'s correction rule.
- **FR-014**: Projection acquisition MUST set an explicit timeout and MUST NOT retry indefinitely.
  Exhausted retries are a publication failure, not a reason to proceed with partial data.
- **FR-015**: Projection acquisition MUST comply with the source's terms of use, and MUST be isolated
  behind the same kind of interface as league data so the source can be replaced without touching
  ranking or rendering.

**Part 3 — Computation**

- **FR-016**: System MUST build each team's projected category totals for the scored week from
  per-player per-game projections and the number of games each player's real-world team plays in that
  week.
- **FR-017**: System MUST use the real schedule for the week in question rather than a league-average
  games-per-week constant.
- **FR-018**: System MUST respect the league's active roster slot limits when assembling projected
  totals, selecting contributors by a declared, documented, deterministic rule. System MUST NOT sum
  the entire roster, which would credit bench depth the format cannot deploy in a week.
- **FR-019**: System MUST score projected totals using the **same** all-play comparison the in-season
  algorithm uses, reusing its declared category weights. A second scoring function MUST NOT be
  introduced.
- **FR-020**: System MUST shrink the resulting score toward even odds by a declared, documented
  constant, so a projection cannot assert certainty.
- **FR-021**: The computation MUST be a pure function of its input snapshot, performing no network and
  no filesystem access.
- **FR-022**: System MUST break ties deterministically and document the rule, so identical inputs
  always yield identical ordering.
- **FR-023**: Players projected for zero games in the scored week MUST be excluded from projected
  totals rather than contributing zeros.
- **FR-024**: Unfilled roster slots MUST contribute nothing, and MUST NOT be imputed from league
  averages or replacement-level estimates.
- **FR-025**: A rostered player with no available projection MUST NOT be silently dropped. System MUST
  count unprojected players per team and carry that count into the internal report.
- **FR-026**: System MUST refuse to publish when projection coverage falls below a declared,
  documented threshold — either league-wide or for any single team — because a ranking computed from
  mostly-missing inputs is a broken page, not a degraded one.
- **FR-027**: A team projected for zero attempts in a ratio category MUST be handled by the rule
  already declared for that case in the in-season algorithm, not by a new one.

**Part 4 — Disclosure and publication**

- **FR-028**: The published page MUST show only **rank** and **rank movement** as numbers originating
  from the draft ranking computation, consistent with `001` FR-032–034.
- **FR-029**: The computed score, its components, and the shrink constant MUST NOT appear on the page
  in any form — not as figures, not rounded, not in alt text, tooltips, data attributes, or markup
  comments.
- **FR-030**: The page MUST state that the ranking reflects draft projections rather than played
  games, and MUST NOT describe the mechanism by which projections give way to results.
- **FR-031**: Published prose MUST pass the existing disclosure-term screen. Any new draft-specific
  vocabulary MUST be screened before it can reach the page.
- **FR-032**: A team's standing **within a category** MAY be published as prose or as a league-data
  fact. A per-category rate produced by the ranking computation MUST NOT be published.
- **FR-033**: The declared draft algorithm version MUST be recorded in the archived internal report
  and emitted into the page's provenance comment.
- **FR-034**: The internal report MUST retain the full decomposition — projected totals, component
  scores, unprojected counts — so the maintainer can settle a dispute without it being on the page.

**Part 5 — Continuing in-season role**

- **FR-035**: System MUST recompute the roster-based prior from **current** rosters on every in-season
  run, so it reflects injuries, trades, and waiver activity since the draft.
- **FR-036**: The in-season ranking MUST consume that prior as its forward-looking term, using the
  blend already declared by the in-season algorithm.
- **FR-037**: A change to the draft algorithm MUST bump its declared version and MUST arrive with a
  before/after rank comparison over archived weeks — because this algorithm affects in-season
  published ranks, not only the week-0 page.

**Part 6 — Failure behaviour**

- **FR-038**: If projections cannot be acquired, or coverage is below threshold, the system MUST
  publish nothing, leave the previously published page untouched, exit non-zero, and notify through
  the configured channel.
- **FR-039**: Publication MUST remain all-or-nothing. A run MUST NOT publish a ranking section without
  the rest of the page, or a page whose ranking covers fewer than 18 teams.
- **FR-040**: A run that produces output identical to what is already published MUST NOT create a
  commit in the publish repository.

**Part 7 — Draft recap article**

- **FR-041**: System MUST generate exactly one league-wide draft recap article for the week-0 page,
  covering the draft and the resulting rankings, rather than one article per team.
- **FR-042**: System MUST acquire the draft results — pick order, acquiring team, and player for every
  selection — and MUST archive them immutably as an input.
- **FR-043**: The article MUST be derived solely from the week-0 internal report and the archived draft
  results. The report MUST be fully determined before any prose is generated, consistent with `001`'s
  report-before-article rule.
- **FR-044**: Article generation MUST be treated as an acquisition stage, not a rendering stage:
  generated once, archived immutably, and replayed from the archive on subsequent runs. A repeated run
  MUST NOT issue a new model call. This is what keeps rendering deterministic under Constitution
  v2.0.0 Principle I.
- **FR-045**: The article MUST NOT disclose the ranking method, and MUST pass the disclosure-term
  screen required by FR-031 before publication.
- **FR-046**: The article MUST pass a tone screen and MUST NOT disparage or ridicule an identifiable
  member. Light humour directed at picks and rosters is permitted; humour directed at a person's
  competence or character is not.
- **FR-047**: The article MAY name players, picks, and draft positions, which are league data. It MUST
  NOT publish any rate or score produced by the ranking computation, per FR-032.
- **FR-048**: If article generation fails, or its output fails any screen, the page MUST still publish
  with the complete ranking table and MUST omit the article section entirely — no placeholder and no
  explanation — consistent with `001` FR-030a. The run MUST notify the maintainer, because the page
  itself will be silent about the omission.
- **FR-049**: If draft results are unavailable or incomplete, the system MUST still publish the
  ranking and MUST omit the article rather than generating a recap from rosters alone.

### Key Entities

- **Player Projection**: one player's expected per-game production across the nine categories, with
  ratio categories carried as makes and attempts. Sourced externally; never computed here.
- **Projection Snapshot**: the complete set of player projections as retrieved at a point in time,
  archived immutably with its source identity and retrieval time. The input that makes a past draft
  ranking reproducible.
- **Draft Results**: the ordered record of every selection — pick number, acquiring team, player.
  League data, archived immutably, and the raw material for the recap.
- **Projected Team Week**: one team's projected nine-category totals for a specific scored week,
  derived from its roster, the projections, and the real schedule. The direct analog of an observed
  team week, which is what lets the existing comparison logic be reused unchanged.
- **Draft Ranking Entry**: a team's rank, its computed score, its component scores, and its
  unprojected-player count. Only rank leaves the internal report.
- **Roster-Based Prior**: the same computed score in its in-season role as the forward-looking term of
  the published ranking.
- **Draft Recap Article**: the generated league-wide narrative for the week-0 page, archived as
  acquired output and replayed thereafter.
- **League Lifecycle State**: which of pre-draft, post-draft, or in-season a run is operating in —
  the switch that decides whether a ranking is computable and publishable at all.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the first run after the draft completes, the page shows all 18 teams in rank order.
- **SC-002**: Across every run executed before the draft completes, zero pages containing a ranking
  are published.
- **SC-003**: Replaying any archived post-draft snapshot offline reproduces the published page
  byte-identically.
- **SC-004**: No number traceable to the ranking computation, other than rank and rank movement,
  appears anywhere in the published output — verified on every run by the existing validation gate.
- **SC-005**: The draft recap references at least one concrete, verifiable draft fact — a specific
  pick, team, or player — for a majority of the 18 teams.
- **SC-006**: Every rostered player is either projected or counted as unprojected; no rostered player
  is unaccounted for in the internal report.
- **SC-007**: When projections are unavailable or coverage is below threshold, no page is published,
  the previous page remains live, and the maintainer is notified — in 100% of such runs.
- **SC-008**: When article generation fails, the page still publishes with complete rankings, in 100%
  of such runs.
- **SC-009**: A ranking published at week 0 and the roster-based prior used in week 5 are produced by
  the same declared algorithm version, verifiable from the archive.
- **SC-010**: A maintainer can explain any individual team's week-0 placement from the internal report
  alone, without re-running the generator.
- **SC-011**: Zero published articles contain language that disparages an identifiable member.

## Assumptions

- **Week 0 is published, not merely computed** (resolved 2026-10-20). The alternative considered and
  rejected was computing the draft ranking only as the in-season prior, which would have followed
  `docs/rankings-algorithm-v1.md` §4's argument that an absent ranking beats a confidently wrong one.
  The decision accepts a projection-based public ranking provided it is labeled as such.
- **A 1–18 ordering, not tiers.** The design document weighs tiers against an ordering and recommends
  the ordering, on the grounds that strict disclosure already hides the score, so the only false
  precision a reader can see is the ordering itself. This also keeps one rendering path rather than a
  presentation that appears once a season.
- **The week-0 article is a draft recap** (resolved 2026-10-20), covering the draft itself rather than
  explaining rank movement — which does not exist at week 0 anyway. This is the largest of the three
  options considered, and it reuses `001`'s article stage against a new input type.
- **An external projection source exists, is permitted for this use, and supplies makes and
  attempts.** This is the only data dependency in the project that reaches outside the league, and
  FR-010 makes the makes-and-attempts question a go/no-go on the source rather than a detail. If no
  compliant source exists, this feature cannot ship as specified and the fallback is to publish no
  ranking until the in-season algorithm has data.
- **Draft results are available from the league provider** as a pick-by-pick record. FR-049 covers the
  case where they are not.
- **Projected games come from the real-world schedule**, which is deterministic and already needed to
  define week boundaries.
- **The shrink constant is a judgment call, not a fitted value.** It is declared, documented, and
  expected to be refit from the archive after one season. Choosing its initial value is a planning
  decision.
- **The draft ranking carries its own declared version**, independent of the in-season algorithm
  version, while deliberately sharing the in-season scoring function and category weights.
- **The league drafts once per season.** Mid-season redrafts, keeper carryover, and dynasty valuation
  are out of scope.
- **Constitution v2.0.0 applies**, including the weekly cadence and the amended Principle I under
  which an archived, replayed acquisition stage is permitted. Both projection acquisition and article
  generation are such stages.
- **Roster slot configuration is available from the league provider**, which FR-018 depends on.
- **This feature reuses `001`'s archive, report, rendering, validation, publish, notification, and
  article stages.** It adds two acquisition inputs — projections and draft results — and a ranking
  source. It does not introduce a second pipeline.
- **Model choice, prompt design, and the recap's structure are planning decisions**, deliberately
  unspecified here.
