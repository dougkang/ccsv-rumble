# Contract: `data/matchups.csv`

The interface between the attended capture (`tools/chrome_capture.py matchups`) and the unattended
run. The capture tool writes it, and `fetch/captured.py` reads it. A change to either side must keep
to this contract.

## Shape

UTF-8 CSV with a header. **One row per team per matchup**: each side of a matchup gets its own row.
The file may hold any number of weeks.

```csv
week,matchup,team_id,team_name,opponent_id,fgm,fga,ftm,fta,tpm,pts,reb,ast,stl,blk,to,fg_pct_display,ft_pct_display,cat_wins,captured_at,week_start,week_end
1,1,t.01,Keyboard Cats,t.03,134,242,59,79,25,352,121,67,22,18,37,.554,.747,4,2026-10-26T09:12:40-07:00,2026-10-20,2026-10-25
1,1,t.03,Triton Aggies,t.01,131,297,67,84,54,383,119,74,26,13,57,.441,.798,5,2026-10-26T09:12:40-07:00,2026-10-20,2026-10-25
```

The first 19 columns are unchanged from today's capture. The last three are **new**:

| Column | Format | Meaning |
|---|---|---|
| `captured_at` | ISO-8601 datetime **with offset** | when the capture ran. Identical for every row of a week |
| `week_start` | `YYYY-MM-DD` | first scoring day, as the league displays it |
| `week_end` | `YYYY-MM-DD` | last scoring day, as the league displays it |

## Writer obligations (`chrome_capture.py`)

1. **Per-week replace (FR-012).** Keep all existing rows whose `week` differs from the captured
   week, replace that week's rows, and write the result sorted by `(week, matchup, team_id)`.
   Capturing week 2 must never remove week 1.
2. **Dates come from the league (FR-009a, research R9).** Read them from the scoreboard, or from
   `--matchup-start`/`--matchup-end` when given. If neither source provides them, refuse to write.
   Never compute them from a calendar.
3. **Existing integrity checks stay.** Each team appears once, there are `teams / 2` matchups, and
   the displayed percentage agrees with made/attempted.
4. **Atomic write.** Write to a temporary file and rename it, so an interrupted capture cannot
   leave a truncated file to be committed.

## Reader guarantees (`fetch/captured.py`)

| Condition | Result |
|---|---|
| No rows for the requested week | `WeekNotCaptured`. Skipped on recheck, a failure otherwise (research R4) |
| Missing or blank `captured_at` / `week_start` / `week_end`, or values that differ within a week | failure naming the week |
| Blank or non-integer stat | failure naming the team and column (FR-006) |
| Not exactly 18 teams, or a team twice | failure naming the missing or duplicated ids (FR-005) |
| Opponents not mutual | failure naming both teams (FR-007) |
| Team id unknown to `rosters.csv` | failure naming the id (FR-011) |
| `cat_wins` disagrees with recount | failure naming both teams and both counts (FR-008) |
| `captured_at` (league tz) on or before `week_end` | failure: "week N captured before it ended" (FR-009) |
| Dates differ from the league calendar | failure naming both ranges (research R10) |

Every failure is a `ProviderError`. `cli.py` already maps that to exit `EXIT_ACQUIRE` with nothing
published.

## Versioning

Rows written before this contract lack the three new columns. They are read, and they fail the
timing check, which is correct: they were captured mid-week. The fix is to recapture, not to
migrate.
