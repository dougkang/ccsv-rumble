# Research: Captured-Data League Provider

Phase 0 for [plan.md](plan.md). Each entry records the decision, why it was made, and what else
was considered. Two checks were run against the committed data and code before any design was
fixed: R2 and R5.

## R1 — The capture rows are the raw input; no Yahoo-shaped JSON

**Decision**: The capture source returns the week's CSV rows as they are. A capture-specific
normalizer turns those rows into a `Snapshot`. The rows are archived as CSV text in a new
`raw-matchups.csv` file inside the entry, written byte-for-byte the way `write_projections`
already writes `raw-projections.csv`. They do not go into `raw-yahoo.json`. The snapshot's
`raw_source` is set to `"matchups.csv"`.

**Rationale**: Principle III requires the raw inputs to be archived *before any transformation*.
Converting rows into a synthetic Yahoo scoreboard just so `build_snapshot` can parse them is a
transformation. The archive would then record a payload Yahoo never sent, and a parse bug would
be diagnosed against invented data.

**Alternatives considered**: The original prompt asked for a Yahoo-shaped payload, so that
`normalize.py` would stay untouched. Rejected for the reason above. It would also couple the
capture to the walker's tolerance of shape changes, which is a property that exists only to
survive Yahoo's JSON.

## R2 — The category-win checksum (FR-008) matches real data

**Check run**: For each of the 18 committed week 1 rows, I counted strict category wins against the
opponent and compared the count to `cat_wins`. A tie counts as a win for neither side, and
turnovers count lower-wins. I ran it twice: ratio categories at exact `made/attempted`, then at
the displayed 3-decimal value. **18 of 18 matched under both rules.**

**Decision**: The checksum recounts category wins with `allplay.compare_category`, the same
comparison the ranking uses. It does not use `category_wins`, which always scores a tie as half.
A row passes if `cat_wins` equals any of four counts: exact or displayed percentages, with a tie
counted as nothing or as half. The capture scraper accepts values like `4.5`, which suggests the
page may show half-ties. Week 1 had no ties, so nothing has confirmed either convention.

**Rationale**: Yahoo may compare percentages at display precision, in which case .4412 vs .4408
is a tie. Week 1 had no such near-tie, so the data cannot say which rule Yahoo uses. Accepting
either rule avoids rejecting a valid week over a question nobody can settle yet. A real misread
column still shifts the count under both rules.

**Alternatives considered**: Exact-only, which would risk failing a valid week on a near-tie.
Display-only, which carries the same risk the other way.

## R3 — Seam: a source-specific builder next to the provider

**Decision**: `acquire_week` currently calls `build_snapshot` (Yahoo) directly. It will take a
`build` callable instead. The CLI picks one *league source* per run (FR-003): a provider paired
with its normalizer. The capture provider implements `LeagueDataProvider`:
`fetch_stat_category_map` returns `{}`, `fetch_week` returns the week's rows, and the two methods
the pipeline never calls (`fetch_rosters`, `fetch_transactions`) return empty payloads.

**Rationale**: `provider.py` already states that "swapping providers changes this package and
the normalizer, and nothing downstream." Passing the normalizer in alongside the provider is
exactly that seam. The archive, diff, correction and quarantine logic in `acquire_week` stays
shared, which is what makes FR-016 hold for both sources.

**Alternatives considered**: A separate `acquire_captured_week`. Rejected because it would
duplicate the correction and quarantine logic, and the two copies would drift.

## R4 — "Not captured" is a distinct signal, not a failure

**Decision**: The capture provider raises `WeekNotCaptured`, a subclass of `ProviderError`, when
the file has no rows for the requested week. `execute` catches it **only** in the recheck loop:
it logs "week N not re-checked: not in capture" and keeps the archived entry. Anywhere else, the
error propagates as an acquisition failure. The message names
`chrome_capture.py matchups --week N`.

**Rationale**: This implements the spec's Edge Cases rule. The archive already holds a valid
version of a re-checked week. A gap week or the publish week has nothing to fall back on.

## R5 — Capture-sourced snapshots carry the roster capture

**Check run**: `build_week_page` derives the in-season roster prior from `history[-1].rosters`
(`pipeline.py`, `_draft_entries`). Snapshots from `build_snapshot` never set `rosters`. So on the
API path, week 1+ would publish with **no roster prior**, even though `SHRINKAGE_K=3` intends the
prior to carry 75% of week 1's score.

