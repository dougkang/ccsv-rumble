# Data Model — Power Ranking Article Generator

Entities, fields, and the validation rules that carry constitutional or spec weight. Types are
Python dataclasses in `src/ccsv_rumble/models.py` — declarative only, no behavior.

The single most important property of this model: **`PublishableReport` has no field capable of
holding a ranking-derived number other than rank and movement.** Spec FR-032 is therefore enforced
by the type, not by template discipline.

---

## 1. Snapshot

Everything one run acquired for **one week**. Immutable once archived (Principle III). A week may
have several snapshots over time — the original plus any corrections — distinguished by `entry_id`.

| Field | Type | Notes |
|---|---|---|
| `entry_id` | `str` | `"entry-001"`, `"entry-002"`, … Monotonic within the week. **The identifier FR-049 requires a published page to record.** |
| `acquired_at` | `datetime` | When this entry was fetched |
| `supersedes` | `str \| None` | The `entry_id` this corrects; `None` for a week's first entry |
| `season` | `str` | e.g. `"2026-27"` |
| `week` | `int` | League matchup week, 1-indexed |
| `week_start`, `week_end` | `date` | Yahoo's week boundaries, in the configured timezone |
| `teams` | `list[Team]` | All 18, sorted by `team_id` |
| `category_totals` | `dict[TeamId, CategoryLine]` | The all-play grid. One entry per team |
| `matchups` | `list[Matchup]` | Who actually played whom — for real record and luck |
| `rosters` | `dict[TeamId, list[PlayerSlot]]` | For event derivation and `RosterPrior` |
| `transactions` | `list[Transaction]` | Adds, drops, trades within the week |
| `player_weeks` | `list[PlayerWeek]` | Per-player box score totals, for standout detection |
| `stat_category_map` | `dict[str, str]` | Yahoo `stat_id` → canonical category name, **read from league settings at fetch time** |
| `raw_source` | `str` | Relative path to the verbatim pre-parse JSON |

**Validation.** `len(teams) == 18`; every team present in `category_totals`; `stat_category_map`
covers all nine expected categories or the run fails loudly (research.md §1). `entry_id` must not
already exist for that week — the store creates, never overwrites.

**Which entry a computation uses.** Ranking always reads each week's **latest** entry, so
corrections feed current and future rankings (FR-047). Rendering a *replay* reads the **specific**
entry recorded on the published page (FR-049). These are different lookups and conflating them
would silently break either SC-005 or FR-047 — a `latest_entry(week)` and an `entry(week, id)`
accessor, with no default, keeps the distinction explicit at every call site.

---

## 2. CategoryLine

One team's totals for one week. The shooting categories are the subtle part.

| Field | Type | Notes |
|---|---|---|
| `pts`, `reb`, `ast`, `stl`, `blk`, `tpm` | `int` | Counting categories, higher wins |
| `to` | `int` | **Inverted** — lower wins |
| `fgm`, `fga` | `int` | Stored separately, parsed from Yahoo's composite `"FGM/FGA"` string |
| `ftm`, `fta` | `int` | Same, from `"FTM/FTA"` |
| `games_played` | `int` | Context only — not a category |

**Validation.** `fgm <= fga`, `ftm <= fta`, all values non-negative.

**No percentage fields exist.** `fg_pct` is computed at comparison time as `fgm/fga`, never stored.
A stored percentage is unaggregatable and unrecoverable once rounded — the exact failure the
algorithm doc §6 warns about.

**Comparison rules** (`rank/allplay.py`):
- Counting categories: higher value wins; equal is a tie (0.5 each).
- `to`: lower wins.
- Ratio categories: compare `made/attempted`. If both teams have 0 attempts → tie. If exactly one
  has 0 attempts → that team **loses**. Explicit branch, per research.md §8.

---

## 3. Ranking

Output of `rank/`. Pure function of `Snapshot` history + `algorithm_version`.

| Field | Type | Notes |
|---|---|---|
| `algorithm_version` | `str` | `"v1"` — required by Principle I |
| `week` | `int` | |
| `entries` | `list[RankingEntry]` | Sorted by `(-power_score, team_id)` |

