# Draft Rankings Algorithm v1

**Status**: implemented for week 0 (spec `002`); see Open questions for what remains
**League format**: 18-team head-to-head 9-category (PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO)
**Declared algorithm version**: `draft-v1` (required by Constitution Principle I)
**Companion**: [`rankings-algorithm-v1.md`](./rankings-algorithm-v1.md), declared version `v1`

---

## 1. Scope

This document covers the ranking published **between draft completion and the first scored week** —
"week 0" — and the continuing life of that same number as the `RosterPrior` term inside `PowerScore`
for the rest of the season.

**Not in scope: pre-draft.** Before the draft there are no rosters, so this algorithm has no input.
Its output is not uncertain, it is *undefined*. See §6.

**This is not a player draft ranking.** "Draft rankings" in fantasy basketball normally means a
ranked list of players to pick — what Hashtag Basketball and Dribble Grid publish. This document
ranks the league's **18 teams** based on the rosters they came out of the draft with. It consumes
player valuations; it does not produce them.

---

## 2. Why this is a separate algorithm

Three reasons, none of which is "the math is different" — see §3.

1. **Different inputs.** `v1` consumes observed per-week category totals. `draft-v1` consumes rosters
   plus external player projections, and has no observed totals at all. The data dependency in §5 is
   the only one in the entire project that reaches outside the league itself.
2. **Independent versioning.** Refitting the projection source, changing the shrink constant, or
   altering how projected weekly totals are assembled should not bump the in-season algorithm version
   and should not force a before/after comparison on in-season output. Two declared versions let each
   move on its own cadence. See §8 for the coupling that remains.
3. **Different honesty obligations.** `v1` reports what happened. `draft-v1` reports a forecast, and
   Constitution Principle I's reproducibility promise is a much weaker claim when the inputs are
   somebody else's projections. The publication rules in §6 exist only for this algorithm.

---

## 3. What it deliberately shares: the all-play core

**The scoring function is identical to `v1`'s.** `draft-v1` builds each team's *projected* weekly
9-category totals, then runs the same all-play grid over them — 17 simulated matchups and 153
category comparisons per team, same tie rules, same threshold at 5 of 9.

This is the whole design, and the reason is `v1` §2's archetype table. **A prior built from summed
9-cat z-scores is the Spread Sam failure.** A team that drafts 1st-in-four-categories and
17th-in-five has a perfectly respectable z-score sum and an EMW near zero. Rank that team by summed
z-scores at week 0 and it lands mid-pack; then `w = n/(n+3)` ramps and it craters. To eighteen people
reading on their phones, that is indistinguishable from the algorithm being broken — when in fact
only the prior was wrong.

Running the prior through all-play makes the two algorithms agree about what "good" means in this
format. A punt build is correctly rated as strong on draft night, not as a mid-pack team that
mysteriously becomes strong in December.

A second benefit: **units.** `v1` §3 insists everything stays in win-probability-against-a-random-
opponent units. A z-score sum "mapped across the league to a 0–1 scale" is not that — a percentile
map puts the best team at exactly `1.000`, where real EMW tops out near `.90` even for a dominant
punt build. Blending a uniform 0–1 prior against a clustered EMW once `w > 0` would systematically
exaggerate both extremes for the first month. Shared machinery means the blend in `v1` §3 is adding
two quantities that actually mean the same thing.

Third: the **category profile** (`v1` §5) works at week 0 for free, because the projected grid has
the same shape as the observed one. Punt builds are visible straight off the draft board. This is the
most interesting thing the week-0 page will have to say, and it only exists if the prior is computed
category-wise rather than as a scalar — a summed-z-score prior has nothing to decompose. Per `v1` §5
it reaches the page as prose, never as figures; see §6.

### Pipeline

```
post-draft rosters
  + per-player per-game 9-cat projections
  + projected games played for the scored week
      ↓
projected weekly category totals per team      (18 × 9 grid)
      ↓
the v1 all-play grid, unchanged                 (EMW_proj, CAW_proj)
      ↓
shrink toward .500                              (§4)
      ↓
DraftScore ∈ (0, 1), same units as PowerScore
```

---

## 4. The formula

```
DraftScore(i) = 0.5 + s · ( AllPlay_proj(i) − 0.5 )

where
  AllPlay_proj(i) = 0.65 · EMW_proj(i) + 0.35 · CAW_proj(i)     (weights reused from v1 §3)
  s               = shrink constant, recommend 0.6
```

