# Feature Specification: Browser-Session Data Source

**Feature Branch**: `worktree-browser-acquisition` (no feature branch created — no `before_specify` git hook is registered)

**Created**: 2026-10-21

**Status**: Draft — clarifications resolved. **Blocked on a constitution amendment** (see Constitution
Alignment). Feasibility unconfirmed by design (see Discovery Gate); Phase 0 may proceed in parallel.

**Input**: User description: "Browser-session acquisition provider for Yahoo Fantasy. The OAuth app path is blocked by a 403 that is a property of the registered application rather than the account, so acquisition switches to authenticating as the league member via a browser-minted session credential, driven by the existing httpx client with no browser in CI. This revises the provider named in 001's contracts/data-source.md without changing ranking, reporting, rendering, or publishing. Feasibility is not yet established: the browser surface must be confirmed to supply FG and FT as made/attempted rather than a rounded percentage, and to cover all 18 teams in one response, before the provider can be built. The session credential expires on a timescale of days to weeks, which conflicts with the constitution's requirement that the weekly trigger need no interactive input or local developer machine."

**Depends on**: [`001-power-ranking-article`](../001-power-ranking-article/spec.md) — this feature adds an
acquisition path and revises that feature's
[`contracts/data-source.md`](../001-power-ranking-article/contracts/data-source.md). It does not change
its ranking, reporting, rendering, validation, or publish stages.

**Resolves**: the constitution's `TODO(DATA_SOURCE)`, which requires the provider decision to be made
through this workflow rather than ad hoc.

## Why this feature exists

Acquisition is blocked. Yahoo returns `403` for every fantasy endpoint — including `game/nba`, which
touches no league — because the refusal is a property of the **registered application**, not of the
account. Token refresh still returns `200`, so authentication looks healthy right up to the first
real request.

Critically, **that permission is gated behind Yahoo's review of the application**, not behind a
setting the maintainer can change. The 403 is therefore normally a pending approval with no
committed timeline and no guarantee of being granted. Separately, a refresh token issued before
approval keeps its original grant and keeps returning 403 until the consent flow is re-run.

So this is not a workaround for a misconfiguration. While approval is pending — or permanently, if
it is refused — authenticating as the league member is the only acquisition path available. No page
has ever been published from live data: `data/` is empty.

A browser session removes the registered app from the path entirely, because the Yahoo Fantasy web
app authenticates **as the league member**. There is no app grant left in the causal chain to fail.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Establish whether the browser surface can carry the algorithm (Priority: P1)

Before any provider is built, the maintainer confirms from their own browser that the data the
algorithm needs is actually present on a Yahoo web surface, and captures a sample of it.

**Why this priority**: Two facts can invalidate the entire feature, and both are cheap to check and
expensive to discover late. This story is the go/no-go for everything below it, and it delivers value
on its own: either a confirmed target with a captured fixture, or early knowledge that this path is
dead and the fallback applies.

**Independent Test**: Run the discovery recorder against the live league page and read its verdict.
Delivers a decision plus a saved payload, with no provider code in existence.

**Acceptance Scenarios**:

1. **Given** the maintainer is signed in to Yahoo and viewing the league, **When** discovery runs
   across the scoreboard and stats views, **Then** each candidate response is reported with its team
   count, whether shooting arrives as made/attempted, and whether a past week is addressable.
2. **Given** a candidate response carries `18/42`-style values inside stat objects, **When** the
   verdict is produced, **Then** shooting is reported as confirmed and the payload is available to
   save as a test fixture.
3. **Given** a candidate response carries shooting only as a decimal such as `.458`, **When** the
   verdict is produced, **Then** that surface is reported as unusable rather than passing, and the
   reason names the loss of made/attempted as unrecoverable.
4. **Given** a response contains a made/attempted-shaped value that is in fact a date or a win-loss
   record, **When** the verdict is produced, **Then** it is reported as unconfirmed rather than
   confirmed, and the matched samples are shown for inspection.
5. **Given** no candidate satisfies all 18 teams in one response, **When** the verdict is produced,
   **Then** the shortfall is reported explicitly as blocking.

---

### User Story 2 - The weekly page publishes again (Priority: P1)

The scheduled weekly run acquires the full league grid using a credential the maintainer minted once
in their browser, and publishes the page exactly as before.

