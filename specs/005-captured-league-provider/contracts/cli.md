# Contract: CLI source selection

Added to `run` and `dry-run`. `replay` and `verify` are unaffected, because they read the archive
only.

| Option | Default | Meaning |
|---|---|---|
| `--source {capture,yahoo}` | `capture` | league data source for weeks ≥ 1, one per run (FR-002, FR-003) |
| `--matchups PATH` | `data/matchups.csv` | the capture file; ignored with `--source yahoo` |

## Behaviour

- **`--source capture`**
  - `YAHOO_*` variables are not read. Their absence is not an error (FR-001).
  - The roster capture (`--rosters`) is required for weeks ≥ 1. If it is missing, the run fails
    and names the file.
  - The run logs `league source: capture (data/matchups.csv), weeks [..]` (FR-004).
- **`--source yahoo`**: exactly today's behaviour (FR-018).
- **Week 0 only**: neither source is constructed. This is unchanged.

## Exit codes

Unchanged. Every capture defect is `EXIT_ACQUIRE`, sends a failure notification, and publishes
nothing.

## Workflow

`.github/workflows/weekly.yml` needs no change. Without `--source`, the run uses capture.
