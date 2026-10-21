# Feature Specification: Power Ranking Article Generator

**Feature Branch**: `main` (no feature branch created — no `before_specify` git hook is registered)

**Created**: 2026-10-17

**Status**: Draft — clarifications resolved, ready for planning

**Input**: User description: "build an power ranking article generator that uses the power ranking algorithm defined in @docs/rankings-algorithm-v1.md. the approach should involve two parts: 1. generating a simple report containing power rankings, comparison vs previous ranking, as well as any notable events such as injuries, trades, great performances from players. 2. the second part will generate the article itself using an LLM. for each team, identify which of the notable events might have caused the change in power ranking. we should never reveal our power ranking algorithm."

## Clarifications

### Session 2026-10-20

- Q: When a scheduled run is missed entirely, what should the next run do about the unprocessed week? → A: Auto-backfill and publish retroactively (option B) — fetch and archive the missing weeks, and publish a page for each
- Q: If Yahoo revises a past week's box scores after that week's page is published, should the system update anything? → A: Re-check a bounded window and correct forward only (option B) — corrections feed current and future rankings; already-published pages are left as published
- Q: Should the published page be discoverable by search engines, given that it names real members of a congregation? → A: Unlisted and not indexed (option C) — `noindex` plus a non-guessable URL
- Q: When an article fails and the page publishes with rankings only, should the page say anything about the missing write-up? → A: Silent omission (option A) — the article section is simply absent, with no placeholder or explanation

## User Scenarios & Testing *(mandatory)*

### User Story 1 - League member checks where their team stands (Priority: P1)

A member of the league opens the page and sees the current 1–18 power rankings, how each team
moved since the last update, and a short factual list of what happened in the league this week —
injuries, roster moves and trades, and standout player performances.

**Why this priority**: This is the whole product in its minimum form. The rankings table and the
events list are the durable value; the written article is commentary layered on top. If the
article never ships, this page is still worth publishing every week.

**Independent Test**: Run the generator against a league data snapshot and confirm the rendered
page shows a complete 18-team ranking, per-team movement versus the previous published ranking,
and a notable-events list — with no article present and no LLM involved at any point.

**Acceptance Scenarios**:

1. **Given** a snapshot with a previously published ranking, **When** the report is generated,
   **Then** every team shows its current rank, its previous rank, and the change between them.
2. **Given** the very first run of the season with no previous ranking, **When** the report is
   generated, **Then** every team shows a rank with movement explicitly marked as unavailable
   rather than as zero or a blank.
3. **Given** a week in which a rostered player recorded an unusually strong statistical week,
   **When** the report is generated, **Then** that performance appears in the notable-events list
   attributed to the team that rostered them.
4. **Given** a team whose rank moved within the noise threshold, **When** the report is generated,
   **Then** that team's movement is classified as not significant.

---

### User Story 2 - League member reads the weekly write-up (Priority: P2)

The same member reads a short written article covering the week: who rose, who fell, and which of
the week's notable events plausibly explain each meaningful move. The article reads like a person
wrote it, never states the ranking formula, and never claims more certainty about cause than the
evidence supports.

**Why this priority**: This is what makes people come back and argue, but it depends entirely on
the P1 report existing first. It is also the only part that can fail in an open-ended way.

**Independent Test**: Feed a fixed, hand-written report artifact to the article stage and confirm
it produces prose that references only facts present in that artifact, attributes causes only for
teams flagged as significant movers, and contains no formula, metric name, weight, or constant.

**Acceptance Scenarios**:

1. **Given** a report where a team fell several places and lost a starter to injury that week,
   **When** the article is generated, **Then** the article links that fall to that injury in
   hedged language rather than asserting it as established fact.
2. **Given** a report where a team's movement is classified as not significant, **When** the
   article is generated, **Then** the article does not invent a cause for that team.
3. **Given** any report, **When** the article is generated, **Then** the article contains no
   metric names, numeric weights, formula descriptions, or component scores from the ranking
   method.
4. **Given** an article that references a player, number, or transaction absent from the input
   report, **When** validation runs, **Then** the article is rejected and not published.

---

### User Story 3 - Maintainer audits a past week (Priority: P3)