**Why this priority**: This is the outcome the league actually sees, and the reason the feature
exists. Without it the site stays empty.

**Independent Test**: With a stored credential and a confirmed surface, run the existing weekly
command end to end and confirm a published page equivalent to what the OAuth path would have
produced.

**Acceptance Scenarios**:

1. **Given** a valid stored credential and a confirmed surface, **When** the weekly run executes,
   **Then** per-week per-category totals for all 18 teams are acquired, archived verbatim, ranked,
   and published in one atomic push.
2. **Given** the same week is acquired twice, **When** the second run completes, **Then** no second
   archive entry is created for unchanged data and no commit is made to the publish branch.
3. **Given** past weeks are missing from the archive, **When** the run executes, **Then** those weeks
   are backfilled in ascending order and the correction window is re-fetched, exactly as the existing
   pipeline does.
4. **Given** acquisition succeeds, **When** the archive is inspected, **Then** the entry records
   which acquisition path produced it, so a mixed-provenance archive stays unambiguous.
5. **Given** a published page and its archive entry, **When** that week is replayed offline, **Then**
   it reproduces byte-identically with no network access.

---

### User Story 3 - A dead credential is obvious and harmless (Priority: P2)

When the stored session expires, the run fails loudly, leaves the live page untouched, and tells the
maintainer what to do.

**Why this priority**: Expiry is not an edge case here, it is the expected steady state. The
constitution's "leave the good page up and complain loudly" rule is what makes a short-lived
credential tolerable rather than dangerous.

**Independent Test**: Run with a deliberately invalid credential and confirm nothing publishes, the
exit is non-zero, and a notification names the cause and the fix.

**Acceptance Scenarios**:

1. **Given** an expired credential, **When** the run attempts acquisition, **Then** it fails before
   any ranking or rendering work, publishes nothing, exits non-zero, and notifies.
2. **Given** an expired credential, **When** the upstream answers with a redirect to a sign-in page,
   **Then** that redirect is treated as a hard authentication failure and never followed or parsed.
3. **Given** an expired credential, **When** the upstream answers `200` with a sign-in page body,
   **Then** that body is rejected rather than normalized as league data.
4. **Given** an authentication failure, **When** the failure is handled, **Then** it is not retried,
   because a credential cannot become valid again within one run.
5. **Given** a failed run, **When** the live site is checked, **Then** the previously published page
   is unchanged.

---

### User Story 4 - Re-minting the credential is quick and verified (Priority: P2)

When the credential dies, the maintainer replaces it in about a minute and knows immediately whether
the replacement works.

**Why this priority**: This recurring chore is the entire cost of the approach. If it is slow or
gives no confirmation, the feature degrades into a weekly source of doubt.

**Independent Test**: Capture a fresh credential, verify it, and confirm a subsequent run succeeds.

**Acceptance Scenarios**:

1. **Given** a freshly captured credential, **When** it is verified against the acquisition surface,
   **Then** the result states plainly whether it authenticates, without printing the secret.
2. **Given** a captured credential that does not authenticate, **When** verification runs, **Then**
   nothing is stored, so a known-bad credential never silently replaces a working one.
3. **Given** verification succeeds, **When** the stored credential is written, **Then** it is written
   outside version control with owner-only permissions.
4. **Given** verification is pointed at the real acquisition surface rather than a page navigation,
   **When** it passes, **Then** it has demonstrated the credential works for the request the run will
   actually make.

---

### Edge Cases

- **Credential expires mid-run**, between the fetch of week 4 and week 5 in a backfill. Partial
  acquisition must not be archived as complete, and the run must fail rather than publish a page
  built on a truncated history.
- **Shooting silently degrades to a percentage** after a Yahoo redesign. Normalization must refuse a
  value it cannot split into made and attempted rather than coercing it to zero or storing a rounded
  figure that cannot be re-aggregated.
- **Fewer than 18 teams** appear in a response — a surface that silently returns only the viewing
  manager's matchup. The run must fail rather than rank a partial grid, since all-play is undefined
  without the full grid.
- **A category stops resolving** because the surface renames or drops it. All nine must resolve or
  the run fails loudly; identifiers must never be hardcoded.
- **A historical week is rejected** while the current week succeeds, breaking backfill and the
  correction window but not the current page.
