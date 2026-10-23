# Contract — Projection Source

The only input in this project that originates outside the league. FR-015 requires it be isolated
behind the same kind of interface as league data, so the source can be replaced without touching
ranking or rendering.

## Provider protocol

```python
class ProjectionProvider(Protocol):
    def fetch_projections(self, season: str, target_week: int) -> dict[str, Any]:
        """RAW, unnormalized projection data. Archived verbatim before parsing."""
        ...

    def source_id(self) -> str:
        """Stable identity of the source, recorded with the snapshot (FR-011)."""
        ...


class ProjectionError(RuntimeError):
    """Acquisition or validation failure. Per FR-038: publish nothing, exit non-zero, notify."""
```

Same shape as `LeagueDataProvider`: raw out, normalization separate and pure. Swapping sources changes
this module and the normalizer, nothing downstream.

## Required fields — non-negotiable

A source that cannot supply these cannot support the algorithm.

1. **All nine scoring categories, per player, per game.** Not a composite rating, not a positional
   rank, not a single z-score total. The category profile is the main reason the week-0 page is worth
   publishing, and it does not exist if the input is a scalar.
2. **FG and FT as makes and attempts.** Never as a percentage. This is the go/no-go on any source.
3. **Projected games for the target week, per player** (research D2), derived from the real schedule
   rather than a league-average constant (FR-017).
4. **A player identifier that matches the league provider's roster ids.** Name matching is a fallback
   for diagnostics only — a league with two players of the same surname will silently mis-attribute
   production otherwise.

## The percentage trap — reject, never derive

**A source publishing `FG%` instead of `FGM/FGA` must be refused at ingest with an explicit error.**

This is worth stating twice because the tempting workaround is wrong. Given a percentage and nothing
else, attempts are unrecoverable: `.458` is consistent with `11/24` and `22/48`, which aggregate
differently into a team week. Inferring attempts from minutes or shot-rate estimates would make the
two categories that the category profile most depends on quietly fictional.

FR-010 therefore makes this a rejection rather than a degradation. The run fails loudly; it does not
publish eight-ninths of a ranking.

## Input format

The chosen source (research D1) is a maintainer-curated local file. Declared schema:

```csv
player_id,name,positions,projected_games,pts,reb,ast,stl,blk,tpm,to,fgm,fga,ftm,fta
nba.p.1234,A. Player,"PG,SG",4,24.1,4.2,6.8,1.1,0.4,2.9,2.4,8.6,18.8,4.1,4.7
```

| Column | Type | Validation |
|---|---|---|
| `player_id` | str | required; must match a roster id |
| `name` | str | diagnostics only |
| `positions` | str | comma-separated; empty permitted but warned |
| `projected_games` | int | `>= 0`; `0` excludes the player (FR-023) |
| `pts … to` | float | per-game; `>= 0` |
| `fgm, fga, ftm, fta` | float | per-game; `fga >= fgm`, `fta >= ftm` |

Counting categories are per-game floats, accumulated and rounded once at the end of assembly rather
than per player — see [data-model.md](../data-model.md).

**Rejections** (each a `ProjectionError`, each publishing nothing):

- a `fg_pct` / `ft_pct` / `fg%` / `ft%` column present instead of makes and attempts
- `fga < fgm` or `fta < ftm`
- a missing `projected_games` column
- a negative value anywhere
- coverage below either threshold in `config.py` (FR-026)

## Archiving

The raw file is archived verbatim before parsing (Principle III), alongside a parsed
`ProjectionSnapshot` recording `source_id` and `retrieved_at` (FR-011). The pair must be sufficient to
recompute the ranking offline with no network (FR-012).

An unparseable input goes to `_quarantine/` rather than becoming an archive entry, reusing the
mechanism added for league data — the archive's invariant that every entry is complete still holds,
and the evidence needed to fix the parser survives.

## Revisions

Sources revise numbers daily. FR-013: a revision never alters an already-published ranking. A new
snapshot is archived as a new entry and feeds **future** runs only, exactly as a league-data correction
does.

This is why replay must read the snapshot rather than the live file. Today's implementation reads the
file at rank time, so editing it changes the result of replaying a past week — the defect FR-011 and
FR-012 exist to close.

## Resilience

Not applicable to a local file, but specified so a future networked source inherits it: explicit
timeout, bounded retries, exhausted retries are a publication failure rather than a reason to proceed
with partial data (FR-014). Access must comply with the source's terms (FR-015).

## Fallback ladder

If no compliant source can be produced, in order (design document §6):

1. **Draft-slot prior** — build the prior from where each player was actually drafted. Zero external
   dependency. **Strictly inferior**: a scalar with no category structure, so punt-build identification
   and the whole category profile are lost.
2. **Publish no ranking** until the in-season algorithm has data. A confidently wrong week-0 ranking is
   worse for a casual audience than an absent one.
