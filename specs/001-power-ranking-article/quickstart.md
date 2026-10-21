# Quickstart — Validation Guide

How to prove this feature works end to end. Each scenario maps to a spec user story or a
constitution gate. This is a validation guide, not an implementation guide — no bodies here.

## Prerequisites

```bash
uv sync                      # Python 3.14 + dependencies
```

A Yahoo OAuth app (Client ID + Secret) with a one-time consent completed to obtain a refresh
token, and the league key for the 18-team league.

```bash
export YAHOO_CLIENT_ID=...        YAHOO_CLIENT_SECRET=...
export YAHOO_REFRESH_TOKEN=...    YAHOO_LEAGUE_KEY=454.l.XXXXXX
export ANTHROPIC_API_KEY=...      # optional — omit to validate the rankings-only path
export LEAGUE_TIMEZONE=America/Los_Angeles
```

---

## Scenario 1 — US1: the rankings page, no LLM involved (P1)

The MVP. Proves the page is worth publishing before any article exists.

```bash
unset ANTHROPIC_API_KEY
uv run ccsv-rumble dry-run --week 1
```

**Expect:** exit 0; a rendered page with all 18 teams ranked, each showing rank and movement; a
notable-events list; **no article section**; and a log line stating the article stage was skipped.

**Verify by hand:** open the output and confirm no power score, EMW/CAW figure, per-category
percentage, or schedule-luck number appears anywhere (FR-032, SC-010). Rank and movement are the
only computation-derived numbers permitted. The article section should be **absent entirely** —
no placeholder, no "no write-up this week" note (FR-030a).

## Scenario 2 — First run of the season, no previous ranking

```bash
uv run ccsv-rumble dry-run --week 1
```

**Expect:** every team shows a rank with movement rendered as explicitly unavailable — a dash or
"new", **not** `0` and not blank (FR-005). If no `data/projections.csv` exists, expect no ranking
at all and standings only, labeled as such (algorithm doc §4).

## Scenario 3 — US2: the article (P2)

```bash
export ANTHROPIC_API_KEY=...
uv run ccsv-rumble dry-run --week 4
```

**Expect:** exit 0, with an article present.

**Verify by hand — this is the scenario that needs human eyes:**
- Teams flagged within-noise have **no** causal explanation attached (FR-019).
- Causation is hedged — "might have", "likely" — never asserted as fact (FR-018).
- No metric name, formula, or weight appears (FR-021).
- Tone is warm and nobody is mocked (FR-023).
- Every player name and number traces to the week's events (FR-022).

## Scenario 4 — Article validation rejects a bad article

```bash
uv run pytest tests/integration/test_article_rejection.py
```

Feeds a hand-written `ArticleContent` containing a fabricated player and an attribution on a
within-noise team.

**Expect:** validation fails with both `event_traceability` and `noise_attribution` in the failure
list; the article is not published; the rejected article **is** archived with its reasons
(FR-026, FR-027).

## Scenario 5 — FR-029: degraded publish, not a suppressed run

```bash
uv run pytest tests/integration/test_article_failure_still_publishes.py
```

Simulates the Claude call raising, timing out, and returning `stop_reason: "refusal"`.

**Expect, in all three cases:** the rankings-only page publishes, exit code is **0**, and a
notification is recorded (FR-029, FR-030, SC-007). A failure here that blocks publication is a
misreading of Principle II — the constitution's "complete page is defined per feature" clause
exists for exactly this.

**Also assert the FR-030b case:** when the article fails *and* the notification itself fails, the
run exits **5**, not 0. With silent omission (FR-030a) the page carries no signal, so an
unreported degradation is invisible — that combination must not look like success.

## Scenario 6 — US3 + Principle I: replay is byte-identical and offline

```bash
uv run ccsv-rumble replay --week 4
uv run ccsv-rumble verify --week 4
```

**Expect:** `verify` exits 0. `replay` makes **no** network call and **no** model call — the
archived article is reused.

**This fixture assumes week 4 has a single archive entry.** The byte-identical guarantee is not
unconditional across entries — it holds because `replay` and `verify` both resolve the `entry_id`
recorded on the published page, not the week's latest. Scenario 12 covers the corrected case, where
`--latest` legitimately produces different output.

```bash
uv run pytest tests/integration/test_replay_offline.py
```

Patches the socket layer and the Anthropic client to raise on construction.

**Expect:** replay still succeeds. This is the test that proves the Principle I regeneration rule,
and it is the one most likely to rot as code is added — a stray import that constructs a client at
module load will fail it.

## Scenario 7 — Determinism

```bash
uv run pytest tests/unit/test_render_deterministic.py
```

