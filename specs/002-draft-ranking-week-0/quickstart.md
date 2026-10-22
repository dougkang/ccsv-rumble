# Quickstart — Validating Draft Ranking (Week 0)

**Feature**: [`002-draft-ranking-week-0`](spec.md) · **Phase 1** · 2026-10-22

How to prove the feature works. Every scenario below runs **offline** — the chosen projection source
is a local file and replay needs no network — so none of this waits on league-data acquisition.

## Prerequisites

```bash
uv sync
uv run pytest                      # baseline must be green before starting
```

One input you must supply, in the schema from
[`contracts/projection-source.md`](contracts/projection-source.md):

```bash
# gitignored; real file for a live run, fixture for tests
data/projections.csv
```

**The format has changed from 001.** The old `player_id,value` file will be rejected: it carries one
pre-aggregated scalar, and FR-010 requires the nine categories with makes and attempts. That rejection
is correct behaviour, not a regression — see [research.md](research.md) D1.

One unknown to fill first: the league's **active roster slots and position eligibility**
([research.md](research.md) D3). Read it off the league settings page in a browser and declare it in
`config.py`. Phase 4 cannot be validated without it.

## Scenario 1 — Pre-draft publishes nothing and is not a failure

Covers FR-003, FR-004, FR-008, SC-002. The behaviour most likely to be got wrong, because the
"correct" outcome looks identical to a silent failure.

```bash
uv run ccsv-rumble dry-run --from-archive --week 0    # against a pre-draft fixture
echo "exit: $?"
```

**Expect**: exit `0`. No page rendered. A log line naming the lifecycle state *and the reason* —
"2 of 18 rosters below 10", not merely "pre-draft". **No failure notification.**

**Also assert the inverse**, since this is the risk the plan calls out: a genuine acquisition failure
must still exit non-zero and notify. If both paths go quiet, the gate is wrong.

### 1a — A drafted league must classify as drafted

**This is the highest-value test in the feature**, because the failure it guards is silent by design.

```bash
# fixture built from real post-draft roster sizes: 10 players per team, IL empty
uv run ccsv-rumble dry-run --from-archive --week 0
```

**Expect**: `POST_DRAFT`, and a page. **Not** pre-draft.

The league carries 12 roster slots but a draft fills only 10 — the two IL slots start empty. A
completeness check written against the 12-slot maximum would mark every team incomplete forever,
classify every run as pre-draft, and so publish nothing while **exiting zero and never notifying**.
The generator would report success every week and produce no page, indefinitely, with no alarm.

So `DRAFT_ROSTER_SIZE = 10`, excluding IL — and this test is what keeps it honest. A test that passes
whether the constant is 10 or 12 is not testing anything; build the fixture with IL genuinely empty.

**Also assert**: a team that dips to 9 players mid-season, between a drop and an add, classifies as
`IN_SEASON` rather than pre-draft. Draft completeness is only consulted when no scored week has
finished, so the order of the three checks is itself load-bearing.

## Scenario 2 — Week-0 page shows 18 teams with movement unavailable

Covers FR-005, FR-006, FR-030, SC-001.

```bash
uv run ccsv-rumble dry-run --from-archive --week 0
```

**Expect**: all 18 teams in rank order. Rank movement rendered as **unavailable, not zero** — no
previous ranking exists, and zero would assert "unchanged", which is a different and false claim. A
projection label that does not describe the mechanism by which projections give way to results.

## Scenario 3 — Nothing from the computation leaks

Covers FR-028, FR-029, FR-033, SC-004. Enforced by the existing validation gate; this confirms it
covers the new fields.

```bash
uv run ccsv-rumble dry-run --from-archive --week 0
grep -ciE 'draft.?score|emw|caw|shrink|0\.6' <rendered page>   # expect 0
```

**Expect**: `draft_score`, `emw_proj`, `caw_proj` and `DRAFT_SHRINK` appear nowhere — not as figures,
not rounded, not in alt text, tooltips, data attributes, or markup comments.

**Expect present**: both algorithm versions in the provenance comment — `v1` *and* `draft-v1`. A rank
depending on two algorithms cannot be traced by citing one (FR-033).

## Scenario 4 — The percentage trap is refused

Covers FR-010. The go/no-go on any projection source.

```bash
# a fixture with fg_pct/ft_pct columns instead of fgm,fga,ftm,fta
uv run ccsv-rumble dry-run --week 0 --projections tests/fixtures/projections-percent-only.csv
echo "exit: $?"
```

