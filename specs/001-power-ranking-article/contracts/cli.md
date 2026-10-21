# Contract — Command-Line Interface

The CLI is this project's only external interface. The constitution requires a single command that
performs a full run end to end with no manual steps, plus a dry-run mode and an archive-replay
mode.

## Commands

```
ccsv-rumble run      [--week N] [--season S] [--no-backfill] [--recheck-weeks N]
ccsv-rumble dry-run  [--week N] [--season S] [--from-archive] [--no-backfill]
ccsv-rumble replay   --week N [--season S] [--entry ID | --latest]
ccsv-rumble verify   --week N [--season S] [--against PATH]
```

Invoked in CI as `uv run ccsv-rumble run`.

### `run` — the weekly job

Detect gaps and corrections → acquire → archive → per-week rank/report/article/render → index →
single atomic push. See `plan.md` § Run sequence for the ordering, which is load-bearing: the
correction window must be acquired before any ranking is computed.

Defaults to processing **every** completed league week with no archived snapshot, in ascending
order, plus the most recently completed week (FR-037–039). Network access required.

| Flag | Effect |
|---|---|
| `--week N` | Process only week N. Skips gap detection — the escape hatch for re-running one week deliberately |
| `--no-backfill` | Process the current week only even when gaps exist. Gaps are still detected and reported |
| `--recheck-weeks N` | Override the correction window (default in `config.py`). `0` disables the re-check |

**Multi-week runs are all-or-nothing.** If any week fails before staging, the run publishes nothing
and the previously published site stays intact. A per-week *article* failure is not such a failure —
that week stages rankings-only and the run continues (FR-044).

### `dry-run`

Identical to `run` through render and validation, then **stops before publishing**. Writes rendered
output to a local directory and prints a summary. Satisfies the constitution's dry-run requirement.

Without `--from-archive` it performs the live fetch and the Claude call, so it exercises the real
path. With `--from-archive` it sources both from the archive instead — no network, no model — which
is the form the constitution's pre-merge gate 2 names ("a dry run against an archived snapshot
succeeds and its output passes validation") and the form CI should run.

### `replay` — regeneration from archive

Renders a past week from its archive and **runs the same report and HTML validation as `run`**.
Makes no network calls and invokes no model (Principle I's regeneration rule). Fails if the archive
for that week is incomplete rather than silently falling back to a live fetch.

**Which entry it reads matters.** A week may hold several snapshot entries after a correction
(FR-046). `replay` defaults to the entry recorded on the published page, which is what makes
SC-005 true. `--entry <id>` renders a specific entry, and `--latest` renders the newest — useful
for seeing what a corrected week *would* have looked like, but its output is **not** expected to
match what was published.

`replay` and `dry-run --from-archive` overlap deliberately: `replay` is the operator command for
reproducing a past page, `dry-run --from-archive` is the CI gate. Both read the archive and
validate; neither publishes.

### `verify`

Replays a week and compares the result byte-for-byte against what is published. Exits non-zero on
any difference. This is the operator-facing form of the golden-file test and the mechanism behind
SC-005.

**It resolves the published page's recorded `entry_id`**, exactly as `replay` does by default. It
must **never** compare against the week's latest entry: on a corrected week that would report a
difference on every invocation, since the page was legitimately built from an earlier entry
(FR-048, FR-049). `verify` therefore takes no `--entry` or `--latest` flag — comparing a
non-published entry against the published page is not a meaningful check.

Requires read access to the `pages` branch, so it needs `GITHUB_TOKEN` — or `--against <path>` to
compare against a local checkout of that branch instead, which is the offline form.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success — published, or correctly made no commit because output was unchanged |
| `1` | Acquisition failure (fetch, auth, timeout) — nothing published |
| `2` | Report generation or validation failure — nothing published |
| `3` | Render or HTML validation failure — nothing published |
| `4` | Publish failure (push rejected, auth) — page may be stale, previous page intact |
| `5` | Notification failure on a run that had something to report — a degraded article (FR-030), backfilled weeks (FR-043), or a detected correction (FR-050). The site shipped correctly but nobody was told |

Codes 1–4 all leave the previously published site live and untouched (Principle II). In a
multi-week run, a failure in **any** week yields the corresponding code and publishes nothing.

Code `5` exists because of the silent-omission decision (FR-030a): with no on-page signal, an
unreported event is invisible, so FR-030b makes a successful publish plus a failed notification a
non-success. It is **scoped to runs with something to report** — a clean run with nothing to say
emits no notification and exits `0`. Backfills and corrections are included alongside article
failures because all three are states a reader cannot see from the page.

**Article failure is not an error code.** Per FR-029 a failed or rejected article means the run
publishes the rankings-only page and exits `0`, having filed a notification (FR-030). Exiting
non-zero there would make a successful degraded publish look like a failed run.

## Environment

| Variable | Required | Purpose |
|---|---|---|
| `YAHOO_CLIENT_ID` | yes | OAuth2 app credential |
| `YAHOO_CLIENT_SECRET` | yes | OAuth2 app credential |
| `YAHOO_REFRESH_TOKEN` | yes | Long-lived; access tokens derived per run |
| `YAHOO_LEAGUE_KEY` | yes | e.g. `454.l.XXXXXX` |
| `ANTHROPIC_API_KEY` | no | Absent → article stage skipped, rankings-only page published |
| `PUBLISH_BRANCH` | no | Branch to publish to; defaults to `pages`. Same repository as the code |
| `GITHUB_TOKEN` | yes for `run`, `verify` | Supplied automatically by GitHub Actions. Scoped to this repository and rotated per run — **no stored PAT is needed**, because the publish target is a branch of the same repo. `verify --against <path>` avoids needing it |
| `LEAGUE_TIMEZONE` | no | IANA name; defaults to the value in `config.py`. Never the host's local time |

No credential may appear in argv — process arguments are visible to other processes and land in CI
logs. Secrets are environment-only.

**Publishing writes to a branch, not another repository.** `publish` pushes the staged site to
`PUBLISH_BRANCH` (an orphan branch with no shared history with `main`). The workflow that invokes
`run` MUST trigger only on `schedule` and `workflow_dispatch` — adding a `push` trigger would make
the publish step retrigger the workflow indefinitely.

## Output discipline

Human-readable progress on stdout; errors on stderr. The run logs enough to answer, after the fact,
whether it ran, what it fetched, whether it published, and why not if it did not
(constitution: Observability). **Logs are scrubbed of credentials on the write path**, not by
convention.
