# Contract: CLI source selection

Added to `run` and `dry-run`. `replay` and `verify` are unaffected, because they read the archive
only.

| Option | Default | Meaning |
|---|---|---|
| `--source {capture,yahoo}` | `capture` | league data source for weeks ≥ 1, one per run (FR-002, FR-003) |
| `--matchups PATH` | `data/matchups` | the snapshot directory (a single file is also accepted); ignored with `--source yahoo` |

| `--allow-in-progress` | off | **dry-run only.** Preview `--week N` from its latest snapshot even if the week has not ended |

## Behaviour

- **`--source capture`**
  - `YAHOO_*` variables are not read. Their absence is not an error (FR-001).
  - The roster capture (`--rosters`) is required for weeks ≥ 1. If it is missing, the run fails
    and names the file.
  - The run logs `league source: capture (data/matchups), weeks [..]`, then the snapshot chosen for each week (FR-004).
- **`--source yahoo`**: exactly today's behaviour (FR-018).
- **Week 0 only**: neither source is constructed. This is unchanged.
- **`--allow-in-progress`**:
  - requires `--week N` and `--source capture`;
  - skips only the "captured before it ended" check, and logs a warning in its place;
  - runs against a scratch copy of the archive, so the real archive is never written.
  - Not accepted by `run`: an archived in-progress week would be superseded by the final capture only
    as a correction, and corrections are never republished.

## Exit codes

Unchanged. Every capture defect is `EXIT_ACQUIRE`, sends a failure notification, and publishes
nothing.

## Workflow

`.github/workflows/weekly.yml` needs no change. Without `--source`, the run uses capture.
