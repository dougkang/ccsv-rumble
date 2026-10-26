# Feature Specification: Captured-Data League Provider

**Feature Branch**: `matchups-capture` (no feature branch created — no `before_specify` git hook is registered)

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Captured-data league provider. In-season runs (week >= 1) currently always construct the Yahoo OAuth provider, which returns 403 because the Yahoo app is pending Fantasy Sports API review, so week 1+ power rankings cannot be produced. The browser capture side already exists (tools/chrome_capture.py writes data/matchups.csv with per-team week totals: FGM/FGA, FTM/FTA, 3PM, PTS, REB, AST, STL, BLK, TO, cat_wins, opponent, matchup; plus data/rosters.csv), but nothing in src/ reads matchups.csv. Add a LeagueDataProvider implementation backed by the committed capture files, returning the same payload shape normalize.py already consumes, so rank/report/render/publish are untouched. The run selects it when capture files cover the requested week (or via an explicit flag), keeping YahooProvider for when API access is approved. A week whose capture is missing any of the 18 teams, or lacks made/attempted counts, must fail rather than rank a partial grid (all-play needs the full grid). Credentials must not be required on the capture path. This is Phase 3 of specs/004-browser-session-provider, re-scoped from a session-credential HTTP provider to a committed-file provider."

**Depends on**: [`004-browser-session-provider`](../004-browser-session-provider/spec.md). This is
its **Phase 3 — Provider**, re-scoped. 004's Decision (2026-10-22) already established that
acquisition is a browser capture whose output gets committed. What it never built is the piece
that makes the scheduled run *read* that committed data for weeks >= 1. 004's FR-001 through FR-007
(what the data must contain) apply here unchanged.

**Does not change**: reporting, rendering, validation, or publishing — the same boundary 004 drew.
Ranking itself is unchanged *except* for one pre-existing defect brought into scope (FR-019–FR-021):
week 0 is wrongly counted as a played week. Any in-season page hits this defect, whatever the data
source.

## Why this feature exists

Week 0 publishes because it is built from rosters and projections and never touches the league
API. Every week after that does touch it: the run builds the Yahoo OAuth provider, and its first
request fails with a 403, because Yahoo has not yet reviewed the app. The run exits as an
acquisition failure and publishes nothing.

The data needed to rank week 1 is already captured. `data/matchups.csv` holds every team's category
totals for the week, with shooting as makes and attempts, plus the pairings and each side's
category-win count. Nothing reads it. This feature closes that gap and nothing more.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Week 1 publishes from the committed capture (Priority: P1)

After week 1 closes, the maintainer captures the week's matchups, commits, and pushes. The next
scheduled run ranks week 1 from that file and publishes the page. No Yahoo credentials are
configured, and the run never contacts the Yahoo API.

**Why this priority**: This is the whole feature. Without it, no in-season page can be published.

**Independent Test**: Commit a complete capture of a closed week to a checkout with no Yahoo
credentials, run a dry run for that week, and confirm the page renders with all 18 teams ranked
and no network request goes to the league API.

**Acceptance Scenarios**:

1. **Given** a complete capture of week 1 taken after the week ended and no Yahoo credentials, **When** the run targets week 1, **Then** it publishes a week 1 page ranking all 18 teams and exits zero.
2. **Given** the same capture, **When** the run is repeated, **Then** it produces an identical page and creates no new archive entry and no new publish commit.
3. **Given** the week was published from a capture, **When** it is later replayed from the archive with no `data/` directory present, **Then** the replayed page is identical to the published one.

---

### User Story 2 - A bad capture fails loudly instead of publishing a wrong page (Priority: P1)

The capture can be wrong in ways a reader would never see: a team missing, a week still in
progress, a shooting column misread. Every one of these must stop the run before anything is
published, leave the previous page live, and say which check failed.

**Why this priority**: A wrong ranking looks exactly like a right one. The constitution prefers a
stale correct page to a fresh wrong one, and the capture path is where the wrong data enters.