`RosterPrior(i)` in `v1` §3 **is** `DraftScore(i)`, recomputed from the current roster snapshot. No
separate mapping step, and no second definition of roster strength anywhere in the codebase.

### Why shrink at all

All-play over *point* projections is overconfident, and the cause is the same threshold nonlinearity
that motivates EMW in the first place. A team projected to edge five categories by a hair wins every
simulated matchup and scores `1.000` — a claim no honest forecast can make. Because `w = 0` at week
0, nothing else in the system damps it. `EMW(E[totals]) ≠ E[EMW(totals)]`, and the gap is widest
exactly at the threshold.

### Why a constant rather than a simulation

The principled fix is Monte Carlo: draw weekly totals around each projection using per-category
week-to-week variance, run all-play per draw, average. The problem is that at week 0 **there is no
variance to draw from.** Any coefficient of variation used in year one would be invented, and `v1`
§7 makes every such number a declared config constant whose change bumps the algorithm version — so
it would be a fabricated constant that immediately wants refitting.

One shrink constant is the honest version of the same correction. It sits in the same register as
`v1`'s own 0.65/0.35, which that doc openly calls "a judgment call, not a fitted constant."

Worked reference for `s = 0.6`. Take `v1` §2's Punt Pete — a strong *real* team at `EMW ≈ .90`,
`CAW = .627`, so `AllPlay = 0.65(.90) + 0.35(.627) = .804`. Now take a team whose **point
projections** sweep five categories against all 17 opponents: `EMW_proj = 1.000`, and with
`CAW_proj ≈ .70` that is `AllPlay_proj ≈ .895`. Unshrunk, a *forecast* would outrank a proven
dominant team. With `s = 0.6` it lands at `.737` — below Pete's realized `.804`, which is the correct
ordering: no projection should outrank observed dominance. Pete's own roster, used as a prior, shrinks
to `.683`.

**Refit `s` from the archive after one season** — that is the first thing a year of weekly totals
buys. Monte Carlo is `draft-v2`.

### Assembling projected weekly totals

Two sub-decisions that need declared answers, because both are places output could vary:

- **Games in the scored week.** Use the real NBA schedule for that week per player's team, not a
  league-average constant. It is available, it is deterministic, and at 18 teams the spread between a
  3-game and a 4-game week is large enough to matter.
- **Which rostered players count.** The league's active roster slots cap how many players score in a
  week. Recommend: fill each slot greedily by projected 9-cat value subject to position eligibility,
  deterministically, and document the tiebreak. Do **not** sum the whole roster — that rewards bench
  depth the format cannot actually deploy.

---

## 5. Data requirements

Adds exactly one dependency beyond what `v1` already needs, and it is the project's only external one.

1. **Post-draft rosters.** From the league provider.
2. **Per-player per-game 9-category projections.** External. Candidates are `v1`'s cited sources
   (Hashtag Basketball, Dribble Grid). Access MUST comply with the provider's terms per the
   constitution's Technology & Operational Constraints.
3. **Projected games played**, or the NBA schedule plus a games-played estimate.
4. **League roster slot configuration**, for the slot-filling rule in §4.

> **Verify before committing to a projection source.** `v1` §6 item 2 requires FG% and FT% as
> **makes and attempts**, never as percentages. Projection providers commonly publish `FG%` and `FT%`
> only. If yours does, the week-0 category profile silently breaks on two of nine categories — and
> per §3 that profile is the main reason this page is worth publishing at week 0 at all. This is a
> go/no-go question on the source, not a detail.

---

## 6. Publication rules

These are obligations on `draft-v1` specifically, extending `v1` §4's two honesty requirements.

**Everything in §4 is internal.** Under strict disclosure (`v1` §5, spec FR-032–034) `DraftScore`,
`EMW_proj`, `CAW_proj`, and `s` are **never published** — not as figures, not rounded, not in a
tooltip. They exist to order the table and to give the article something true to say. Only **rank and
rank movement** reach the page as numbers. This resolves most of what would otherwise be a tension
here: there is no scalar to argue about, because no scalar is shown.

**Pre-draft: publish no ranking.** Not a shrunk one, not a tiered one. There is no input. Publish a
league preview, the draft date, the rules, or nothing at all.