### RankingEntry

| Field | Type | Notes |
|---|---|---|
| `team_id` | `TeamId` | |
| `rank` | `int` | 1–18 |
| `previous_rank` | `int \| None` | `None` when no prior ranking exists — **never 0** (FR-005) |
| `rank_change` | `int \| None` | `previous_rank - rank`; positive means improvement |
| `movement` | `Movement` | `SIGNIFICANT` \| `WITHIN_NOISE` \| `UNAVAILABLE` |
| `power_score` | `float` | Internal only |
| `emw`, `caw` | `float` | Internal only |
| `roster_prior` | `float \| None` | Internal only; `None` when no projections file |
| `performance_weight` | `float` | The `w = n/(n+3)` value in play this week — internal only |
| `category_profile` | `dict[str, float]` | Per-category all-play win rate — internal only |
| `actual_win_pct` | `float \| None` | From real matchups |
| `schedule_luck` | `float \| None` | `actual_win_pct - emw` — internal only |
| `luck_band` | `LuckBand \| None` | `VERY_LUCKY` \| `LUCKY` \| `NEUTRAL` \| `UNLUCKY` \| `VERY_UNLUCKY` — **the publishable form** |

`luck_band` is the bridge across the strict-disclosure line: it is derived from `schedule_luck` but
is a qualitative label, so it can reach the page as prose (FR-033) while the number cannot.

**Validation.** Ranks are exactly `1..18` with no gaps or duplicates. `movement` is `UNAVAILABLE`
if and only if `previous_rank is None`.

---

## 4. NotableEvent

| Field | Type | Notes |
|---|---|---|
| `event_id` | `str` | Stable, deterministic — derived from `(week, type, subject)`, not a UUID |
| `type` | `EventType` | `INJURY_STATUS` \| `TRADE` \| `ADD` \| `DROP` \| `STANDOUT_PERFORMANCE` |
| `team_ids` | `list[TeamId]` | One for most; two for a trade |
| `player_name` | `str \| None` | |
| `summary` | `str` | One factual sentence, generated by code — not by the model |
| `detail` | `dict[str, str \| int]` | Typed specifics (status change, stat line, date) |
| `occurred_on` | `date` | |

**`event_id` must be deterministic.** A UUID would change every run and break the golden-file test
and the article's `attributed_event_ids` round-trip.

**Standout performance rule** (FR-009, must be declared not subjective): a rostered player's week
qualifies when their output exceeds their own season-to-date baseline by a declared threshold in at
least one category, with a minimum games-played floor to exclude small-sample noise. Threshold
lives in `config.py`.

---

## 5. InternalReport

Archived, never published (FR-013).

| Field | Type |
|---|---|
| `snapshot_ref` | `str` |
| `ranking` | `Ranking` |
| `events` | `list[NotableEvent]` |
| `algorithm_version` | `str` |
| `constants` | `dict[str, float]` — the exact weights used, for the before/after comparison the constitution requires on algorithm changes |

---

## 6. PublishableReport

The **only** input to the article stage (FR-015) and to rendering.

| Field | Type | Notes |
|---|---|---|
| `season`, `week` | `str`, `int` | |
| `is_projection` | `bool` | True for weeks 0–2 — forces the "draft-based projection" label (algorithm doc §4) |
| `teams` | `list[PublishableTeam]` | |
| `events` | `list[PublishableEvent]` | |

### PublishableTeam

| Field | Type | Notes |
|---|---|---|
| `team_id` | `TeamId` | |
| `team_name` | `str` | |
| `manager_display_name` | `str` | League data only — no contact info (Principle V) |
| `rank` | `int` | Publishable |
| `previous_rank` | `int \| None` | Publishable |
| `rank_change` | `int \| None` | Publishable |
| `movement` | `Movement` | Drives whether attribution is permitted |
| `record` | `str` | e.g. `"6-4"` — league fact, not ranking-derived |
| `luck_band` | `LuckBand \| None` | Qualitative only |
| `category_notes` | `list[str]` | Qualitative phrases, e.g. `"among the league's best at rebounds"` |