**Independent Test**: Feed the run each defective capture listed below and confirm each one exits
non-zero, publishes nothing, sends a failure notification, and logs a message naming the defect.

**Acceptance Scenarios**:

1. **Given** a capture of week N with 17 teams, **When** the run targets week N, **Then** it fails and names the missing team.
2. **Given** a capture of week N taken before week N ended, **When** the run targets week N, **Then** it fails and says the capture is from an in-progress week.
3. **Given** a capture row with a blank or non-numeric made or attempted count, **When** the run targets that week, **Then** it fails and names the team and column.
4. **Given** a capture whose recorded category-win count for a team disagrees with the count computed from the captured totals, **When** the run targets that week, **Then** it fails and names both teams in the matchup.
5. **Given** the run targets week N and the capture contains no rows for week N, **Then** it fails and names the week the maintainer needs to capture.

---

### User Story 3 - The Yahoo API path keeps working for when it is approved (Priority: P3)

If Yahoo approves the app, the maintainer can switch the run back to the API without code changes.
Until then, the API path must not be required, attempted, or able to break a capture-backed run.

**Why this priority**: 004 made browser capture the permanent choice, so this is insurance, not a
goal. Keeping the existing provider costs little; deleting it is a separate decision.

**Independent Test**: With the source explicitly set to the API, confirm the run behaves exactly
as it does today. With the source unset and a capture present, confirm the API path is never used.

**Acceptance Scenarios**:

1. **Given** the league data source is explicitly set to the API and valid credentials exist, **When** the run executes, **Then** it acquires from the API as it does today.
2. **Given** the source is not set, **When** the run executes, **Then** it uses the committed capture and does not require or read Yahoo credentials.

---

### Edge Cases

- **Recapturing a week.** Capturing week N again replaces week N's rows and leaves every other
  week's rows intact. Today the capture tool overwrites the whole file, so capturing week 2 would
  erase week 1. That would break backfill and the correction window.
- **Correction window.** The run re-checks recent weeks for retroactive stat corrections. If a
  re-checked week is in the capture and differs from the archive, it is archived as a correction,
  exactly as with the API. If a re-checked week is absent from the capture, the archived version
  stands and the run logs that the week was not re-checked. This is not a failure, because the
  archive already holds a valid version.
- **Backfill gap.** A completed week that is neither archived nor captured fails the run and names
  the week. Ranking later weeks without it would corrupt cumulative history.
- **Team identity.** Capture team ids must match the ids used by the roster file and by the
  archived week 0. A team id in the matchups capture that is unknown to the roster capture fails
  the run.
- **Manager names.** The matchups capture carries no manager names. These come from the roster
  capture, as at week 0. A manager that cannot be resolved is shown blank, never as a team id.
- **Ties within a category.** A tied category counts as a win for neither side. The win-count
  cross-check (Story 2, scenario 4) must apply the same rule the league does.
- **Zero attempts.** A team with zero FGA or zero FTA in a week is valid data, not a misread. It
  must rank without dividing by zero.
- **Draft-only league.** Before week 1 closes, the run still targets week 0 and must not demand a
  matchups capture.

## Requirements *(mandatory)*

### Functional Requirements

**Source selection**

- **FR-001**: The run MUST be able to acquire league data for weeks >= 1 from the committed capture
  files, with no Yahoo credentials configured and no request to the league API.
- **FR-002**: The committed capture MUST be the default league data source. The Yahoo API MUST be
  used only when the maintainer explicitly selects it.
- **FR-003**: A single run MUST use one league data source for every week it acquires. Mixing
  sources within one run is not permitted.
- **FR-004**: When the run selects the capture source, it MUST log which source it used and which
  weeks the capture covers.

**Completeness and integrity** (each of these is a failure: exit non-zero, publish nothing, notify)

- **FR-005**: The capture for a week MUST cover every team in the league exactly once, in exactly
  half as many matchups as there are teams. Otherwise the run MUST fail.