- **The upstream rejects the request's declared identity**, where the session is only honored for a
  request resembling the browser that minted it. This collides with the existing contract requirement
  that every request carry a descriptive User-Agent.
- **A long backfill becomes a burst** after an outage, and gets rate-limited into leaving the archive
  gapped for another week.
- **The archive holds entries from both acquisition paths** across a season, and a reader cannot tell
  which produced a given week.
- **A captured discovery payload containing real member names** is committed to the test corpus.

## Requirements *(mandatory)*

### Functional Requirements

**Contract conformance** — the requirements any provider must satisfy, inherited from 001:

- **FR-001**: Acquisition MUST supply per-week, per-category totals for all 18 teams from the league
  as a whole, not only the requesting member's matchup.
- **FR-002**: Acquisition MUST supply field goals and free throws as makes and attempts, never as a
  percentage, and MUST fail the run rather than store a rounded value.
- **FR-003**: Acquisition MUST supply the matchup schedule, so real record and schedule luck remain
  derivable.
- **FR-004**: Acquisition MUST supply current rosters for event derivation.
- **FR-005**: Historical weeks MUST be individually addressable, so a missed week can be backfilled
  and a completed week re-fetched to detect upstream corrections.
- **FR-006**: The category mapping MUST be read from league settings on every run, and all nine
  expected categories MUST resolve or the run MUST fail loudly. Identifiers MUST NOT be hardcoded.
- **FR-007**: Raw acquired payloads MUST be archived verbatim before any parsing, and MUST be
  sufficient to regenerate that week's page with no network access. A payload that fails to parse
  MUST be preserved as evidence rather than discarded, and MUST NOT be written as a regular archive
  entry, so the archive's invariant that every entry is complete still holds. This mechanism already
  exists and this feature is its first real beneficiary — see the Integration Plan.

**Authentication and failure handling**:

- **FR-008**: The session credential MUST be supplied at runtime from the environment or a secret
  store, and MUST NOT appear in either repository, in archived data, in generated HTML, or in logs.
- **FR-009**: The run MUST verify the credential before performing any acquisition work, so a dead
  credential fails before partial state exists.
- **FR-010**: A redirect to a sign-in destination MUST be treated as a hard authentication failure.
  It MUST NOT be followed, and its destination MUST NOT be parsed as league data.
- **FR-011**: A success status carrying a sign-in page body MUST likewise be rejected, since the
  upstream signals a dead session this way rather than with an error status.
- **FR-012**: An authentication failure MUST NOT be retried within a run, because a credential's
  validity cannot change between attempts. Transient faults and rate limiting MUST retry within the
  existing bounded budget.
- **FR-013**: Any acquisition failure MUST abort before ranking, publish nothing, leave the live page
  untouched, exit non-zero, and emit a notification naming the cause and the remedy.
- **FR-014**: Requests MUST set an explicit timeout and MUST be paced, so a multi-week backfill does
  not become a burst.

**Provenance and selectability**:

- **FR-015**: Each archive entry MUST record which acquisition path produced it, so an archive
  spanning both paths is unambiguous.
- **FR-016**: The acquisition path MUST be selectable at runtime without code changes, and the
  existing application-credential path MUST remain available, so a restored app grant is a
  configuration change and rollback costs nothing.
- **FR-017**: Switching paths MUST NOT alter ranking, reporting, rendering, validation, or
  publishing, and MUST NOT require changes outside the acquisition layer and its normalizer.

**Maintainer workflow**:

- **FR-018**: The maintainer MUST be able to capture a credential from their browser and verify it
  against the real acquisition surface, with the result reported without disclosing the secret.
- **FR-019**: A credential that fails verification MUST NOT be stored, so a bad one cannot replace a
  working one.
- **FR-020**: A stored credential MUST be written outside version control with owner-only
  permissions.
- **FR-021**: Discovery MUST grade the made/attempted finding by evidence strength rather than as a
  yes/no, since patterns such as dates and win-loss records are indistinguishable from shooting
  values by shape alone.

**Testing**:

- **FR-022**: The test suite MUST include a captured raw payload as a fixture, with member and team
  names replaced by placeholders, so parser tests run offline and real member data never enters the
  test corpus.