**Expect**: non-zero exit, an explicit error naming the missing makes-and-attempts columns, nothing
published. **Expect NOT**: attempts inferred, derived, or defaulted — a silent success here is the
worst outcome available, because it corrupts exactly the two categories the category profile depends
on.

## Scenario 5 — Replay reproduces, even after the source revises

Covers FR-011, FR-012, FR-013, SC-003, and User Story 4. This is the scenario that fails today.

```bash
uv run ccsv-rumble replay --week 0 --latest
# now edit data/projections.csv — change several numbers
uv run ccsv-rumble replay --week 0 --latest
```

**Expect**: byte-identical output from both runs. The replay reads the **archived snapshot**, so
editing the live file changes nothing.

**This is the regression test for a current defect.** `rank/prior.py` reads the file at rank time, so
on today's code the second run would differ. If both runs match only because the file wasn't really
re-read, the test is not proving what it claims — assert on the archived snapshot path being opened.

## Scenario 6 — Coverage below threshold refuses to publish

Covers FR-026, FR-038, SC-007.

```bash
# fixture where one team can fill only 4 of its 6 active slots
uv run ccsv-rumble dry-run --week 0 --projections tests/fixtures/projections-sparse.csv
echo "exit: $?"
```

**Expect**: non-zero exit, nothing published, previous page untouched, maintainer notified.

Test both floors separately — they catch different failures, so one fixture validates half the rule:

| Fixture | Binds | Why |
|---|---|---|
| one team fillable to 4/6 | per-team (0.667 < 0.80) | one unrankable team among seventeen fine ones |
| every team fillable to 5/6 | league-wide (0.833 < 0.95) | passes every per-team check at 0.833; a gap on all 18 teams is a source problem, not 18 coincidences |

Also assert the **boundary**: a single team at 5/6 (0.833) must **pass**, since six active slots means
0.80 permits exactly one unfillable slot. An off-by-one here either blocks a publishable week or
publishes a team a third of whose week is unknown.

**And assert coverage is not confused with the unprojected count.** A team with six projected starters
and four unprojected bench players has **100% coverage** and an unprojected count of 4 — it must
publish. Conflating the two would refuse a perfectly rankable league (research D5).

## Scenario 7 — Unprojected players are accounted for

Covers FR-025, SC-006.

**Expect**: every rostered player either has a projection or is counted as unprojected; the counts are
in the internal report; and the count may appear on the page **as prose**, never as a table figure
(research D6).

## Scenario 8 — The shrink constant earns its value

Covers FR-020, and makes the design document's justification executable rather than prose.

Assert the worked example from `docs/draft-rankings-algorithm-v1.md` §4: a team whose point
projections sweep five categories scores `AllPlay_proj ≈ .895` unshrunk, which would outrank a proven
dominant team at `.804`. With `s = 0.6` it must land at `≈ .737` — **below** the proven team.

**Expect**: that ordering holds. It is the whole reason the constant exists: no projection should
outrank observed dominance.

## Scenario 9 — Article failure degrades one section

Covers FR-048, FR-049, SC-008.

**Expect**: with draft results absent, or article generation failing, the page still publishes with the
complete ranking table and **no article section at all** — no placeholder, no explanation. The
maintainer is notified, because the page is silent about the omission.

```bash
uv run ccsv-rumble dry-run --from-archive --week 0   # repeat run
```

**Expect**: no model call on a repeat run — the archived article is replayed (FR-044).

## Scenario 10 — Purity is enforced, not just intended

Covers FR-021 and the violation recorded in [plan.md](plan.md).

```bash
uv run pytest tests/unit/test_architecture.py -v
```

**Expect**: the widened assertion fails against the pre-fix `rank/prior.py` and passes after. Check
that first — a test that passes on both versions is not testing anything. The existing version misses
the violation entirely, because it inspects the import graph against internal package names and
`csv`/`pathlib` are neither.

## Scenario 11 — The prior reacts to roster change

Covers FR-035, FR-036, and User Story 3.

Take two in-season snapshots differing **only** by one team losing its highest-projected player.

**Expect**: that team ranks no higher in the second than the first, and nothing else moves for any
other reason. Confirm the prior is recomputed from current rosters rather than reused from the draft —
otherwise the only forward-looking term in the in-season ranking is frozen at draft night.

## Pre-merge gates

Beyond the project's standing gates:

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ccsv-rumble dry-run --from-archive --week 0     # must pass validation
```

Plus, per Principle I and FR-037: a change to `DRAFT_SHRINK`, the slot-filling rule, or the coverage
thresholds **bumps `draft-v1`** and must arrive with a before/after rank comparison over archived
weeks — because this algorithm affects in-season published ranks, not only the week-0 page.
