# Contract — Article Stage

The one nondeterministic stage. Its contract is written to make the spec's constraints
*mechanically checkable* rather than matters of prompt discipline.

## Signature

```python
def generate_article(report: PublishableReport, client: Anthropic) -> Article: ...
```

`generate_article` accepts **only** `PublishableReport` (spec FR-015). `InternalReport` must not be
importable from the `article` package path — if the model never receives the component metrics, it
cannot leak them no matter how the prompt is worded.

## Input

The publishable report, exactly as defined in [data-model.md](../data-model.md) §6. Notably it
carries **no numeric ranking metric** — no power score, no EMW/CAW, no schedule-luck figure. What
it does carry for each team: rank, previous rank, rank change, a `movement` flag, the real record,
a qualitative `luck_band`, and qualitative `category_notes`.

## Output schema (structured)

The call sets `output_config.format` to a `json_schema`. The model returns:

```json
{
  "headline": "string",
  "intro": "string",
  "team_notes": [
    { "team_id": "string", "prose": "string", "attributed_event_ids": ["string"] }
  ],
  "outro": "string"
}
```

**Why structured rather than prose.** Checking free prose for fabricated facts means parsing prose.
With `attributed_event_ids` as a first-class field, the two highest-risk spec requirements collapse
into set operations:

- **FR-022 (traceability)**: `attributed_event_ids ⊆ {e.event_id for e in report.events}`
- **FR-019 (no attribution for noise)**: for any team whose `movement` is `WITHIN_NOISE` or
  `UNAVAILABLE`, `attributed_event_ids` must be empty

Both are deterministic, unit-testable, and immune to phrasing.

## Prompt requirements

The system prompt must establish, at minimum:

| Requirement | Spec ref |
|---|---|
| Never state or imply how the ranking is computed — no formula, metric names, weights, or component scores | FR-021 |
| Express causation as plausible, not established — "might have", "likely reflects" | FR-018 |
| For a team flagged within-noise, say there is no clear driver rather than inventing one | FR-019, FR-020 |
| Use no number that is not present in the input report | FR-022, FR-034 |
| Warm, good-humored tone; never demean, mock, or make personal remarks about a league member | FR-023 |
| Refer to people only by team name or manager display name present in the data | FR-024 |
| For a quiet week, say the week was quiet | Edge case |
| Refer to the week by its number and in the **past tense** when it is not the current week | FR-041 |

**Backfilled weeks need the week in the prompt.** A backfill generates one article per missing week
(FR-038), each from that week's own `PublishableReport`. The signature needs no change —
`PublishableReport` already carries `week` — but the prompt must *use* it, and must state whether
this is the current week or a backfilled one. Without that, a page for week 3 published three weeks
late opens with "this week" and reads as though it were current, which is exactly what FR-041
forbids.

Two notes on prompt construction. First, **state the tone requirement positively** — describing the
desired voice works better than enumerating prohibitions. Second, the model is being asked to be
*uncertain* about causation, which is the opposite of its default pull toward a confident
explanation; that instruction needs to be explicit and is worth a worked example in the prompt.

## Call configuration

Per [research.md](../research.md) §4: `claude-opus-5`, adaptive thinking (on by default),
`max_tokens` 16000, `output_config.format` set to the schema above, and `fallbacks: "default"`
with beta `server-side-fallback-2026-07-01`.

**Check `stop_reason` before reading `content`.** A refusal returns HTTP 200 with
`stop_reason: "refusal"` and possibly empty content — indexing `content[0]` unconditionally would
crash the run. A refusal is handled as an article failure, not a crash: the run publishes
rankings-only per FR-029.

Assistant-turn prefill is rejected on this model, so `output_config.format` is the only supported
way to constrain output shape. That is the chosen route regardless.

## Validation (pure)

```python
def validate_article(content: ArticleContent, report: PublishableReport) -> ValidationOutcome: ...
```

No network, no model. Checks:

| Check | Rule |
|---|---|
| `event_traceability` | Every `attributed_event_ids` entry exists in the report |
| `noise_attribution` | Non-significant movers have no attributions |
| `team_coverage` | Every `team_id` in `team_notes` exists in the report; no duplicates |
| `no_disclosure` | Prose contains no metric name, formula fragment, or weight-like decimal. Pattern list in `config.py` |
| `no_foreign_numbers` | Numerals in prose match a value present in the report |
| `no_pii` | No email, phone, or URL patterns |
| `tone` | No term from a declared disallowed-language list |
| `non_empty` | Headline, intro, and outro all non-empty; `team_notes` covers all 18 teams |

A failure of any check means the article is **rejected and not published** (FR-026). The rejected
article and its failure list are still archived (FR-027).

`no_foreign_numbers` and `no_disclosure` are heuristics and will have false positives — a team
named "Fantastic Four", a prose phrase like "a .500 week". They must be tuned against real output,
and because a false positive costs only a rankings-only page for one week, they should err strict.

**One false positive is guaranteed, not hypothetical:** `PublishableTeam.record` is a single string
like `"6-4"`, and prose will naturally read "at 6-4 they…". A naive numerals-in-prose scan sees `6`
and `4` as two unmatched numbers. The check must decompose `record` into its component values when
building the set of permitted numbers — along with `rank`, `previous_rank`, `rank_change`, and any
numeral inside an event `summary` or `detail`.

## Replay

On `replay`, the archived article is read and reused. No client is constructed and no call is made
(Principle I). A test asserts this by patching the SDK to raise if instantiated.
