# Power Rankings Algorithm v1

**Status**: proposed design, not yet implemented
**League format**: 18-team head-to-head 9-category (PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO)
**Declared algorithm version**: `v1` (required by Constitution Principle I)

---

## 1. The problem this has to solve

In an 18-team H2H 9-cat league, **win-loss record is a bad power ranking**. Two reasons, both
made worse by the league size:

1. **You play almost nobody.** Over a ~20-week season you face at most 20 of your 17 possible
   opponents, many only once. Your record is as much a description of your schedule as of your
   team. In a 10-team league you'd face everyone twice; at 18 teams the schedule is wildly
   unbalanced by construction.
2. **A win throws away 8 of the 9 bits.** Going 9-0 and going 5-4 are both "1-0." Record
   discards almost all of the information the week produced.

Standard platform power rankings (CBS uses record + total points + a breakdown of how you'd
have fared against everyone) are built for points leagues and don't exploit category structure.
So v1 is built around **all-play**: compare every team against every other team, every week,
ignoring who they actually played.

### What I rejected, and why

- **Pythagorean expectation.** The basketball exponents in the literature (Morey 13.91,
  Hollinger 16.5) are fit to *real NBA points scored/allowed per game*. Fantasy weekly totals
  have a completely different variance profile — fantasy football's empirically fit exponent is
  ~2.37, an order of magnitude off the NBA figure. Using 13.91 on fantasy scores would make a 3%
  scoring edge look like a near-certain win. There's no reason to go looking for the "right"
  fantasy-basketball exponent either: Pythagorean compresses a season into two scalars, while
  all-play uses the full weekly distribution against every opponent. All-play strictly dominates
  it here.
- **Raw category z-scores summed across cats.** Standard for *player* valuation, wrong for team
  ranking in H2H — see §2, it's the Spread Sam failure.
- **Record-based indices with a points component.** No single "points" scalar exists in a
  category league.

---

## 2. Two all-play metrics, and why the primary one is a step function

### EMW — Expected Matchup Win% (primary)

For each week, replay team *i*'s category totals against **every** other team *j*'s totals for
that same week. Count categories won (ties = 0.5). If *i* takes ≥5 of 9, that's a simulated
matchup win.

- 17 simulated matchups per team per week
- ~340 over a 20-week season, versus ~20 real games

EMW answers exactly the question a power ranking should: **how often would this team beat a
randomly chosen opponent?** It is in win-probability units, so it needs no normalization to be
meaningful.

### CAW — Category All-Play Win% (secondary)

Same replay, but score every category comparison individually instead of collapsing to a
matchup result.

- 9 × 17 = **153 category comparisons per team per week**
- ~3,060 over a season

CAW is far lower-variance than EMW and stabilizes within 2–3 weeks. But it measures average
category strength, which is *not* the objective.

### How a week is actually scored

Scaled down to 4 teams and 3 categories (PTS, REB, TO — **TO inverted, lower wins**) so the
mechanics are visible. One week of totals:

| Team | PTS | REB | TO |
|---|---|---|---|
| A | 500 | 200 | 60 |
| B | 480 | 190 | 50 |
| C | **520** | 150 | 70 |
| D | 400 | **210** | **45** |

**CAW** — score all 3 comparisons per category (3 cats × 3 opponents = 9 per team):

| Team | PTS wins | REB wins | TO wins | Total | CAW |
|---|---|---|---|---|---|
| A | 2 | 2 | 1 | 5/9 | **.556** |
| B | 1 | 1 | 2 | 4/9 | **.444** |
| C | 3 | 0 | 0 | 3/9 | **.333** |
| D | 0 | 3 | 3 | 6/9 | **.667** |

**EMW** — replay each pairing, best 2 of 3 wins the matchup:

| Matchup | PTS | REB | TO | Result |
|---|---|---|---|---|
| A vs B | A | A | B | A wins 2-1 |
| A vs C | C | A | A | A wins 2-1 |
| A vs D | A | D | D | D wins 2-1 |
| B vs C | C | B | B | B wins 2-1 |
| B vs D | B | D | D | D wins 2-1 |
| C vs D | C | D | D | D wins 2-1 |

| Team | Simulated record | EMW |
|---|---|---|
| D | 3-0 | **1.000** |
| A | 2-1 | **.667** |
| B | 1-2 | **.333** |
| C | 0-3 | **.000** |