Renders the same fixture snapshot twice in one process and again in a subprocess, comparing bytes.
Catches unsorted dict iteration, an unseeded shuffle, and a clock read inside `render/`.

## Scenario 8 — Ranking math on known inputs

```bash
uv run pytest tests/unit/test_allplay.py
```

Includes the 4-team, 3-category worked example from `docs/rankings-algorithm-v1.md` §2, which has
hand-computed expected values (D: CAW .667 / EMW 1.000; A: .556 / .667; B: .444 / .333;
C: .333 / .000). Also covers category ties, a zero-FTA week, and TO inversion.

If this test and the doc ever disagree, one of them is wrong — fix both together.

## Scenario 9 — Idempotency and the no-op commit

```bash
uv run ccsv-rumble run --week 4
uv run ccsv-rumble run --week 4    # immediately again
```

**Expect:** the second run completes successfully and creates **no commit** in the publish
repository, because the output is identical (Principle II). Re-running must never corrupt the
archive — the archive store refuses to overwrite an existing week.

## Scenario 10 — Secrets stay out

```bash
uv run pytest tests/unit/test_scrub.py
grep -rE '(ANTHROPIC_API_KEY|YAHOO_REFRESH_TOKEN|ghp_|sk-ant)' archive/ || echo "clean"
```

**Expect:** `clean`. Scrubbing happens on the archive write path, so no call site can forget it
(Principle V).

## Scenario 11 — Multi-week backfill with one failing article (the highest-value test)

```bash
uv run pytest tests/integration/test_backfill_multi_week.py
```

Archive has weeks 1–2; weeks 3, 4, 5 are complete upstream and missing locally. The article stage
is stubbed to fail on week 4 only.

**Expect:**
- Weeks 3, 4, 5 are fetched and archived in **ascending** order (FR-039).
- Week 4's movement compares against **week 3**, not against week 2's published ranking — getting
  this wrong is the subtle failure this test exists to catch.
- Week 4 stages rankings-only; weeks 3 and 5 stage with articles (FR-044).
- Weeks 3 and 5's articles refer to their own week in the past tense, not as "this week" (FR-041).
- **One** commit and **one** push containing all three weeks plus the index (FR-042).
- Notification lists the three backfilled weeks and week 4's article failure.

This exercises FR-039, FR-042, and FR-044 simultaneously, which is why `plan.md` flags it as the
most valuable test in the suite. If any single integration test is written first, write this one.

## Scenario 12 — Correction changes the archive but not the page

```bash
uv run pytest tests/integration/test_correction_forward_only.py
```

Week 3 is published. The provider is then stubbed to return different week-3 totals.

**Expect:**
- A new archive entry `entry-002` for week 3; `entry-001` is **untouched** (FR-046).
- Week 4's ranking computes from week 3's **corrected** data (FR-047).
- Week 3's published page is **unchanged** — no commit touches it (FR-048).
- `replay --week 3` still reproduces the published page, because it resolves `entry-001` from the
  page's recorded `entry_id` (FR-049, SC-005).
- `replay --week 3 --latest` produces *different* output, and that is correct.
- The correction is reported through the notification channel (FR-050).

Also assert the inverse: a re-fetch of an **unchanged** week creates **no** new entry. Yahoo
responses carry volatile fields, so a naive byte comparison appends a junk entry every run — this
assertion is what catches that.

## Scenario 13 — Discoverability

```bash
uv run pytest tests/unit/test_noindex.py
curl -s https://<publish-url>/robots.txt
```

**Expect:** every rendered page contains a `noindex` directive; `/robots.txt` disallows all
crawlers; no sitemap is emitted (FR-051, FR-053, SC-011). The URL check in FR-052 is a human
review item, not an automated test.

---

## Pre-merge gate summary

The constitution's six gates, as commands:

```bash
uv run pytest                                          # 1. suite green
uv run ccsv-rumble dry-run --from-archive --week 4     # 2. dry run vs archive, validation passes
git diff -- tests/golden/                              # 3. golden diffs reviewed, intentional
                                                       # 4. algorithm change: before/after
git diff | grep -iE 'sk-ant|ghp_|@gmail'               # 5. no secret or PII in the diff
uv run pytest tests/unit/test_allplay.py               # 6. ranking logic covered
```

Gate 2 uses `dry-run --from-archive`, not `replay` — the constitution's wording is "a dry run
against an archived snapshot succeeds and **its output passes validation**", and `dry-run` is the
command defined to validate and stop. Both read the archive; `dry-run --from-archive` is the CI
form.

Gate 4 has no single command — an algorithm change means running `replay` across archived weeks on
both the old and new constants and attaching the rank comparison to the PR.