- **FR-006**: Every team row MUST carry integer made and attempted counts for both field goals and
  free throws, plus integer values for every counting category the league scores. A missing,
  blank, or non-numeric value MUST fail the run and name the team and column.
- **FR-007**: Each matchup's two rows MUST name each other as opponent. Otherwise the run MUST fail.
- **FR-008**: The run MUST check each team's recorded category-win count against the count
  computed from the captured totals, and fail on any disagreement. This is the checksum that
  catches a misread column, the same way 004 uses the displayed percentage.
- **FR-009**: Each capture MUST record when it was taken. The run MUST refuse to rank a week from a
  capture taken before that week ended in the league's time zone. A week has ended once the
  calendar day after its last scoring day has begun.
- **FR-009a**: The week's start and end dates MUST come from the league itself, as the capture
  records them (FR-013). The run MUST NOT compute them by counting fixed seven-day weeks from the
  season start. Yahoo's week 1 is a short Tuesday–Sunday week (2026-10-20 to 2026-10-25), and
  later weeks run Monday–Sunday, so a fixed seven-day count from opening day puts every week
  boundary one day late.
- **FR-010**: A capture that has no rows for a week the run must publish MUST fail the run with a
  message naming the week and the command that captures it.
- **FR-011**: A team id present in the matchups capture but absent from the roster capture MUST
  fail the run.

**Capture tool**

- **FR-012** *(revised 2026-10-26: daily snapshots)*: Every capture MUST be kept as a dated
  snapshot, one file per capture day. Capturing a week again on the same day replaces only that
  week's rows in that day's file. The run MUST rank each week from its latest snapshot taken after
  the week ended. Original text: Capturing a week MUST replace only that week's rows in the committed matchups file,
  preserving every other week.
- **FR-013**: The capture tool MUST record, for each week it writes, the capture time required by
  FR-009 and the week's start and end dates as the league displays them.

**Archive and replay** (Principle III)

- **FR-014**: The run MUST archive the captured rows it used for each week verbatim, before any
  transformation, and the archive MUST identify the capture as the week's source.
- **FR-015**: Replaying a week acquired from a capture MUST reproduce the published page with no
  network access and no `data/` directory.
- **FR-016**: Re-running with an unchanged capture MUST NOT create a new archive entry or a publish
  commit. A changed capture for an already-archived week MUST be recorded as a correction that
  supersedes the earlier entry.

**Boundary**

- **FR-017**: Ranking, reporting, rendering, validation, and publishing MUST produce the same output
  for the same league data whether it came from the capture or the API. "Same league data" is
  defined in research R12.
- **FR-018**: The existing API path MUST continue to work unchanged when explicitly selected.

**Week 0 in the in-season ranking** (pre-existing defect, brought into scope)

- **FR-019**: The ranking for week N ≥ 1 MUST count only played weeks 1..N as history. Week 0 MUST
  NOT count as a completed week, and its all-zero totals MUST NOT be averaged into any week's
  result-based metrics.
- **FR-020**: Rank movement for week 1 MUST be measured against week 0's *published* (draft)
  ranking. A ranking recomputed from week 0's zero totals MUST NOT be used.
- **FR-021**: The page's "projection" and "provisional" labels for week 1 MUST be decided from the
  number of played weeks, not from the length of a history that includes week 0.
- **FR-022**: Replay MUST apply FR-019–FR-021 the same way a live run does, so a replayed week 1
  matches the published one.

### Key Entities

- **Week capture**: Every row the capture holds for one league week, plus when it was taken. Each
  row is one team's side of one matchup: team, opponent, matchup number, made/attempted shooting,
  counting categories, the displayed shooting percentages (kept as a checksum), and the recorded
  category-win count.
- **Roster capture**: The existing team and player file. Here it supplies team names and managers,
  and defines which team ids are valid.
- **Archive entry**: The existing per-week archive record. For a capture-sourced week, its raw input
  is the week capture's rows instead of an API payload.
- **League data source**: Where the run gets league data for weeks >= 1: either the committed
  capture (the default) or the Yahoo API (selected explicitly).