Note C: best in the league at PTS, and dead last overall. Scale this to 9 cats and 17 opponents
and you get 153 category comparisons and 17 matchup replays per team per week. Ties score 0.5 on
both sides in both metrics.

### Why both — the archetype table

This is the crux. In H2H categories you need 5 of 9, which makes the objective a **threshold**
function. Three teams in an 18-team league:

| Archetype | Category profile | CAW | EMW | Reality |
|---|---|---|---|---|
| **Balanced Betty** | exactly mid-pack in all 9 cats | .500 | ~.500 | Exactly average |
| **Punt Pete** | 2nd of 18 in 6 cats, last in 3 | .627 | **~.90** | Usually wins 6-3 |
| **Spread Sam** | 1st in 4 cats, 17th in 5 | .477 | **≈0** | Usually loses 4-5 |

Pete loses his three punted categories to *everyone*, so he needs five of his remaining six.
Against mid-pack-or-worse opponents he takes all six and wins 6-3; against the several teams who
are also strong in two or three of those six he can slip to 4-5. Hence ~.85–.95, not 1.000.

Sam's five weak categories are 17th of 18, so in each he beats exactly one team — but a
*different* team in each category. He wins a matchup only when a single opponent happens to sit
below him in two of those five at once. Rare, hence ≈0.

Spread Sam has a CAW near average and an EMW near zero. Any ranking built on summed category
strength puts Sam mid-pack; Sam is in fact the worst team in the league *for this format*.
Meanwhile Punt Pete — a deliberate punt build, which is a legitimate and strong strategy at
18 teams — is correctly rated as dominant.

**Therefore EMW is the headline number.** CAW enters only as a variance reducer: it's an estimate
of the same underlying strength with ~18× the sample, which matters a lot in weeks 1–6.

```
Performance = 0.65 · EMW + 0.35 · CAW        (both recency-weighted, both in win% units)
```

The 0.65/0.35 split is a judgment call, not a fitted constant — it leans on the objective while
borrowing enough from CAW to keep early-season rankings from thrashing. Worth revisiting with a
season of archived data.

---

## 3. The full v1 formula

Everything stays in **win-probability-against-a-random-opponent units** (0 to 1), so the final
score is directly interpretable rather than an arbitrary index.

```
PowerScore(i) = w · Performance(i) + (1 - w) · RosterPrior(i)

where
  w                = n / (n + 3)                     n = completed weeks
  Performance(i)   = 0.65 · EMW_rw(i) + 0.35 · CAW_rw(i)
  EMW_rw, CAW_rw   = recency-weighted, half-life 4 weeks
  RosterPrior(i)   = projected roster strength, mapped to a win% scale (§4)
```

**Recency weighting.** Week *w* of *n* gets weight `0.5 ^ ((n - w) / 4)`. Rosters churn through
injuries, waivers, and trades, so a team's week-2 performance shouldn't anchor its week-18
ranking. Half-life 4 weeks ≈ the most recent month carries ~75% of the weight.

**Shrinkage.** `w = n/(n+3)` ramps from pure roster projection at week 0 to ~87% realized
performance by week 20. The k=3 constant means realized play overtakes the prior partway
through week 3. This mirrors the pattern the fantasy football sources converged on: weight
roster strength early, let season-long performance take over as it accumulates.

| Completed weeks | Weight on performance |
|---|---|
| 0 | 0% (pure projection) |
| 2 | 40% |
| 4 | 57% |
| 8 | 73% |
| 20 | 87% |

Internally, keep the score as a `.624`-style win%. Do **not** rescale to a 0–100 index — it would
discard the one property that makes the number interpretable *to the maintainer*.

**The score is never published.** Per spec FR-032, the page shows rank and rank movement only.
The win% lives in the archived internal report, where it exists for debugging and for the
before/after comparisons the constitution requires when the algorithm changes.

---

## 4. Cold start: the league hasn't drafted yet

At week 0 there is no performance data at all, so `w = 0` and the ranking *is* `RosterPrior`.

`RosterPrior` = sum of per-game 9-cat z-score values for rostered players, weighted by projected
games played, then mapped across the league to a 0–1 scale. This requires an external
player-projection source and is the only part of v1 with a data dependency beyond the league
itself.