- **FR-023**: The authentication failure path MUST be tested to show that it does not publish.
- **FR-024**: Replay from an archived entry MUST be tested to confirm it performs no acquisition.

### Key Entities

- **Session credential**: proof that requests are made on behalf of a league member. Short-lived,
  supplied at runtime, never persisted to either repository. Distinct from an application credential
  in that it carries no app grant and therefore cannot be refused for lacking one.
- **Acquisition path**: a named, selectable way of obtaining raw league data. More than one may exist
  simultaneously; exactly one is active per run and is recorded on every archive entry it produces.
- **Discovery verdict**: the per-candidate record of whether a surface satisfies the contract —
  team coverage, shooting evidence and its strength, and historical addressability.
- **Raw payload**: the verbatim pre-parse response for one week, archived immutably and sufficient
  for offline regeneration.

## Discovery Gate

This specification deliberately does not assert that the browser surface works. Two facts gate
implementation, and until both are confirmed against the live league no provider should be written:

| Gate | Requirement | Consequence if unmet |
|---|---|---|
| **G1** | Shooting available as makes and attempts | Surface is unusable; FR-002 unsatisfiable |
| **G2** | All 18 teams in one response | Surface is unusable; FR-001 unsatisfiable |
| G3 | Historical weeks addressable | Current week only; backfill and correction window lost |
| G4 | A structured response rather than only markup | Workable but a more brittle parse target |
| G5 | Minimum credential set | Larger stored secret than necessary |
| G6 | Required request identity | Possible conflict with the descriptive User-Agent requirement |

G1 is checked first: it is the cheapest fact that invalidates the most work.

User Story 1 and its tooling are complete and committed. The gates are unresolved only because they
require a signed-in browser session against the live league, which the maintainer must perform.

## Integration Plan — connecting this as the data source

*Included at the maintainer's request. This is plan-phase material that `/speckit-plan` would
normally own; it is recorded here so the wiring is agreed before implementation and should be
migrated or refined when the plan is produced.*

### Where it attaches

The acquisition seam already exists and was built for exactly this. `LeagueDataProvider`
(`src/ccsv_rumble/fetch/provider.py`) is a Protocol returning raw payloads; normalization into a
snapshot is a separate pure step; and the provider is constructed in exactly one place,
`cli.py:_provider_from_env`. Nothing in `rank`, `report`, `render`, or `publish` is touched, which is
what makes FR-017 verifiable rather than aspirational. The existing architecture test already asserts
the pure packages cannot import the acquisition layer.

### Phases, each with a gate

**Phase 0 — Discovery (complete, gates open).** The recorder and capture tooling are committed. The
maintainer runs discovery against the live league and records the verdict for G1–G6 in this
directory's research notes. *Gate: G1 and G2 both confirmed, or the fallback in Assumptions applies
and this feature stops here.*

**Phase 1 — Fixture.** Save a confirmed payload, scrub member and team names to placeholders, and
commit it as a test fixture (FR-022). Every later phase is developed offline against it. *Gate: a
scrubbed fixture exists and contains no real member data.*

The quarantine behaviour added in `0d93e14` is what makes this phase recoverable, and this feature
is the case it was written for: *"the payload most likely to break the parser is the first real
response from Yahoo, which cannot be reproduced from a fixture written against documentation."*
A first live acquisition that fails to parse therefore leaves the payload on disk to be turned into
a fixture, instead of discarding the one artifact needed to fix the parser. A browser surface has no
published schema at all, so this applies more strongly here than it did to the documented API.

**Phase 2 — Parsers, offline.** Extend the normalizer for the confirmed payload shape. If the shape
carries stat objects, the existing pure helpers in `fetch/yahoo.py` — the made/attempted splitter,
the category-map builder, the team-stat extractor — are reused rather than duplicated, since they
already encode both Yahoo traps. If the shape differs, new pure parse functions are added alongside
them and the shared contract assertions are factored out so neither path can skip them. *Gate: unit
tests over the fixture pass, including the refusal cases in FR-002 and FR-006, with no network.*

**Phase 3 — Provider.** Add a module implementing `LeagueDataProvider` over the session credential,
using the existing HTTP client, timeout, pacing, and bounded-retry settings. Authentication failures
are classified and not retried (FR-010 through FR-012), mirroring the lesson already recorded for the
`403`: a permission state cannot change between attempts within a run. *Gate: failure-path test shows
an authentication failure publishes nothing (FR-023).*