**Decision**: The rule depends on whether the archive already holds the week, not on which loop
is calling. If `store.has_week(season, week)` is true, the snapshot carries the latest archived
entry's rosters. Otherwise it carries the roster capture (`data/rosters.csv`). This covers every
case with one rule: a first acquisition, a backfill, a recheck, and the current week being
acquired twice in one run, which happens on a same-week retry when it is both a recheck week and
the publish week.

**Rationale**: `rosters.csv` holds the rosters as of capture time. Attaching today's rosters to a
re-checked past week would change history. `archive/diff.compare` would then log every waiver
move as a stat correction and write a new archive entry for it. Carrying the archived rosters
forward means a recheck compares category totals only.

**Consequence**: The roster file should be captured together with the week. `chrome_capture.py
dailies` already does both. The quickstart uses it.

**Consequence for parity**: Capture-sourced pages are *expected* to differ from API-sourced pages
whenever projections are present, because only the capture path switches the prior on. See R12.

**Out of scope, recorded**: The API path has the same missing-prior gap. It is not fixed here,
because FR-018 says the API path stays unchanged.

## R6 — Team identity and names

**Decision**: Team ids must be the roster capture's `t.NN` ids. A matchups team id missing from
`rosters.csv` fails the run (FR-011). Each week's **team name** comes from that week's matchups
rows, because team names change mid-season and the week's own capture is right for that week.
**Managers** come from `rosters.csv`, blank if unresolved. A matchups name that differs from the
roster name is not an error.

## R7 — Matchup orientation

**Decision**: `home_team_id` is the lower team id and `away_team_id` the higher, sorted the same
way `extract_matchups` sorts. The matchup tuple is sorted by that pair.

**Rationale**: FR-017 requires identical downstream output from either source. Yahoo's own
home/away labels are not used anywhere downstream.

## R8 — Capture file format and per-week replace

**Decision**: Add three per-row columns to `data/matchups.csv`: `captured_at` (ISO-8601 with UTC
offset), `week_start` and `week_end` (ISO dates). Per-row rather than a sidecar file, so a week's
metadata cannot be separated from its rows when one week is replaced. `chrome_capture.py` merges
on write: it reads the existing file, drops rows whose `week` equals the captured week, appends
the new rows, and writes the result sorted by `(week, matchup, team_id)` (FR-012). Rows in the
existing pre-change format, which lack the new columns, are kept as-is. The loader reports them as
missing `captured_at`, so they fail FR-009, which the current partial week 1 should do anyway.

See [contracts/matchups-capture.md](contracts/matchups-capture.md).

## R9 — Where week dates come from (discovery task)

**Decision**: `yahoo_matchup_capture.js` reads the week's date range from the scoreboard page.
**This needs a browser to confirm.** The scoreboard's week selector usually shows a range like
"Oct 20 – Oct 25", but the selector has not been located.

**Fallback**: If no reliable date element exists, the capture accepts `--matchup-start` and
`--matchup-end`. These are separate from the projections' `--week-start/--week-end`, because `all`
captures the week that ended and projects the week ahead, so the two windows differ. If neither
the page nor the flags supply dates, the capture refuses to write.

**As built**: `__matchup.weekDates()` returns every short text node shaped like "Oct 20 - Oct 25".
Python accepts the result only if all of them parse to one range. **This is unverified against
the live page.**

**Not** a fallback: computing the dates from the calendar function. That would make the
cross-check in R10 compare the formula against itself.

## R10 — FR-009 timing and the calendar fix

**Decision, FR-009**: A week is ended when `captured_at`, converted to `LEAGUE_TIMEZONE`, falls on
a date **after** `week_end`. The run uses the recorded `captured_at` only, never file mtime,
because a git checkout in CI resets mtime.

**Decision, calendar (brought into scope)**: `schedule.week_for_date` changes from "7-day weeks
from opening day" to the league's shape:
- week 1 runs from opening day to the first Sunday on or after it;
- every later week runs Monday to Sunday.

The capture's recorded dates are checked against this calendar. A mismatch fails the run and
names both date ranges.

**Rationale**: This is not cosmetic. On Monday 2026-10-26 the current formula gives
`(6 // 7) + 1 = 1`, so `completed = 0`, and the plan targets **week 0**. A Monday run after
recapturing would republish week 0 instead of week 1. The Tuesday cron gets the right answer only
because every Tuesday falls after both boundaries. The cross-check replaces silent drift with a
loud failure.

**Known future break, out of scope**: Yahoo usually merges the All-Star break into one long week.
No fixed formula survives that. The cross-check turns it into a named failure when it arrives,
and a declared week table in `config.py` is the likely fix then.

