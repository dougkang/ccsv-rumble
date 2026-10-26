# Quickstart: validating the captured-data provider

These steps prove the feature end to end. The contracts are in
[contracts/matchups-capture.md](contracts/matchups-capture.md) and
[contracts/cli.md](contracts/cli.md).

## Prerequisites

- Chrome signed in to Yahoo, with **Allow JavaScript from Apple Events** enabled.
- Week 1 has ended. Capture on **Monday 2026-10-26 or later**. Today's file was captured Sunday
  evening and will be refused.

Every run below uses a scratch archive (`--archive`). `acquire_week` writes entries even on a dry
run, and a stray `archive/2026-27/week-01/` is easy to commit along with `data/`. To get the real
week 0 into the history, start from a copy:

```bash
rm -rf /tmp/qs-archive && cp -R archive /tmp/qs-archive
```

## 1. Recapture week 1, with rosters

```bash
uv run python tools/chrome_capture.py dailies --week 1
head -3 data/matchups.csv   # must show captured_at, week_start=2026-10-20, week_end=2026-10-25
```

## 2. Run with no Yahoo credentials

```bash
env -u YAHOO_CLIENT_ID -u YAHOO_CLIENT_SECRET -u YAHOO_REFRESH_TOKEN -u YAHOO_LEAGUE_KEY \
  uv run ccsv-rumble dry-run --archive /tmp/qs-archive --no-article --out /tmp/site
```

Expected:
- The log shows `league source: capture`.
- The plan targets week 1. This depends on the calendar fix: on Monday the old formula picked
  week 0.
- There are no `fantasysports.yahooapis.com` requests.
- The run exits 0, and `/tmp/site` has a week 1 page with 18 teams.

## 3. Idempotence and replay

```bash
uv run ccsv-rumble dry-run --archive /tmp/qs-archive --no-article --out /tmp/site2   # no new archive entry
diff -r /tmp/site /tmp/site2                                # identical
mv data data.off && uv run ccsv-rumble replay --archive /tmp/qs-archive --week 1 --out /tmp/replay; mv data.off data
```

The replayed week 1 page must match `/tmp/site`, with no `data/` present (FR-015).

## 4. Each defect fails loudly

The tests in `tests/integration/test_capture_defects.py` cover these. To check by hand, edit a
copy and pass `--matchups` and `--archive` (a fresh scratch copy for each):

| Edit | Expected log |
|---|---|
| delete one row | names the missing team |
| blank one `fga` | names team and `fga` |
| change one `cat_wins` | names both teams and counts |
| set `captured_at` to `2026-10-25T20:43:00-07:00` | "week 1 captured before it ended" |
| set `week_end` to `2026-10-26` | names both date ranges |
| run `--week 2` | names week 2 and the capture command |

Each must exit non-zero with nothing published.

## 5. Recapture preserves other weeks

After week 2 ends, run `chrome_capture.py matchups --week 2`. Then confirm that week 1's rows are
unchanged:

```bash
git diff data/matchups.csv
```