**Post-draft: tiers vs. a 1–18 ordering is an open product decision.** The genre's own answer to
having no data is tiers — preseason columns use named bands and say their epistemics out loud, as
NBC's 2026-27 column does: *"this ranking is more about potential and expectations than a hard
count."* Tiers are honest about precision and make `s` far less load-bearing, since nobody has to
defend 11th against 12th when the gap is projection noise.

**But this conflicts with the existing spec**, whose User Story 1 commits the page to "the current
1–18 power rankings." Resolving it is a product call, not an algorithm call:

| Option | For | Against |
|---|---|---|
| Keep 1–18 at week 0 | consistent with every other week; no new rendering path | asserts precision the inputs do not support |
| Tiers at week 0 only | honest about projection noise | a presentation that appears once a season, then vanishes |

My recommendation is **1–18 with prose that carries the hedge**, on the grounds that strict disclosure
already hides the scalar — so the false precision a reader can actually see is limited to the ordering
itself, and a one-off rendering path is a poor trade for an 18-person audience. If tiers are adopted,
their boundaries MUST be declared constants, not eyeballed per run.

**Lead with the category profile.** "Came out of the draft as the best rebounding team in the league
and the worst at the free-throw line" is more interesting and more defensible than an ordering, and it
is the one thing no NBA or fantasy-football column can say. Per `v1` §5, name the **category rank**
(league data, safe) and never the all-play win rate behind it.

**Label the projection honestly, but do not describe the mechanism.** `v1` §4 requires weeks 0–2 be
labeled a draft-based projection. Branching the label on `w < 0.5` rather than on a week number is
better math — `w` is continuous and a cliff at week 3 has no principled basis — but note that *saying
why* the label changed would leak the existence and pace of the shrinkage weight, which FR-032–034
forbids. So: branch on `w` internally, and word the label as a standing, non-numeric statement
("early-season rankings lean on draft projections and settle as games accumulate"). The branch is a
rendering decision; the constant stays private.

**Hedge conditionally, the way the genre does.** Pattern-10 phrasing from the prose review: *"this may
be too low if X stays healthy."* Hedging is load-bearing when `w` is small.

### Fallback ladder, if no projection source is available

1. **Draft-slot prior.** Build the prior from where each player was actually taken — the league's own
   collective valuation, already sitting in league data. Zero external dependency, no provider, no
   terms-of-service question. **Strictly inferior**, not co-equal: draft slot carries no category
   structure, so punt-build identification and the entire category profile are lost. It is a scalar,
   which puts it back in the units trouble §3 exists to avoid.
2. **Publish no ranking.** `v1` §4's existing answer: standings only until week 2. A confidently wrong
   week-0 ranking is worse for a casual audience than an absent one.

---

## 7. Determinism and edge cases

Inherits every rule in `v1` §7 — tie handling at 0.5, stable sort by `(score desc, team_id asc)`,
rounding only at the display boundary. Additional cases specific to this algorithm:

- **Unfilled or empty roster slots** (an incomplete draft, a team that drafted short): define
  explicitly. Recommend contributing zero to counting categories and zero attempts to ratio
  categories, which routes into `v1` §7's zero-attempt rule rather than a new one.
- **A rostered player with no projection** (undrafted rookie, two-way, a provider gap): MUST NOT be
  silently dropped. Treat as zero and **surface the count on the page** — "3 of this team's players
  have no projection" is a legitimate confidence caveat, and hiding it is the kind of quiet
  degradation Principle II exists to prevent.
- **Players projected for zero games** in the scored week: excluded, consistent with `v1` §7's
  bye-week rule.
- **Constants** MUST live in `src/ccsv_rumble/config.py` alongside `EMW_WEIGHT`, `CAW_WEIGHT`,
  `SHRINKAGE_K` and `RECENCY_HALF_LIFE_WEEKS`, per `v1` §8 — a literal written anywhere else is a bug.
  This algorithm adds `DRAFT_SHRINK` (= `s`), `DRAFT_ALGORITHM_VERSION` (= `"draft-v1"`), the
  slot-filling tiebreak, and tier boundaries if §6 adopts tiers. It **reuses** `EMW_WEIGHT` and
  `CAW_WEIGHT` rather than redeclaring them, which is what keeps the two algorithms agreeing about
  what "good" means (§3).