**Alternatives considered**: Deriving the plan from the capture alone. Rejected because a
completed week that was never captured would be invisible to gap detection, and FR-037 backfill
depends on seeing it.

## R11 — Source selection

**Decision**: A new `--source {capture,yahoo}` option on `run` and `dry-run`, defaulting to
`capture` (FR-002), plus `--matchups` with a default of `data/matchups.csv`. On `capture`,
`cmd_run` never calls `_provider_from_env`, so missing `YAHOO_*` variables cannot fail the run
(FR-001). `weekly.yml` does not need to change. Its `YAHOO_*` secrets go unused, and removing
them is left to a separate cleanup.

**Capture default**: With no `--week`, `capture_matchups` captures the week in progress, which
FR-009 always refuses. The default changes to **the most recent week that has ended**, using the
R10 calendar. `--week` still overrides it.

**Alternatives considered**: Auto-detect, meaning use capture when the file covers the week, else
the API. Rejected. It mixes sources across runs, and it turns "the maintainer forgot to capture"
into a confusing Yahoo 403 instead of a message naming the missing week.

## R12 — What FR-017 parity means

**Decision**: FR-017 means that, for the same league data, everything downstream of the snapshot
behaves identically. The test will:
- convert `tests/fixtures/yahoo_week.json` into an equivalent capture CSV;
- **normalize** both snapshots before comparing them: map Yahoo team keys to `t.NN`, drop
  `rosters`, managers and `stat_category_map`;
- assert equal `category_totals`, `matchups` and team order.

The golden page `tests/golden/week-01.html` is compared **only for a run without projections**,
where neither source has a prior.

**Rationale**: The two snapshots legitimately differ in ids, managers, the stat map, and above all
rosters (R5), which switch on the roster prior. A naive byte comparison would fail for reasons that
are not bugs.

## R13 — Week 0 is counted as a scored week (pre-existing; fixed here)

**Finding**: When week 1 publishes, `history` is `[week 0, week 1]`, and nothing filters week 0
out:

1. `score.build_ranking` counts `completed = len(history) = 2`, so `performance_weight` is 0.40
   instead of 0.25.
2. Week 0's all-zero totals, where every category ties, are averaged into EMW and CAW at a recency
   weight of 0.84, against week 1's 1.0. Week 1 scores are pulled toward .500.
3. `pipeline.py:521`: an archived week that is not being republished gets its `previous_ranks` from
   `build_ranking(history)`. For week 0, that ranks all-zero totals, which is an arbitrary order.
   So week 1's movement arrows compare against noise, not against the draft ranking readers saw.
4. `build_week_page` uses `len(history) <= 1` for `is_projection` and `is_provisional`, and that is
   false at week 1 once week 0 is present.
5. `cli._render_archived` builds the same history, so replay has the same defect.

The API path is affected the same way. The golden `week-01.html` was built with no archived week 0,
which is why no test caught it.

**Decision**: Fix it in the **pipeline**, not in `rank/`:
- The ranking history passed to `build_ranking`, and to the labels, holds played weeks only
  (`week > 0`).
- Week 0's `previous_ranks` comes from its archived **published** ranking (`publishable.json` in
  the week 0 entry), the order readers actually saw.
- `_render_archived` uses the same helper, so live runs and replay cannot drift apart (FR-022).
- `derive_events` keeps receiving prior *played* weeks. Week 0 has no player weeks, so this changes
  nothing there.

**Algorithm version**: `ALGORITHM_VERSION` stays `v1`. `build_ranking` is not modified; it was being
given the wrong input. The constitution's before/after comparison on archived data is trivially
empty, because no week ≥ 1 has ever been archived or published. This is recorded so the reviewer
does not have to rediscover it.

**Alternatives considered**: Filtering inside `build_ranking`. Rejected. The pure function would
need to know that "week 0" means "projection", which is a pipeline concept, and every caller would
silently depend on that.

**Found during implementation, and fixed**: Week 2 had the same defect as point 3, one week
later. Recomputing week 1's ranks for the carry-forward leaves out the roster prior that the
published week 1 page included. Now that capture snapshots carry rosters (R5), the prior is
present, and at one played week it is 75% of the score. So week 2's movement would have been
measured against an order no reader saw. `pipeline.carried_ranks` now carries **any** archived
week's published ranks, read from the newest entry that has a `publishable.json`, since a
correction entry has none. It recomputes only for a week that was never published. Replay uses the
same function. Test: `test_week2_movement_is_against_the_published_week1_ranking`.