**Phase 4 — Selection and provenance.** Make the path selectable by environment variable, defaulting
to the existing application-credential path so the default stays as it is today and the new path is
opted into (FR-016). Record the active path on each archive entry; the existing per-entry source
field carries this with no schema change (FR-015). *Gate: both paths constructible; archive entries
distinguishable; replay test still shows no acquisition (FR-024).*

**Phase 5 — Preflight and operations.** Verify the credential once at the start of a run before any
acquisition (FR-009). Add the credential to the scheduled job's secrets. Document the re-mint
procedure beside the existing setup notes. *Gate: a run with a deliberately invalid credential fails
before ranking, publishes nothing, exits non-zero, and notifies.*

**Phase 6 — First live run.** Dry-run, inspect the rendered page, then publish. *Gate: a replay of
the published week reproduces it byte-identically.*

### Rollback

Flip the selection variable back to the application-credential path. No code revert, no archive
surgery — entries already carry their provenance. If a published page is wrong, revert the commit on
the publish branch, which the constitution already defines as the rollback mechanism and which does
not require reverting generator code.

### What this plan deliberately does not do

- It does not remove the application-credential path. The app grant may yet be fixed, and keeping
  both makes that a configuration change.
- It does not introduce a browser into the scheduled job. The browser mints the credential once,
  locally; the run uses the HTTP client already in the dependency set. Adding a browser engine would
  need justification against a named requirement under the project's dependency-restraint rule, and
  a step that happens once locally is not one.
- It does not change the published artifact. The page, its validation, and its weight budget are
  unaffected.

## Constitution Alignment

This feature satisfies the constitution in most respects and conflicts with it in exactly one, which
is recorded here rather than resolved.

**Aligned**: the credential is a runtime secret from the environment, which Principle V contemplates
explicitly by naming cookies alongside tokens and API keys. Acquisition failure resolves toward
leaving the good page up and complaining loudly, per Principle II. Raw payloads are archived before
parsing, per Principle III. Ranking and rendering stay pure and untouched, per Principle I. No
runtime dependency is added, per dependency restraint. The provider stays behind an interface, as the
data-source constraint requires.

**In conflict**: the operational constraint that *"the weekly trigger MUST be automated and MUST
require no interactive input or local developer machine."* A browser-minted session expires on a
timescale of days to weeks, where an application refresh token does not. That makes a recurring
manual re-mint a standing condition of this approach, not an incident.

**Resolution — amendment, not exception.** The maintainer has decided this is resolved by amending
the constitution rather than by recording a per-PR exception, on the governance section's own
reasoning that a recurring exception is evidence the principle needs amending. The condition here
recurs by design.

Two consequences follow, and both constrain this feature:

1. **The amendment is a separate PR.** The amendment procedure requires it be proposed as a PR
   *"editing this file alone"*, with the version bump, the rationale, and a migration note for work
   in flight. It therefore cannot be bundled with this specification.
2. **This feature is blocked until that amendment merges.** Until then, a browser-session provider
   requiring periodic manual renewal is non-compliant, and the constitution directs a reviewer to
   block a non-compliant change. Phase 0 discovery is unaffected — it reads data in a browser and
   adds no scheduled behaviour — so the gates can be resolved in parallel.

The amendment is drafted on a separate branch. Its intended shape: keep unattended *operation* as
the requirement, and permit a credential to require periodic interactive renewal where the provider
offers no long-lived alternative, conditioned on documented renewal cadence, Principle II failure
behaviour on expiry, out-of-band verifiability before the next scheduled run, and the existing
prohibition on credential values reaching either repository, archived data, output, or logs.

**The version bump is a maintainer decision and is not assumed.** The versioning policy places
*"whether the change relaxes a constraint or tightens it"* under MAJOR, and permitting what was
previously forbidden does flip compliance judgments — which argues for MAJOR. Against that, MAJOR is
written about *"a principle"* and its central guarantee, and scheduling is an operational constraint
rather than one of the five numbered principles, which argues for MINOR. The amendment PR states the
case and leaves the choice to the maintainer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A weekly page is published from live league data, which has not happened to date.
- **SC-002**: Every published week can be reproduced from its archive with no network access, and
  reproduces identically.