- **Published prose MUST clear `DISCLOSURE_TERMS`.** The existing blocklist already rejects
  `"shrinkage"`, `"weighting"`, `"z-score"`, `"roster prior"`, `"algorithm"` and `"formula"` — which
  means the week-0 projection label in §6 cannot explain itself even if someone wanted it to. Any new
  draft-specific vocabulary (`"draft score"`, `"projection"` used as a method name) should be reviewed
  against that list when this ships.
- **Projection snapshots are archived like any other input** (Principle III). The projection source
  will revise its numbers daily; without the snapshot, a past draft ranking can never be reproduced
  or explained.

---

## 8. Versioning coupling with `v1`

Separating the algorithms separates their version numbers but **does not** decouple their published
output, because `PowerScore = w · Performance + (1 − w) · RosterPrior` depends on both for the whole
season.

Consequences:

- A change to `draft-v1` **changes published `PowerScore` values mid-season**, not just the week-0
  page. Principle I's before/after-comparison requirement therefore applies to `draft-v1` changes
  just as strictly as to `v1` changes.
- **Both declared versions MUST be recorded in the archived internal report and emitted into the
  page's provenance comment**, matching how `v1` §8 already handles `ALGORITHM_VERSION`. A rank that
  depends on two algorithms cannot be traced by citing one of them. The provenance comment is the
  right home for this — it is not a ranking-derived figure, so strict disclosure does not reach it.
- A change that affects only the week-0 publication rules in §6 (tier boundaries, label wording) is a
  `draft-v1` bump but has no effect on in-season `PowerScore`, and the before/after comparison should
  say so explicitly rather than showing an unchanged diff with no comment.

---

## 9. Deliberately out of `draft-v1`

- **Monte Carlo / probabilistic category comparisons.** The right fix for threshold overconfidence,
  deferred to `draft-v2` until the archive can supply real per-category weekly variance. A
  Poisson-binomial threshold over per-category win probabilities is the likely form.
- **Keeper and dynasty value.** Irrelevant to a single-season power ranking.
- **Draft grades or pick-by-pick evaluation.** Fun, and a different document.
- **In-season roster churn as a distinct mechanism.** There isn't one: `RosterPrior` is just
  `DraftScore` recomputed on the current roster snapshot. That is what makes it the only
  forward-looking term in `v1` and what lets it react to an injury or a lopsided trade.

---

## Open questions

- `s = 0.6` is a judgment call with no data behind it. First refit target after season one.
  Its worked example in §4 is now an executable test, so the justification cannot silently rot.
- ~~Projection source unresolved~~ **resolved**: a maintainer-curated local snapshot in a
  declared nine-category schema, archived with its source identity and retrieval time. No
  licensed API supplies makes and attempts, and scraping a site to power a public page is both
  fragile and a terms question — so the makes/attempts requirement in §5 is enforced at ingest
  instead, as a rejection rather than a degradation. See `002` research D1.
- ~~Tier count and boundaries~~ **resolved**: a 1–18 ordering was adopted, per §6's own
  recommendation. Strict disclosure already hides the scalar, so the only false precision a
  reader can see is the ordering itself, and a rendering path that appears once a season is a
  poor trade for an 18-person audience. No tier constants are needed.
- ~~Slot-filling rule needs the league's roster-slot configuration~~ **resolved**:
  `2G, 3FC, 1 Util, 4 B, 2 IL`. Six active slots, so eligibility collapses to three classes
  and slots fill narrowest-first (`G, G, FC, FC, FC, UTIL`), ties on `(value desc, player_id
  asc)`. Note the consequence §4 did not anticipate: at six slots one missing projection is
  **17%** of a team's week, not 10%, which is why the coverage floor permits exactly one
  unfillable slot.
- **New, found during implementation**: a draft fills 10 of 12 roster spots, because the two
  IL slots start empty. Any completeness check written against the roster maximum classifies
  every run as pre-draft — and pre-draft publishes nothing, exits zero and notifies no one, so
  it would produce no page indefinitely with no alarm. `DRAFT_ROSTER_SIZE = 10` excludes IL.
- **Still open**: `schedule.build_plan` does not target week 0 (it returns week 1 before any
  week completes), and a week-0 snapshot needs a rosters-only acquisition path since no
  scoreboard exists. Tracked as `002` T087–T089.
