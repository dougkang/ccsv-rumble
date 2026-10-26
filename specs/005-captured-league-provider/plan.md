# Implementation Plan: Captured-Data League Provider

**Branch**: `matchups-capture` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-captured-league-provider/spec.md`

## Summary

For weeks ≥ 1, the run currently goes only through the Yahoo API, which returns 403. This plan
adds a **capture** league source and makes it the default. The source reads `data/matchups.csv`
together with `data/rosters.csv`, validates the week (coverage, pairing, integers, a category-win
checksum, capture timing, calendar agreement), and builds the same `Snapshot` the API path builds.
Reporting, rendering and publishing are untouched.

Three supporting changes:
1. `acquire_week` takes a source-specific snapshot builder, so archive, correction and quarantine
   logic stay shared between the two sources.
2. The capture tool records capture time and week dates, and replaces one week's rows at a time
   instead of overwriting the file.
3. `schedule.week_for_date` changes to the league's real calendar: a short Tue–Sun week 1, then
   Mon–Sun weeks. Without this, a Monday run targets week 0.
4. Week 0 stops being counted as a played week in the in-season ranking (R13). This defect predates
   the feature, but every week 1 page hits it whatever the data source. The fix is in the pipeline
   only: `build_ranking` itself is unchanged.

Rationale for each decision is in [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.14 (`pyproject.toml`); the capture-page scraper is JavaScript run
in Chrome via AppleScript

**Primary Dependencies**: stdlib `csv`, `datetime`, `zoneinfo`. No new dependencies

**Storage**: committed files. Input is `data/matchups.csv` and `data/rosters.csv`. Output is the
append-only `archive/` (new `raw-matchups.csv` per entry)

**Testing**: pytest (`tests/unit`, `tests/integration`, golden pages in `tests/golden`)

**Target Platform**: GitHub Actions `ubuntu-latest` for the run; macOS + Chrome for the attended
capture

**Project Type**: CLI batch job producing a static site

**Performance Goals**: not material. One 18-row week is parsed per acquisition

**Constraints**:
- no network on the capture path;
- deterministic: the clock and timezone are injected, never read inside pure code;
- the capture path must not read or need credentials.

**Scale/Scope**: 18 teams, about 20 weeks, roughly 360 rows per season

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | How this plan complies | Status |
|---|---|---|
| I. Pure ranking, deterministic render | Nothing in `rank/`, `render/` or `report/` changes. The week 0 fix only changes the history the pipeline passes in (R13); version unchanged, and the before/after comparison is empty. The new normalizer lives in `fetch/`, outside the pure packages that `test_architecture.py` guards. Timing checks take the clock as a parameter | ✅ |
| II. Fail loud and safe | Every capture defect raises `ProviderError`, which leads to `EXIT_ACQUIRE`, nothing pushed, and a notification. Skipping a recheck week is logged and is not a silent fallback, because the archived entry is valid | ✅ |
| II. Idempotent re-runs | An unchanged capture produces an unchanged snapshot. `diff.compare` returns no delta, so no entry and no commit. Rechecks carry archived rosters forward, so rosters cannot produce false corrections (R5) | ✅ |
| III. Archive raw inputs | The week's rows are archived verbatim as `raw-matchups.csv` before any transformation, not as a reshaped payload (R1). Replay reads `snapshot.json` and needs no `data/` | ✅ |
| IV. Static, accessible output | No change | ✅ |
| V. Secrets | The capture path reads no credentials. The archive is still scrubbed on write | ✅ |
| Scheduling: no human between trigger and publish | The human step is capture + commit, which happens before the trigger. This was settled in 004's Decision | ✅ |
| Provider behind an interface | The capture provider implements `LeagueDataProvider`. The source is chosen in one place, `cli.py` | ✅ |

**Post-design re-check**: still passes. The design adds one new archive file name and changes no
existing file's meaning.

## Project Structure

### Documentation (this feature)

```text
specs/005-captured-league-provider/
├── plan.md                     # this file
├── research.md                 # R1–R11
├── data-model.md               # WeekCapture, validation order, Snapshot mapping
├── quickstart.md               # end-to-end validation
├── contracts/
│   ├── matchups-capture.md     # the CSV contract between capture and run
│   └── cli.md                  # --source / --matchups
└── tasks.md                    # /speckit-tasks
```

### Source Code (repository root)

```text
src/ccsv_rumble/
├── fetch/
│   ├── captured.py        # NEW: load + validate WeekCapture, CapturedProvider,
│   │                      #      build_capture_snapshot, WeekNotCaptured
│   ├── normalize.py       # unchanged (Yahoo builder)
│   └── provider.py        # + WeekNotCaptured(ProviderError)
├── archive/store.py       # + EntryPaths.raw_matchups, write_raw_text, text quarantine
├── pipeline.py            # acquire_week(build=...); execute(source=...); recheck skips WeekNotCaptured;
│                          #   played-weeks history + week-0 published previous_ranks (R13)
├── schedule.py            # week_for_date: Tue–Sun week 1, then Mon–Sun; + week_range(week)
└── cli.py                 # --source, --matchups; capture path never calls _provider_from_env

