# Data Model — Draft Ranking (Week 0)

**Feature**: [`002-draft-ranking-week-0`](spec.md) · **Phase 1** · 2026-10-22

Existing types in `src/ccsv_rumble/models.py` are reused wherever they fit. Two of them turn out to
fit unusually well, and two need a field added.

## What already fits

**`CategoryLine` is the projected TEAM week.** It already carries the nine categories with ratio
categories split into `fgm/fga/ftm/fta`, plus `games_played`. A *projected* team week has exactly the
shape of an observed one, which is the structural reason the all-play grid can be reused unchanged
(design document §3). No new type is needed there, and introducing one would break that reuse.

**But it cannot carry a PER-GAME projection — corrected during implementation.** `CategoryLine`'s
fields are `int`, because an observed week is a whole number of made shots. A per-game projection is
not: `8.6` FGM on `18.8` FGA are ordinary values, and storing them as ints truncates to `8` and `18`
**at the source**, before any accumulation. Measured, that turns a true `.457` FG% into `.444` — a
1.3-point error, biased consistently downward, large enough to flip a category comparison and
unrecoverable by any later rounding discipline.

So per-game projections use a separate float-valued `PerGameLine`, and the integer `CategoryLine`
appears only where it belongs: the assembled team total. Totals are accumulated in floats and
**rounded once, at the end of assembly**, never per player — which would bias totals by up to half a
unit per contributor.

`PerGameLine` mirrors `CategoryLine`'s invariants (`fgm <= fga`, `ftm <= fta`, non-negative) rather
than inheriting them, since the field types differ.

**`Snapshot` is the archive unit.** New inputs attach to it rather than forming a parallel structure.

## Additions to existing types

### `PlayerSlot` — needs position eligibility

```python
@dataclass(frozen=True)
class PlayerSlot:
    player_id: str
    name: str
    team_id: TeamId
    status: str = ""
    positions: tuple[str, ...] = ()      # NEW — raw eligibility, e.g. ("PG", "SG")
```

FR-018 requires respecting position eligibility, which is impossible without this. Defaulted to empty
so existing fixtures keep working; ingest warns when a whole roster lacks positions, since that
silently degrades slot filling into "best six players regardless of position".

**Raw positions collapse to three slot classes**, because the league's layout is `2G, 3FC, 1 Util`
rather than Yahoo's usual nine-slot arrangement:

```python
def eligible_for(slot: str, positions: tuple[str, ...]) -> bool:
    if slot == "UTIL":
        return True
    if slot == "G":
        return bool({"PG", "SG", "G"} & set(positions))
    if slot == "FC":
        return bool({"SF", "PF", "C", "F"} & set(positions))
```

A dual-eligible player (a SG-SF) satisfies both `G` and `FC`, which is the only place the assignment
order can matter — see [research.md](research.md) D4. An empty `positions` tuple is eligible for
`UTIL` only, so a roster with no position data fills one slot and leaves five unfillable, which trips
the coverage floor loudly instead of quietly mis-ranking.

### `Ranking` — must record both algorithm versions

```python
@dataclass(frozen=True)
class Ranking:
    algorithm_version: str
    week: int
    entries: tuple[RankingEntry, ...]
    draft_algorithm_version: str = ""    # NEW — "draft-v1"
```

(The new field goes last: a defaulted field cannot precede non-defaulted ones.)

FR-033 and design document §8: a rank that depends on two algorithms cannot be traced by citing one.
Both are emitted into the page's provenance comment, which is permitted because a provenance comment
is not a ranking-derived figure.

### `RankingEntry` — draft decomposition

```python
    # existing: power_score, emw, caw, roster_prior, performance_weight, category_profile …
    draft_score: float | None = None     # NEW — DraftScore, post-shrink
    emw_proj: float | None = None        # NEW
    caw_proj: float | None = None        # NEW
    unprojected_count: int = 0           # NEW — FR-025
```

All internal (FR-034). `PublishableReport` already has no field able to hold any of them, which is the
existing structural guarantee that they cannot leak; these additions deliberately do not change that.

`unprojected_count` is the one value that may also reach the page, as prose rather than a figure —
see research D6 for why FR-028 does not forbid it.

## New entities

### `PlayerProjection`

One player's expected per-game production, plus how many games they are projected to play in the
target week.

| Field | Type | Notes |
|---|---|---|
| `player_id` | `str` | must match the roster's `player_id` |
| `name` | `str` | for diagnostics only; matching is by id |
| `per_game` | `PerGameLine` | per-game expectation, FLOAT fields; ratio categories as makes and attempts |
| `projected_games` | `int` | real-schedule derived for the target week (research D2) |

