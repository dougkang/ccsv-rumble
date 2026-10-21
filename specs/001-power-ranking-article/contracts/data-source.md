# Contract — Data Source Provider

The constitution requires the fetch layer be isolated behind an interface so the provider can be
replaced without touching ranking or rendering code. This is that interface, plus the field-level
requirements any provider must satisfy.

## Provider protocol

```python
class LeagueDataProvider(Protocol):
    def fetch_week(self, season: str, week: int) -> RawWeek: ...
    def fetch_stat_category_map(self, season: str) -> dict[str, str]: ...
    def fetch_rosters(self, season: str, week: int) -> RawRosters: ...
    def fetch_transactions(self, season: str, week: int) -> RawTransactions: ...
```

Each method returns **raw, unnormalized provider data**, which is archived verbatim before any
parsing (Principle III). Normalization into `Snapshot` is a separate, pure step — so a provider
swap changes one module and the normalizer, and nothing downstream.

## Required fields — non-negotiable

A provider that cannot supply these cannot support the algorithm.

1. **Per-week, per-category totals for all 18 teams.** Not just the caller's own matchup. All-play
   is impossible without the full grid — this is the single hardest requirement and the first thing
   to verify against any new provider.
2. **FG and FT as makes and attempts.** Never as a percentage. A rounded percentage cannot be
   re-aggregated or compared correctly, and the information is unrecoverable afterward.
3. **Week boundaries** matching how the platform defines a matchup week.
4. **The actual schedule** — who played whom — for real record and schedule luck.
5. **Current rosters** for event derivation.
6. **Historical weeks addressable**, so a missed run can be backfilled (FR-038) and a completed
   week can be re-fetched to detect upstream corrections (FR-045). Yahoo satisfies this via
   `week={n}`; a provider without it cannot support either requirement.

## Yahoo implementation notes

| Need | Endpoint |
|---|---|
| Category map | `GET /fantasy/v2/league/{league_key}/settings` → `stat_categories` |
| Weekly grid + schedule | `GET /fantasy/v2/league/{league_key}/scoreboard;week={week}` (includes `team_stats`) |
| Per-team fallback | `GET /fantasy/v2/team/{team_key}/stats;type=week;week={week}` |
| Rosters | `GET /fantasy/v2/team/{team_key}/roster;week={week}` |
| Transactions | `GET /fantasy/v2/league/{league_key}/transactions` |

### Two traps specific to Yahoo

**1. Shooting stats are composite strings.** `stat_id` `9004003` carries `FGM/FGA` and `9007006`
carries `FTM/FTA` as a single `"made/attempted"` value. The parser must split on `/` and coerce
both halves to `int`. A parser that assumes numeric stat values fails on exactly the two categories
whose information cannot be reconstructed later. Handle the empty/`"-"` case (a team with no
attempts) explicitly rather than letting it raise.

**2. Never hardcode `stat_id` values.** The IDs above come from community sources and are not
authoritative. Read the mapping from `league/settings` every run and **assert all nine expected
categories resolve**, failing the run loudly if any is missing. Hardcoded IDs are how this breaks
silently in a future season or a re-created league.

### Auth

OAuth 2.0. `YAHOO_REFRESH_TOKEN` is the stored secret; exchange it for a short-lived access token
at the start of each run. One-time interactive consent obtains the refresh token; everything after
is unattended.

### Re-fetching completed weeks for corrections

FR-045 requires re-fetching the last *N* completed weeks every run. Mechanically this is the same
`scoreboard;week={n}` call as the original acquisition — there is no "changed since" parameter, so
detection is by comparison, not by query.

**Compare normalized data, not raw bytes.** Yahoo responses carry volatile fields that differ
between two fetches of an unchanged week — request-scoped identifiers, timestamps, ordering. A raw
byte comparison would report a correction every single run and append a useless archive entry each
time. `archive/diff.py` compares the **normalized** `CategoryLine` values plus rosters and
transactions, and only those; a difference there is a real correction.

Request cost stays flat: *N* extra scoreboard calls per run, where *N* is the window, not the
season length.

### Resilience

Every call sets an explicit timeout and a bounded retry count (constitution: no indefinite
retries). Exhausted retries are a Principle II failure — report and publish nothing. A descriptive
User-Agent is set on every request.

A backfill of many weeks means many sequential requests in one run. Those must be paced and share
the same retry budget — a long outage must not turn the recovery run into a burst that Yahoo
rate-limits, which would leave the archive gapped for another week.

## Fixture requirement

The test suite must include a captured raw Yahoo response as a fixture, with team and manager names
replaced by placeholders, so parser tests run offline and the real league's data is not committed
into the test corpus.