**Deliberately absent: `power_score`, `emw`, `caw`, `roster_prior`, `performance_weight`,
`category_profile`, `schedule_luck`.** There is no field to put them in.

### PublishableEvent

`event_id`, `type`, `team_ids`, `player_name`, `summary`, `occurred_on`. Same as `NotableEvent`
minus `detail`.

---

## 7. Article

| Field | Type | Notes |
|---|---|---|
| `week` | `int` | |
| `model` | `str` | Which model produced it |
| `content` | `ArticleContent \| None` | `None` if generation failed |
| `validation` | `ValidationOutcome` | |
| `generated_at` | `datetime` | Archived; not rendered into the page body |

### ArticleContent (the structured output schema)

| Field | Type |
|---|---|
| `headline` | `str` |
| `intro` | `str` |
| `team_notes` | `list[TeamNote]` |
| `outro` | `str` |

**TeamNote**: `team_id`, `prose` (str), `attributed_event_ids` (`list[str]`).

### ValidationOutcome

| Field | Type | Notes |
|---|---|---|
| `passed` | `bool` | |
| `failures` | `list[ValidationFailure]` | `check` name + message |
| `checked_at` | `datetime` | |

Archived whether passed or rejected (FR-027).

---

## 8. State transitions

### Per week

```
            ┌─ fetch fails ────────────────────────▶ WEEK ABORTS → whole run publishes nothing
            │
Snapshot ───┼─ report validation fails ────────────▶ WEEK ABORTS → whole run publishes nothing
            │
            └─ report OK ──┬─ article OK + valid ──▶ STAGED (rankings + events + article)
                           │
                           ├─ article fails ───────▶ STAGED (rankings + events)  ─┐
                           │                                                       ├─ FR-029/044:
                           └─ article invalid ─────▶ STAGED (rankings + events)  ─┘   complete
                                                     + notify (FR-030)
```

The asymmetry is the point: a failure *before* the report blocks publication entirely, while a
failure in the optional article degrades that week's page rather than suppressing the run. Both
paths must be covered by tests (Principle II's failure-path requirement).

Note the verb change from the original design: a week reaches **STAGED**, not PUBLISHED. Nothing
reaches the publish repository until every week in the run has been staged.

### Per run

```
weeks_to_process = [gap weeks ascending] + [current week]       (FR-037, FR-039)
corrections applied to archive first                            (FR-045, FR-046)

   for each week ──▶ per-week flow above
                        │
          ┌─ any week aborted ──────────────▶ NO PUBLISH (previous site intact)
          │
          └─ all weeks staged ──▶ render index ──▶ diff vs published
                                                      │
                                      ┌─ identical ───▶ NO COMMIT              (Principle II)
                                      │
                                      └─ changed ─────▶ ONE commit, ONE push   (FR-042)
                                                        + notify backfills,
                                                          corrections, failures
```

**A correction never enters this flow as a publishable week.** It changes the archive (new entry)
and therefore changes what later rankings compute from, but it does not re-stage the corrected
week's page (FR-048). Only *missing* weeks are staged. Collapsing "week changed upstream" and
"week absent from the archive" into one code path is the most likely way to implement FR-038 and
FR-048 as a contradiction.

A run whose staged output is byte-identical to what is already published makes **no commit**,
regardless of which branches it took.

---

## 9. PublishedPage

The rendered artifact for one week. Named in the spec's Key Entities; modeled here because FR-049
gives it a field that matters.

| Field | Type | Notes |
|---|---|---|
| `season`, `week` | `str`, `int` | |
| `entry_id` | `str` | **The snapshot entry this page was built from** (FR-049). Replay resolves this exact entry, not the week's latest |
| `algorithm_version` | `str` | The version in force when published |
| `has_article` | `bool` | False → the article section is omitted entirely, with no placeholder (FR-030a) |
| `path` | `str` | Stable per-week address (FR-040) |

`entry_id` and `algorithm_version` are recorded in the page as a machine-readable comment rather
than visible text — they are provenance for the maintainer, and neither is a ranking-derived number
in the FR-032 sense (they identify *which* computation ran, not any of its values).