## Constitution Alignment

- **Principle II (fail loud and safe)**: FR-005 through FR-011 each fail the run rather than publish
  from a defective capture. The previous page stays live.
- **Principle III (archive raw inputs)**: FR-014 and FR-015. The capture rows *are* the raw input. If
  the archive held a reshaped API-style payload instead, it would record data that never existed in
  that form.
- **Scheduling (no human between trigger and publish)**: satisfied as 004 decided. The human step is
  the capture and commit, which happen before the trigger.
- **Secrets**: the capture path reads no credentials, so a capture-backed run needs no Yahoo secrets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Week 1 publishes within one scheduled run of the maintainer committing a complete
  post-week capture, with zero Yahoo credentials configured.
- **SC-002**: Each defect class in User Story 2 is refused 100% of the time, with nothing published
  and a message naming the defect.
- **SC-003**: Replaying a capture-sourced week from the archive matches the published page byte for
  byte.
- **SC-004**: Two consecutive runs on an unchanged capture create no archive entries or publish
  commits beyond those of the first run.
- **SC-006**: With week 0 archived, week 1's ranking is identical to a ranking of week 1 alone with
  one completed week, and its movement arrows compare against the published week 0 order.
- **SC-005**: The maintainer's weekly chore stays one capture command plus commit and push. No new
  manual step is added.

## Assumptions

- **Matchup pages give made/attempted shooting.** The matchups capture already reads FGM/FGA and
  FTM/FTA from each matchup page and checks them against the displayed percentage. This supersedes
  004's finding that "the matchup view shows percentages only" and its plan to derive shooting from
  per-player roster data (FR-002a). That derivation is not needed on this path.
- **Past weeks stay addressable.** The capture tool accepts an explicit week. This assumes a
  completed week's matchup pages still show that week's final totals, which is 004's open gate G7
  restated for matchup pages. If it is false, backfill and the correction window can use only weeks
  captured at the time, and the fallback rules in Edge Cases apply.
- **Real record comes from pairings plus totals.** Matchup wins and losses can be computed from the
  pairings and category totals. The recorded category-win count is a checksum, not an input.
- **Games played is not needed for ranking.** The capture has no games-played column. Only the
  per-player "standout week" events read games played, and per-player weekly lines are out of
  scope here. So capture-sourced weeks will have **no standout events**. The article still gets
  rankings, movement, and matchup results.
- **Week boundaries come from the league, not a formula** (FR-009a). The run's existing calendar
  assumes seven-day Tuesday–Monday weeks from opening day, but the league's weeks are a short
  Tuesday–Sunday week 1 followed by Monday–Sunday weeks. The weekly Tuesday run picks the right
  week only by coincidence, since every Tuesday falls after both boundaries. A run on a Monday
  would treat the week that just ended as still in progress. The README's example capture window
  (`--week-end 20261026`) inherits the same error. Planning brought the fix into scope
  ([research.md](research.md) R10), with a cross-check against the capture's recorded dates.
  Week dates on capture-sourced pages come from the capture.
- **The committed week 1 data is probably not final.** `data/matchups.csv` was captured at 20:43 PT
  on Sunday 2026-10-25, week 1's last day, while late West Coast games could still have been in
  progress and before Yahoo's overnight stat finalization. FR-009 refuses it. Recapture week 1 on
  Monday 2026-10-26 or later.

## Dependencies

- `tools/chrome_capture.py matchups` and `tools/yahoo_matchup_capture.js`, which already exist and
  are extended only by FR-012 and FR-013.
- `data/rosters.csv`, which supplies team identity and managers.

## Out of Scope

- Removing the Yahoo API provider. That is a separate decision.
- Automating the capture or running it in CI. 004 settled that capture is attended.
- Per-player weekly stats, transactions, and roster changes for weeks >= 1. This feature supplies
  what the ranking needs. Anything an article wants beyond that is a separate feature.
- Correcting the `nba.l.194131` league key. It matters only to the API path.