Two honesty requirements:

- Week 0 MUST be labeled on the page as a **draft-based projection**, not a power ranking.
  Week 1 has real results, so it is a ranking — labeled **provisional**, never a projection.
- If no projection source is available, publish **no ranking** until week 2 and show standings
  only. A confidently wrong week-0 ranking is worse for a casual audience than an absent one.

`RosterPrior` keeps earning its place after week 0 — it's the only forward-looking component,
so it's what reacts when a team loses a star to injury or wins a lopsided trade.

---

## 5. Derived insights — computed internally, published only as prose

> **Revised 2026-10-18.** An earlier draft of this section required publishing each team's
> component metrics so readers could audit a ranking. That is superseded by the strict
> disclosure decision in spec FR-032–034: **no number derived from the ranking computation is
> published except rank and rank movement.** The insights below are still computed — they're
> what give the article something true to say — but they reach the page as narrative, not as
> figures.

These fall out of the same computation for free, and in an 18-team league they'll be dramatic:

| Insight | Computed as | Published as |
|---|---|---|
| **Schedule luck** | `actual win% − EMW` | Prose only: "the league's easiest run of opponents so far." Never the figure — it would expose EMW directly. |
| **Category profile** | 9 per-category all-play win rates | Prose only: "quietly dominant on the glass, giving away threes every week." |
| **Best/worst in league** per category | rank within each category | Prose only, and safe to name — it's a league-data fact, not a ranking output. |
| **Trend** | change in rank over 2 weeks | **Publishable as a number** — rank movement is explicitly permitted. |
| **Unluckiest week** | largest category haul that still lost | Prose, plus the underlying category tally, which is league data. |

### Explainability, under strict disclosure

The audience reads this casually on a phone and *will* argue with it, and a black-box ranking
invites "this is rigged" — a church league is the wrong venue for that. Strict disclosure means
that tension is resolved **in the prose rather than in a table**: the article must give each
significant mover a concrete, factual reason drawn from the week's events, so a reader gets a
"why" without any component of the method being exposed. See spec SC-008.

The full decomposition still exists in the archived internal report. It's available to the
maintainer for settling a dispute; it just isn't on the page.

---

## 6. Data requirements → feeds `TODO(DATA_SOURCE)`

This algorithm imposes hard constraints on the data-source decision. Deciding the provider
*before* checking these would be a mistake.

1. **Per-team, per-week, per-category totals for all 18 teams — not just your own matchups.**
   All-play is impossible without the full grid. This is the single most likely thing a provider
   won't expose cleanly.
2. **FG% and FT% as makes and attempts, never as percentages.** A percentage cannot be
   re-aggregated across a week or compared at the right granularity once it's been rounded.
   Store `fgm/fga` and `ftm/fta`.
3. **Weekly period boundaries**, matching how the platform defines a matchup week.
4. **The actual schedule**, to compute real record and therefore luck.
5. **Current rosters**, for `RosterPrior`.
6. **Player projections** (external), for `RosterPrior` only.

**Mid-season backfill is likely impossible.** If the generator starts after the season is
underway and the provider has no historical weekly category endpoint, all-play cannot be
reconstructed — and Constitution Principle III's archive only begins the day the job first runs.
Since the league hasn't drafted yet, this is avoidable: **start archiving from week 1**, even
before the page is ready to publish.

---

## 7. Determinism and edge cases → Constitution Principle I

Principle I requires the ranking module to be a pure function of the snapshot with no I/O. Each
of these needs a single documented answer, because each is a place where output could vary run
to run:

- **Ties in a category comparison**: 0.5 to each side. Never host-order dependent.
- **Ties in PowerScore**: stable sort by `(PowerScore desc, team_id asc)`. Never by dict order.
- **Zero attempts in a ratio category** (a team with 0 FTA for the week): define explicitly —
  recommend treating it as a loss against any team with ≥1 attempt and a tie against another
  team with 0. Document it; don't let it fall out of a division-by-zero guard.
- **Floating point**: round only at the display boundary, never mid-computation, or the
  golden-file test from the constitution's quality gates will flake.
- **Constants** (`0.65`, `0.35`, `k=3`, `half-life=4`) MUST live in one declared module-level
  config, not scattered as literals. Changing any of them bumps the algorithm version and
  triggers the before/after comparison the constitution requires.