The maintainer picks a past week, regenerates that week's page from the archive with no network
access, and gets a page identical to what was published — including the article text as it ran
that week.

**Why this priority**: Required by the project constitution and the only way to settle a dispute
about a past ranking, but it delivers no week-to-week value to readers.

**Independent Test**: Archive a run, then regenerate from that archive offline and compare the
output byte-for-byte against what was published.

**Acceptance Scenarios**:

1. **Given** an archived run, **When** the page is regenerated from that archive offline,
   **Then** the output is byte-identical to the published page and no language model is invoked.

---

### Edge Cases

- **First run of the season / pre-draft**: no previous ranking exists and no games have been
  played. Movement is unavailable and the ranking is projection-based.
- **Article stage fails** (unavailable, times out, or returns unusable output): see FR-029.
- **Article fails fact validation**: treated identically to a generation failure.
- **No notable events at all** in a quiet week: the article must be able to say so rather than
  manufacture drama.
- **Every team within the noise threshold**: the article attributes no causes and says the week
  was quiet at the top.
- **Tied power scores**: ranking order must be deterministic and the tie must not present as
  arbitrary movement on the next run.
- **A team's movement is significant but no notable event plausibly explains it**: the article
  must report the move without attributing a cause.
- **An event affects a team that did not move**: the event is still listed; no causal claim is made.
- **Run produces output identical to what is already published**: nothing is republished.
- **One or more weeks were missed**: the run backfills them in ascending order and publishes a page
  for each, labeled with its own week (FR-037–044).
- **A backfilled week's article fails**: that week publishes rankings-only and the backfill
  continues; one bad week does not abort the rest.
- **Many weeks missed at once** (a long outage): all are backfilled in one atomic push, so a
  partially-filled archive is never published.
- **A correction changes a past week's standings**: the corrected data is archived as a new entry
  and used going forward, the published page for that week is left untouched, and the maintainer is
  notified (FR-045–050).
- **A correction arrives for a week older than the re-check window**: not detected. Accepted
  tradeoff of a bounded window — late corrections to distant weeks do not move current rankings
  enough to justify re-fetching the season every week.

## Requirements *(mandatory)*

### Functional Requirements

**Part 1 — Deterministic report**

- **FR-001**: System MUST compute power rankings using the algorithm declared in
  `docs/rankings-algorithm-v1.md`, recording the algorithm version alongside the results.
- **FR-002**: System MUST produce the report as a pure function of its input snapshot, invoking no
  language model and performing no network access during report generation.
- **FR-003**: System MUST rank all 18 teams with a deterministic, documented tie-break so that
  identical inputs always yield identical ordering.
- **FR-004**: System MUST compare each team's current rank against the previous published ranking
  and record the change.
- **FR-005**: System MUST mark movement as unavailable, not zero, when no previous ranking exists.
- **FR-006**: System MUST classify each team's movement as **significant** or **within normal
  variation** against a declared, documented threshold.
- **FR-007**: System MUST identify notable events for the period, covering at minimum: player
  injury and availability changes, completed trades, notable roster additions and drops, and
  standout individual player performances.
- **FR-008**: System MUST attribute each notable event to the affected team or teams.
- **FR-009**: System MUST define "standout performance" by a declared, documented rule rather than
  by subjective judgment, so the same week always yields the same set.
- **FR-010**: System MUST produce the report in a structured, machine-readable form.
- **FR-011**: System MUST archive each run's report immutably, per the project's archive
  principle.

**Part 1b — Two views of the report**

- **FR-012**: System MUST emit two distinct report artifacts from each run: an **internal report**
  and a **publishable report**.
- **FR-013**: The internal report MUST retain full ranking detail — component metrics, weights,
  and intermediate values — for debugging and reproducibility. It MUST be archived and MUST NOT
  be published.