**Validation**: `projected_games >= 0` on `PlayerProjection`; `fga >= fgm`, `fta >= ftm` and
non-negativity on `PerGameLine` itself. A projection supplying a percentage instead of makes and
attempts is **rejected at ingest** (FR-010), never coerced.

### `ProjectionSnapshot`

The archived input that makes a past draft ranking reproducible.

| Field | Type | Notes |
|---|---|---|
| `source_id` | `str` | which source the numbers came from (FR-011) |
| `retrieved_at` | `datetime` | when (FR-011) |
| `target_week` | `int` | the week `projected_games` refers to |
| `projections` | `tuple[PlayerProjection, ...]` | |
| `raw_source` | `str` | path to the verbatim pre-parse file, as `Snapshot` does |

**Immutable and append-only**, like every archive entry. FR-013: a later revision by the source never
alters an already-published ranking — a revision is a new snapshot used by future runs.

### `DraftResults`

| Field | Type | Notes |
|---|---|---|
| `season` | `str` | |
| `picks` | `tuple[DraftPick, ...]` | ordered |
| `is_complete` | `bool` | false → omit the article, still publish the ranking (FR-049) |

`DraftPick`: `pick_number: int`, `team_id: TeamId`, `player_id: str`, `player_name: str`.

### `LifecycleState`

```python
class LifecycleState(StrEnum):
    PRE_DRAFT = "pre_draft"
    POST_DRAFT = "post_draft"
    IN_SEASON = "in_season"
```

Plus a `reason: str` carried alongside it, because FR-008 requires recording *why* publication was
withheld. A bare enum cannot distinguish "no rosters at all" from "two teams drafted short", and those
read very differently in a log three weeks later.

## Derivation: roster + projections → projected grid

Pure, in `rank/projected.py`. Per team:

1. **Candidates** — rostered players with a projection. Players projected for **zero games** are
   excluded entirely rather than contributing zeros (FR-023), which matters because a zero-game player
   would otherwise drag ratio categories toward a false floor.
2. **Slot filling** — six slots in the declared order `G, G, FC, FC, FC, UTIL` (narrowest eligibility
   first), each taking the best *eligible* unassigned player by projected scalar value, ties by
   `(value desc, player_id asc)` (research D4). The scalar chooses contributors only; it never scores
   teams.
3. **Accumulate** — for each filled slot, add `per_game × projected_games` into a float accumulator.
4. **Round once**, at the end, into a `CategoryLine`.
5. **Unfilled slots contribute nothing** — not a league average, not a replacement level (FR-024).
6. **Count unprojected** rostered players and carry the count (FR-025).

Then the existing all-play grid runs over the 18 × 9 result unchanged, and `draft_score.py` applies
`0.5 + s · (AllPlay_proj − 0.5)`.

**Zero attempts in a ratio category** routes into the in-season algorithm's existing zero-attempt rule
rather than a new one (FR-027). This is the reason step 4 produces a `CategoryLine` rather than a
bespoke type: the existing rule already handles it, and a new type would need a parallel rule.

## State transitions

```
            rosters incomplete / absent
                      │
                      ▼
                 PRE_DRAFT ──────────── publish nothing, exit 0, no notification
                      │                 reason recorded (FR-008)
     all 18 rosters complete
                      │
                      ▼
                POST_DRAFT ──────────── week-0 page: draft ranking is the headline,
                      │                 movement unavailable, projection label
     a scored week completes
                      │
                      ▼
                 IN_SEASON ──────────── in-season ranking is the headline;
                                        draft score continues as RosterPrior,
                                        recomputed from current rosters (FR-035)
```

The transition out of `POST_DRAFT` changes which algorithm is the headline but does **not** retire the
draft computation — FR-007 and FR-035. That continuity is the reason this is one feature rather than a
week-0 special case bolted on.

## Archive layout

```text
data/<season>/
├── week-00/
│   ├── entry-001/
│   │   ├── snapshot.json
│   │   ├── projections.json      # NEW — ProjectionSnapshot
│   │   ├── draft-results.json    # NEW — DraftResults (absent → no article)
│   │   ├── raw-projections.csv   # NEW — verbatim pre-parse input
│   │   └── article.json
└── _quarantine/                  # existing: unparseable payloads
```

Week 0 uses the same entry structure as any other week, so `replay` and `verify` need no new mode —
they already address a week and an entry. A correction to projections appends `entry-002` rather than
overwriting, consistent with 001's correction rule and FR-013.