- **SC-003**: All 18 teams and all nine categories are present in every archived week, or that week
  is absent and reported — never partially present.
- **SC-004**: No run ever publishes a page built on data that failed a contract check.
- **SC-005**: Replacing an expired credential takes under five minutes from noticing the failure
  notification, and the maintainer knows whether the replacement works before the next scheduled run.
- **SC-006**: A failed acquisition leaves the previously published page byte-identical.
- **SC-007**: No credential value appears in either repository, in archived data, in generated pages,
  or in logs, verified as a pre-merge gate.
- **SC-008**: Switching acquisition paths requires no change outside the acquisition layer and its
  normalizer, and no ranking or rendering output changes as a result.
- **SC-009**: Published pages remain within the existing page-weight budget and accessibility
  requirements, which this feature does not affect.

## Assumptions

- **The league member can see the data in a browser.** The maintainer is a member of the league and
  already views these pages; nothing here reaches data not already visible to that account.
- **Volume stays negligible.** One league, a handful of paced requests per week, under the existing
  pacing and bounded-retry rules. Access must comply with the provider's terms, as the constitution
  requires.
- **The application-credential path is retained, not replaced** (FR-016). It costs little to keep and
  the app grant may be repaired independently.
- **The existing pipeline is unchanged.** Gap detection, the correction window, archiving, ranking,
  article generation, rendering, validation, and publishing are all reused as built.
- **Expiry is detected reactively, not predicted.** The run fails on a dead credential and notifies;
  no attempt is made to forecast expiry or warn before it happens. Principle II already makes the
  reactive failure safe, and a predictive canary would add a scheduled job to save at most one stale
  week. Revisit if expiry proves frequent enough to be disruptive.
- **Discovery output is treated as sensitive.** A captured payload carries real team and manager
  names; it is scrubbed before becoming a fixture and is not committed raw.
- **Fallback if the gates fail**: confirmed by the maintainer — if no surface supplies made/attempted
  for all 18 teams, the fallback is maintainer-assisted capture: the data is obtained in the browser
  and supplied to the existing archive-replay path, which already exists and is tested. This trades
  unattended operation for a correct page. Reconstructing team totals from player-level box scores
  was considered and rejected as liable to diverge from the platform's official totals.

## Dependencies

- `001-power-ranking-article` — the pipeline, archive, ranking, rendering, and publish stages, and
  the data-source contract this feature revises.
- The quarantine behaviour for unparseable payloads (`0d93e14`), which Phase 1 relies on.
- **A constitution amendment permitting periodic interactive credential renewal.** Blocking for
  implementation; not blocking for Phase 0 discovery.
- The maintainer's signed-in browser session, for discovery and for each credential mint.
- The scheduled job's secret store, for the credential at run time.
- No new runtime dependency.

## Out of Scope

- Changing the ranking algorithm, the published page, or its validation.
- Running a browser in the scheduled job.
- Supporting a provider other than Yahoo.
- Predicting credential expiry before it happens.
- Repairing the application grant, which is independent and may proceed in parallel.

## Clarifications

### Session 2026-10-21

- Q: The weekly credential expires in days to weeks, conflicting with the rule that the weekly
  trigger require no interactive input or local developer machine. Record a Constitution exception
  on this feature's PR, or amend the constitution? → A: **Amend the constitution.** The condition
  recurs by design rather than once, and the constitution's own governance section holds that a
  recurring exception is evidence the principle needs amending rather than repeated waiving.
  The amendment must be proposed as a PR editing `.specify/memory/constitution.md` **alone**, per
  the amendment procedure, and therefore cannot ride along with this specification. **This feature
  is blocked on that amendment merging** — see Constitution Alignment below.

- Q: If discovery shows no surface supplies shooting as makes and attempts for all 18 teams, what is
  the fallback? → A: **Maintainer-assisted capture.** The data is obtained in the browser and
  supplied to the existing archive-replay path, which is already built and tested. This trades
  unattended operation for a correct page. Reconstructing team totals by summing player-level box
  scores was considered and rejected: it preserves unattended operation but can diverge from the
  platform's official totals on mid-week lineup and injured-reserve changes, and a ranking that
  disagrees with what members see on the site is worse than one that is late.
