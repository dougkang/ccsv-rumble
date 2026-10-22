# Contract — Draft Results

League data: the pick-by-pick record. Needed **only** by the recap article (FR-041, FR-042); the
ranking needs rosters alone.

That split is load-bearing. It means the week-0 page ships without draft results, and it means draft
results failing never costs you the ranking.

## Provider addition

Extends `LeagueDataProvider` rather than introducing a new seam — this is league data, from the same
provider as rosters and scoreboards.

```python
class LeagueDataProvider(Protocol):
    # … existing methods …
    def fetch_draft_results(self, season: str) -> dict[str, Any]:
        """Raw pick-by-pick record. Archived verbatim before parsing."""
        ...
```

## Required fields

| Need | Field | Notes |
|---|---|---|
| Pick order | `pick_number` | 1-based, contiguous |
| Acquiring team | `team_id` | must match a known team |
| Player | `player_id`, `player_name` | name is what the recap uses in prose |

**Completeness** is explicit, not inferred: `is_complete` is true only when every pick of a finished
draft is present. A partial record is treated as unavailable (FR-049), because a recap built from half
a draft board would confidently describe a draft that did not happen.

## Behaviour when absent or incomplete

FR-049: **publish the ranking, omit the article.** Not a placeholder, not an explanation — the article
section is absent entirely, consistent with 001 FR-030a.

The maintainer is notified (FR-048), because the page gives no sign anything is missing. A failed
notification is therefore a failed run, per 001's existing rule.

**This is the expected first state, not an edge case.** League-data acquisition is the subject of
`004-browser-session-provider`, whose gates are unresolved. So week 0 realistically ships
rankings-only, with the recap arriving when draft results can be read. The spec was written so that is
a complete page rather than a degraded one.

## Archiving

Archived immutably as an input (FR-042), in the week-0 entry alongside the snapshot and projections.
The recap is derived **solely** from the week-0 internal report plus these results (FR-043), and the
report must be fully determined before any prose is generated — 001's report-before-article rule.

## Article constraints this contract carries

The recap may name players, picks, and draft positions: league data, safe (FR-047). It must not:

- publish any rate or score from the ranking computation (FR-047, FR-032)
- disclose the ranking method — it must clear `DISCLOSURE_TERMS` (FR-045, FR-031)
- disparage or ridicule an identifiable member (FR-046)

The tone rule needs care here in a way it does not elsewhere, and the spec names it as an edge case:
**the genuinely funny draft story is usually someone's mistake, and the audience is a congregation
that includes that person.** Humour aimed at a pick or a roster is permitted; humour aimed at a
person's competence or character is not. The screen is mechanical, so the prompt carries the burden —
it should steer toward the roster as the subject, never the manager.

One further trap: a recap is *more accurate* if it explains why a team ranks where it does, and strict
disclosure forbids that. The prompt must be given the decomposition as **context for what is true**,
while being instructed that the mechanism itself is unpublishable. The existing disclosure screen is
the backstop, not the plan.