- **FR-014**: The publishable report MUST contain only facts permitted to appear on the public
  page: team ranks, rank movement, movement significance, notable events, and **qualitative**
  descriptors derived from internal metrics (for example, a flag that a team has faced the
  league's easiest schedule). It MUST exclude every numeric component metric, power score,
  weight, constant, and formula element.
- **FR-015**: The article stage MUST receive only the publishable report. It MUST NOT have access
  to the internal report.

**Part 2 — Article generation**

- **FR-016**: System MUST generate a written article from the publishable report using a language
  model.
- **FR-017**: For each team classified as a significant mover, the system MUST attempt to identify
  which notable events plausibly explain the movement.
- **FR-018**: The article MUST express causal attribution as plausible, not established —
  consistent with the request to identify what "might have caused" a change.
- **FR-019**: The article MUST NOT attribute a cause to a team whose movement is classified as
  within normal variation.
- **FR-020**: The article MUST be permitted to state that a team's movement has no clear driver,
  and MUST do so rather than inventing one.
- **FR-021**: The article MUST NOT disclose the ranking method: no formula, no metric names, no
  weights or constants, no component scores, and no description of how inputs are combined.
- **FR-022**: Every player name, team name, number, and transaction appearing in the article MUST
  be traceable to the publishable report.
- **FR-023**: The article MUST maintain a warm, good-humored tone appropriate to a church league,
  and MUST NOT demean, mock, or make personal remarks about any league member.
- **FR-024**: The article MUST NOT reference any person other than by the team name or manager
  display name present in the league data, and MUST NOT include personal information about league
  members.

**Validation and publishing**

- **FR-025**: System MUST validate the generated article before publishing, checking at minimum:
  no disclosure of ranking internals (FR-021), full factual traceability (FR-022), no causal
  attribution for non-significant movers (FR-019), and tone constraints (FR-023, FR-024).
- **FR-026**: System MUST reject an article that fails any validation check and MUST NOT publish
  it.
- **FR-027**: System MUST archive each generated article — including rejected ones, with the
  reason for rejection — so that runs are reproducible and failures diagnosable.
- **FR-028**: When regenerating from an archived run, the system MUST reuse the archived article
  and MUST NOT invoke a language model.
- **FR-029**: A page consisting of rankings and notable events **without** an article is defined
  as complete and publishable. If article generation or validation fails, the system MUST publish
  the rankings-only page rather than suppressing the run entirely.
- **FR-030**: System MUST record and surface article generation failures even though the run still
  publishes, so repeated silent degradation is visible.
- **FR-030a**: When no article is published, the page MUST omit the article section entirely — no
  placeholder, no explanatory note, no carried-forward article from a prior week. The page gives
  the reader no indication that an article was expected.
- **FR-030b**: Because FR-030a leaves the page itself silent, the notification channel is the
  **only** signal that an article failed. The notifications required by FR-030, FR-043, and FR-050
  are therefore load-bearing reliability features, not conveniences, and a run MUST NOT be
  considered successful if it published a degraded page without emitting its notification.
- **FR-031**: System MUST NOT publish when the report itself cannot be generated or fails
  validation; the previously published page remains live.

**Disclosure limits (strict)**

- **FR-032**: The published page MUST show only team rank, rank movement, notable events, and
  narrative prose. It MUST NOT display any numeric value derived from the ranking computation —
  including power scores, component metrics, per-category strength figures, and schedule-luck
  figures.
- **FR-033**: Schedule luck and similar insights MUST be expressed qualitatively in prose when
  published at all (for example, "the league's easiest run of opponents so far"), never as a
  number, because the published figure would otherwise expose a ranking component directly.
- **FR-034**: Rank and rank movement are the only numbers permitted on the page that originate
  from the ranking computation. Factual numbers from league data — a player's rebound total, a
  trade date — remain permitted.

**Publication mode**

- **FR-035**: The weekly run MUST publish without human review or approval. No holding state or
  approval queue is part of this feature.
- **FR-036**: Because publication is unattended, the validation gates in FR-025 are the sole
  safeguard on article content and MUST block publication of any article failing them.

**Missed weeks and backfill**

- **FR-037**: System MUST detect gaps in the archived week history on every run — any league week
  that has completed but has no archived snapshot.
- **FR-038**: System MUST backfill each missing week by fetching, archiving, ranking, generating an
  article for, and publishing a page for that week.
- **FR-039**: Backfill MUST process missing weeks in **ascending week order**, so each backfilled
  week's movement compares against the week immediately preceding it rather than against the most
  recent published ranking.
- **FR-040**: The published site MUST make every week addressable at its own stable location, in
  addition to a current-week view. Retroactive publication is impossible without per-week
  addresses.
- **FR-041**: A backfilled page MUST be labeled with the week it describes and MUST NOT present
  itself as current. Its article MUST refer to that week in the past tense rather than as "this
  week".
- **FR-042**: A run that backfills MUST publish every affected page in a **single atomic push**,
  consistent with the all-or-nothing publishing rule — either all backfilled weeks and the current
  week land, or none do.
- **FR-043**: System MUST report which weeks were backfilled through the configured notification
  channel, so a silently recurring gap is visible.
- **FR-044**: FR-029 applies **per week** during backfill: if a backfilled week's article fails or
  is rejected, that week publishes as a rankings-only page and the backfill continues to the next
  week rather than aborting.

**Upstream stat corrections**

- **FR-045**: Each run MUST re-fetch the most recent *N* completed weeks, where *N* is a declared,
  documented constant, to detect upstream revisions.
- **FR-046**: Changed upstream data MUST be archived as a **new entry** for that week, never
  overwriting the existing entry — consistent with the append-only archive rule.
- **FR-047**: Corrected data MUST be used for the current week's ranking computation and all
  subsequent ones, so rankings going forward reflect the best available numbers.
- **FR-048**: A correction MUST NOT cause an already-published page to be republished. Published
  pages record what was true at publication time.
- **FR-049**: Every published page MUST record which archived snapshot entry it was built from, so
  that regeneration reproduces that page rather than a newer corrected version of the same week.
- **FR-050**: Detected corrections MUST be reported through the configured notification channel,
  so a correction that changes a past week's standings is visible to the maintainer even though no
  page changes.

**Discoverability**

- **FR-051**: Every published page MUST carry a `noindex` directive, and the site MUST serve a
  `robots.txt` disallowing all crawlers.
- **FR-052**: URL obscurity MUST NOT be treated as a protection. The publish repository is public
  and its name may reference the league; the enforced safeguards are FR-024 (no personal
  information beyond league display names) and FR-051 (crawler directives). Moving to a private
  repository or a neutral domain later is an enhancement, not a requirement.
- **FR-053**: The site MUST NOT publish a sitemap, and MUST NOT be linked from any indexed page.

**Note on what this does and does not buy.** `noindex` keeps the *served page* out of search
results. It does not and cannot cover the publish repository, which is public — once populated,
the same rendered HTML is browsable and indexable on github.com. This was weighed and accepted on
2026-10-21: the content is team names, manager display names, scores, and good-natured prose, and
the alternative (a paid plan for a private repository) was judged not worth it for this league.

The practical consequence is that **FR-024's no-PII rule is the real protection, and carries more
weight under this choice, not less.** Nothing about the address or the crawler directives is a
security boundary. Content must be safe to read by anyone who finds it.

**Note on the intended divergence.** FR-047 and FR-048 together mean the archive may hold corrected
data for a week whose published page still shows the original numbers. This is deliberate: the
published record is historical, the archive is authoritative. FR-049 is what keeps both claims true
at once. Backfill (FR-038) publishes a **missing** week; correction (FR-048) never republishes an
**existing** one — these are different cases and must not be collapsed in implementation.

### Key Entities

- **Snapshot**: everything one run fetched — per-team weekly category totals for all 18 teams,
  rosters, transactions, player availability, schedule, and box scores. Immutable once archived.
- **Ranking Result**: the ordered 18 teams with power scores, movement versus previous, movement
  significance classification, and the algorithm version used.
- **Notable Event**: a dated, typed occurrence (injury, trade, add/drop, standout performance)
  attributed to one or more teams, with the factual detail needed to write about it.
- **Internal Report**: Ranking Result plus full component detail. Archived, never published.
- **Publishable Report**: rankings, movement, significance flags, and notable events, stripped of
  all ranking internals. The sole input to article generation.
- **Article**: generated prose for one run, with its validation outcome. Archived whether
  published or rejected.
- **Published Page**: the static output for **one week** — rankings, notable events, and the
  article when one passed validation. Each week has its own stable address; a current-week view
  points at the most recent one (FR-040).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A league member can tell where their team ranks and whether it rose or fell within
  10 seconds of opening the page.
- **SC-002**: 100% of factual claims in a published article are traceable to that run's
  publishable report — zero invented players, numbers, or transactions across a full season.
- **SC-003**: Zero published articles disclose any element of the ranking method.
- **SC-004**: Zero published articles attribute a cause to a team whose movement was within normal
  variation.
- **SC-005**: Regenerating any archived week reproduces that week's published page exactly,
  including when later corrections to that week exist in the archive.
- **SC-006**: The weekly run completes end to end without manual intervention in at least 95% of
  weeks across the season.
- **SC-007**: When article generation fails, the page still publishes with rankings and events
  100% of the time.
- **SC-008**: A reader can identify at least one concrete reason for each significant mover
  without needing to know how the ranking is computed.
- **SC-009**: Zero published articles contain content that demeans or makes personal remarks about
  a league member.
- **SC-010**: Zero numbers derived from the ranking computation, other than rank and rank
  movement, appear on any published page.
- **SC-011**: The published site instructs every search engine not to index it, and publishes no
  sitemap — verifiable by inspecting the published page's crawler directives and `/robots.txt`.
- **SC-012**: A missed week is backfilled and published by the next successful run 100% of the
  time, so the published record has no permanent gaps.

## Assumptions

- **The run is weekly, not daily.** The page updates once per league matchup week. This also
  matches the algorithm: category totals are only meaningful at week boundaries, so a daily run
  would have been recomputing rankings from partial, mid-week data.
- **Strict disclosure.** Nothing numeric from the ranking computation is published. The
  computation still produces component metrics internally; they live only in the archived
  internal report. Insights that depend on them reach the page as prose, never as figures.
- **Report before article.** The two parts are sequential stages: the report is fully determined
  before any prose is generated, and the article is derived solely from it.
- **Article generation is an acquisition step, not a rendering step.** Because a language model is
  not reproducible, its output is treated like fetched data: generated once, archived immutably,
  and replayed from the archive thereafter. This keeps rendering deterministic and keeps the
  ranking computation pure.
- **Both constitution prerequisites are satisfied.** Constitution **v2.0.0** (2026-10-18) amended
  Principle I so the byte-identical guarantee applies to rendering while a nondeterministic
  acquisition stage is permitted provided its output is archived and replayed, and changed the
  cadence from daily to weekly throughout. Principle II also gained the clause defining "complete"
  per feature, which is what makes FR-029's rankings-only page legal rather than an exception.
- **`docs/rankings-algorithm-v1.md` has been updated** (§3 and §5) to match the strict disclosure
  decision recorded in FR-032–034, so planning does not inherit a design doc that contradicts
  this spec.
- **Notable events come from league data**, not from an external news feed — player availability
  status, transactions, and box scores are all league-side. No sports-news integration is assumed.
- **Standout performances are computed**, by comparing a player's output in the period against
  their own established baseline, rather than curated by hand.
- **Movement significance needs a declared threshold.** In an 18-team league with recency-weighted
  inputs, most small rank changes are noise. Without this gate the article would manufacture a
  causal story for all 18 teams every week, which is the main way this output would read as
  machine-generated filler.
- **One article per run**, covering the league as a whole rather than one article per team.
- **Model choice, hosting, and prompt design are planning decisions**, deliberately unspecified
  here.
- **The site is multi-page.** Publishing retroactively (FR-038) requires per-week addresses
  (FR-040), so the output is a set of per-week pages plus a current-week view, not a single page.
  This is a change from the original single-page assumption and affects the render and publish
  stages in `plan.md`.
- **The publish repository name is now constrained**, not merely unrecorded: FR-052 requires it be
  non-guessable from the league, church, or member names. This narrows the open
  `TODO(PUBLISH_TARGET)` decision rather than leaving it fully free.
- **Data source is the Yahoo Fantasy Sports API**, resolved in [research.md](./research.md) §1.
  Yahoo supplies the full 18-team weekly category grid the algorithm requires, exposes FG and FT
  as makes and attempts rather than percentages, and addresses historical weeks — so a missed week
  can be backfilled.
- **The league has not drafted yet**, so early runs will be projection-based and must be labeled
  as such per the algorithm doc §4.