- **Unplayed / bye weeks**: excluded from all-play, not counted as zeros.

---

## 8. Changing the algorithm

Constitution Principle I requires that changing the rankings algorithm bump its declared version
and arrive with a before/after comparison on archived data. Concretely:

1. **Edit `src/ccsv_rumble/config.py`.** Every constant that affects the score lives there and
   nowhere else — `EMW_WEIGHT`, `CAW_WEIGHT`, `SHRINKAGE_K`, `RECENCY_HALF_LIFE_WEEKS`,
   `SIGNIFICANT_RANK_CHANGE`, the standout thresholds. A constant written as a literal elsewhere
   is a bug.
2. **Bump `ALGORITHM_VERSION`** in the same commit. The version is recorded in every archived
   internal report and emitted into each page's provenance comment, so a past ranking can always
   be traced to the rules that produced it.
3. **Replay the archived weeks under both sets of constants** and diff the resulting ranks:

   ```bash
   git stash                                         # old constants
   for w in $(seq 1 "$LAST_WEEK"); do uv run ccsv-rumble replay --week "$w" --out /tmp/before; done
   git stash pop                                     # new constants
   for w in $(seq 1 "$LAST_WEEK"); do uv run ccsv-rumble replay --week "$w" --out /tmp/after; done
   diff -r /tmp/before /tmp/after
   ```

4. **Attach the rank comparison to the PR.** A change that moves nobody is as informative as one
   that reshuffles the table — both tell you whether the constant was doing anything.
5. **Update the golden file** (`tests/golden/week-01.html`) and review the diff deliberately. An
   unexplained rendering diff blocks merge.

The constitution's versioning policy governs *this document and the constants*; it is independent
of the constitution's own version number.

---

## 9. Deliberately out of v1

- **Strength of remaining schedule / playoff odds.** Valuable, but needs a forward simulation —
  v2.
- **Games-played bias.** At 18 teams the waiver wire is thin, and aggressive streaming inflates
  counting categories while hurting FG%/FT%. v1 does **not** correct for this, because it
  genuinely wins matchups — it's strategy, not noise. Revisit only if the league adds a
  games-played cap.
- **Opponent-adjusted all-play.** All-play intentionally ignores who you played; that's the
  feature.
- **Head-to-head record as a component.** Deliberately absent. It's the noise this design exists
  to remove.

---

## Sources

- [How are the Power Rankings on the Standings page determined? — CBS Sports](https://help.freefantasyleagues.cbssports.com/s/article/How-are-the-Power-Rankings-on-the-Standings-page-determined) — record + points + all-play "breakdown"
- [How to Calculate Fantasy Football Power Rankings (With Example) — ffwrapped](https://blog.ffwrapped.com/posts/fantasy-football-power-rankings) — worked composite formula and its stated limitations
- [How to Get Power Rankings for Your ESPN Fantasy Football League — ffwrapped](https://blog.ffwrapped.com/posts/espn-power-rankings) — all-play definition, tie handling, z-score Power Index, schedule luck as actual − expected wins
- [Pythagorean expectation — Wikipedia](https://en.wikipedia.org/wiki/Pythagorean_expectation) — Morey 13.91 / Hollinger 16.5 exponents; basis for rejecting the approach
- [Fantasy basketball — Wikipedia](https://en.wikipedia.org/wiki/Fantasy_basketball) — category and roto scoring structure
- [Head-to-Head scoring in Yahoo Fantasy](https://help.yahoo.com/kb/SLN6212.html) — 9-cat matchup mechanics and tiebreakers
- [Fantasy basketball: pros and cons of points, roto and category leagues — ESPN](https://www.espn.com/fantasy/basketball/story/_/id/38604409/fantasy-basketball-pros-cons-points-roto-category-leagues-nba-2026-27) — format tradeoffs
- [Fantasy Basketball Draft Guide 2026: H2H Strategy — SportsEthos](https://sportsethos.com/top-posts/fantasy-basketball-draft-guide-2026-h2h-strategy/) — punt-build viability in H2H categories
- [Dribble Grid](https://www.dribblegrid.com/) / [Hashtag Basketball](https://hashtagbasketball.com/fantasy-basketball-rankings) — 9-cat player z-score valuation, candidate `RosterPrior` inputs