tools/
├── chrome_capture.py          # per-week merge + atomic write; captured_at/week_start/week_end
└── yahoo_matchup_capture.js   # read the week's date range off the scoreboard (R9 discovery)

tests/
├── fixtures/matchups-week1.csv               # derived from yahoo_week.json for the parity test
├── unit/test_captured_load.py                # each FR-005..FR-011 defect, R2 checksum rules
├── unit/test_schedule_calendar.py            # Mon 10-26 → week 1 completed; boundaries
├── integration/test_capture_parity.py        # FR-017: normalized snapshot equality; golden page without projections (R12)
├── integration/test_capture_defects.py       # User Story 2: exit code, nothing published
├── integration/test_capture_recheck.py       # recheck absent → skipped; changed → correction; rosters carried
└── integration/test_capture_no_credentials.py  # FR-001: YAHOO_* unset, no HTTP
```

**Structure Decision**: This is a single project. The new code lives in `fetch/captured.py`, next
to `rosters.py` and `draft.py`, the two existing file-backed acquisition modules, and follows
their style: a `load` function that raises `ProviderError`/`ProjectionError` with actionable
messages.

## Implementation Order

0. **Week 0 history fix** (R13, FR-019–FR-022). Add a played-weeks helper in `pipeline.py`. Read
   week 0's `previous_ranks` from its published ranking. Use the same helper in
   `_render_archived`. Add an integration test that archives week 0 and checks week 1 rank, labels
   and movement. This comes first because it is independent and source-agnostic.
1. **Calendar.** Write the `schedule.week_for_date` fix and `week_range`, with tests.
   - This is independent of the rest and fixes the Monday-run bug first.
2. **Loader.** Write `fetch/captured.py`: the loader, validation and builder, with unit tests.
   - These tests run against hand-edited fixtures plus the real committed week 1 rows. Those rows
     pass the checksum (R2) and must fail on timing.
3. **Seam.** Make `acquire_week` take a `build` callable, and add the raw-text archive and
   quarantine to `store.py`.
   - The existing integration tests must stay green with the Yahoo builder.
4. **Wiring.** Add the `execute` source parameter and the recheck skip, plus CLI `--source` and
   `--matchups`.
5. **Capture tool.** Add the per-week merge, atomic write and new columns to `chrome_capture.py`.
   - The JS date reading needs the maintainer's browser (R9). Ship the `--week-start/--week-end`
     fallback at the same time so this step cannot block.
6. **Validation.** Write the parity test, which compares normalized snapshots and checks the
   golden `week-01.html` without projections (R12). Then run the quickstart against the real
   recaptured week 1.
7. **Docs.** Update the README's weekly chore:
   - use `dailies`;
   - capture on Monday or later;
   - the capture now defaults to the last *ended* week (R11);
   - fix the example's `--week-end 20261026`.

   Mark 004 Phase 3 as delivered by 005.

## Risks

| Risk | Mitigation |
|---|---|
| The scoreboard shows no machine-readable week dates | `--week-start/--week-end` fallback (R9) |
| Yahoo compares percentages at display precision and a near-tie appears | The checksum accepts either rule (R2) |
| G7: past weeks' matchup pages lose their totals after the week closes | Only the correction window degrades: absent rechecks are skipped (R4). Check this when week 2 opens by capturing `--week 1` again |
| The All-Star long week breaks the calendar formula | The calendar cross-check fails the run loudly and names the dates (R10). A declared week table is the follow-up |
| Roster prior absent on the API path | Out of scope (FR-018). Recorded in R5 |
| Week 0 fix changes week ≥ 1 output | Nothing ≥ 1 has been published or archived, so there is nothing to compare before/after. `ALGORITHM_VERSION` is unchanged because `rank/` is untouched (R13) |

## Complexity Tracking

No constitution violations to justify.
