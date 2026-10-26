# Data Model: Captured-Data League Provider

Phase 1 for [plan.md](plan.md). Downstream models (`Snapshot`, `CategoryLine`, `Team`, `Matchup`)
are **unchanged**. This feature adds one input type and one new kind of archive file.

## WeekCapture (new, `fetch/captured.py`)

Every row the matchups file holds for one week. It is parsed from CSV with no network access.

| Field | Type | Source column | Rule |
|---|---|---|---|
| `week` | int | `week` | ≥ 1 |
| `captured_at` | aware datetime | `captured_at` | required (FR-009); one value per week |
| `week_start`, `week_end` | date | `week_start`, `week_end` | required; one value per week; must equal the league calendar's range for `week` (R10) |
| `rows` | tuple[CaptureRow, ...] | — | exactly `TEAM_COUNT` rows (FR-005) |
| `raw_text` | str | — | the week's rows, re-emitted under the header, archived verbatim (FR-014) |

### CaptureRow

| Field | Type | Rule |
|---|---|---|
| `team_id` | str | appears exactly once in the week; present in the roster capture (FR-011) |
| `team_name` | str | the display name for that week (R6) |
| `opponent_id` | str | the opponent's row must name this team back (FR-007) |
| `matchup` | int | exactly two rows per value; `TEAM_COUNT / 2` distinct values (FR-005) |
| `fgm, fga, ftm, fta, tpm, pts, reb, ast, stl, blk, to` | int | integer, non-negative, not blank (FR-006); made ≤ attempted |
| `fg_pct_display`, `ft_pct_display` | str | checksum only; may be `-` when attempts are 0 |
| `cat_wins` | float | whole or half (`4`, `4.5`); equals the category wins recounted from the totals, under either percentage rule and either tie convention (FR-008, R2) |

### Validation order

Checks run cheapest and most specific first, so the first failure names the real defect:

1. Header has every required column.
2. Rows exist for the requested week. If not, raise `WeekNotCaptured`.
3. Each row parses: FR-006 names the team and column.
4. Week metadata is consistent and present.
5. Coverage and pairing: FR-005, FR-007.
6. Team ids are known: FR-011.
7. Checksum: FR-008 names both teams.
8. Calendar agreement: R10.
9. Timing: FR-009.

Calendar agreement runs before timing. A wrong `week_end` is the root defect, and checking timing
first would report its symptom ("captured before it ended") instead.

Steps 1–7 are pure functions of the file and the roster capture. Steps 8–9 also take the league
calendar and timezone as explicit parameters, never read from a clock.

## Mapping to Snapshot

| Snapshot field | From |
|---|---|
| `teams` | one `Team(team_id, team_name, manager)` per row, sorted by id. The manager comes from the roster capture, blank if unknown |
| `category_totals` | `CategoryLine` from the integer columns, with `games_played = 0` (spec Assumptions) |
| `matchups` | `Matchup(week, min(id, opp), max(id, opp))`, deduplicated and sorted (R7) |
| `week_start`, `week_end` | from the capture |
| `rosters` | if the week is already archived: the latest entry's rosters. Otherwise: the roster capture (R5) |
| `stat_category_map` | `{}` |
| `raw_source` | `"matchups.csv"` |

## Archive entry (extended)

A capture-sourced entry holds `raw-matchups.csv` in place of `raw-yahoo.json`. Everything else
(`snapshot.json`, `internal.json`, `publishable.json`, and so on) is as before. Replay reads
`snapshot.json` only, so it needs neither the raw file nor `data/` (FR-015). If a week's capture
fails to parse, its raw text is quarantined the same way as an API payload, as
`_quarantine/<season>/week-NN-<stamp>.csv`.

## State: a week's capture over time

```
absent ──capture──▶ in-progress (captured_at ≤ week_end) ──recapture after week ends──▶ final
                         │                                                          │
                    run refuses (FR-009)                                 run archives / corrects
```

Recapturing a final week replaces its rows (FR-012). If the totals changed, the next run records a
correction (FR-016). If they didn't change, the run creates no entry.
