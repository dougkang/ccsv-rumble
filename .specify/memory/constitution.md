# ccsv-rumble-page Constitution

ccsv-rumble-page is a Python batch generator. Once a week it pulls fantasy basketball league data,
computes power rankings, renders static HTML (a homepage plus rankings), and pushes that HTML to a
separate repository served by GitHub Pages.

Three facts drive every principle below. The project is **unattended** — it runs on a schedule
with nobody watching, so failures must be loud and safe rather than silent and destructive. It is
**publishing** — its output is a live public page for a church league, so a bad run damages
something real. And its audience is a **community, not customers** — members read it casually on
phones, and they are people in a congregation, not analytics subjects.

## Core Principles

### I. Deterministic Rankings, Reproducible Pages

The ranking computation is pure, and any published page can be reproduced exactly from its
archive.

- The power-rankings computation MUST be a pure function of the input snapshot plus a declared
  algorithm version. It MUST live in its own module, free of I/O, network, and filesystem access.
- Changing the rankings algorithm MUST bump its declared algorithm version, and the change MUST
  be accompanied by a before/after comparison on archived data in the PR.
- Rendering MUST be deterministic: given an identical snapshot, rendering MUST produce
  byte-identical HTML. Two renders over the same archived snapshot that differ are a bug.
- Nondeterminism MUST NOT leak into rendering: no unseeded randomness, no iteration over
  unordered collections without an explicit sort, and no incidental wall-clock values. A
  deliberate "last updated" timestamp is permitted, MUST be the only time-varying element, and
  MUST be injected as an explicit parameter rather than read ad hoc deep in rendering code.
- A nondeterministic stage — a language model, or anything else whose output cannot be reproduced
  on demand — is permitted **only during acquisition**, never during ranking or rendering. Its
  output MUST be captured into the snapshot and archived under Principle III, and from that point
  on MUST be treated exactly like fetched data.
- Regeneration MUST NOT invoke a nondeterministic stage. Replaying an archived snapshot MUST
  reuse the archived output and MUST NOT call a model or any other unrepeatable producer.

Rationale: rankings are the part of this page people will argue about. Being able to say "here is
exactly how that number was produced, and here it is reproduced" is the difference between a
disagreement and a loss of trust. A model that writes prose cannot be reproduced on demand, so
the guarantee is relocated rather than abandoned: the unrepeatable step runs once, is archived,
and everything downstream of it replays exactly.

### II. Never Publish a Broken Page

A run either publishes a complete, validated page or it publishes nothing and reports failure.

- The publish step MUST be gated on validation. At minimum the generated output MUST be
  well-formed HTML, contain every expected section, and contain no empty-state placeholder where
  real data was expected.
- If data fetching or generation fails for any reason, the run MUST NOT push. The previously
  published page MUST remain live and untouched. A stale correct page always beats a fresh
  broken one.
- Publishing MUST be all-or-nothing: either every generated file lands in one push, or none does.
  Partial publishes are forbidden.
- A failed run MUST exit non-zero and MUST emit a failure notification through a configured
  channel, not only to stdout or a log file. TODO(ALERT_CHANNEL): the channel (email, push, issue
  filing, …) is not yet chosen; decide via `/speckit-plan`.
- The generator MUST be safe to re-run at any time. Re-running after a failure, or twice in one
  week, MUST NOT corrupt state or produce a different page than a single run would.
- A run that completes successfully but produces output identical to what is already published
  MUST NOT create a commit in the publish repository.
- What counts as a **complete** page is defined per feature. Content that a feature's
  specification explicitly designates as optional MUST NOT block publication when it is absent or
  fails its own validation: the page publishes without it, and the omission is reported through
  the notification rule above rather than suppressing the run.

Rationale: nobody is watching this run. Every ambiguous failure mode must resolve toward "leave
the good page up and complain loudly."

### III. Raw Data Is Archived and Immutable

Every run MUST persist the raw inputs it acquired, before any transformation, and MUST never
modify or delete a prior run's archive.

- The archive MUST be sufficient to regenerate that week's page offline, with no network access.
- The archive MUST include output produced by nondeterministic stages — model-generated text, for
  example — and not only data fetched from upstream. Without this, Principle I's replay guarantee
  has nothing to replay.
- Archives are append-only. Corrections are added as new entries; history is not rewritten.
- Generation MUST be runnable against an archived snapshot instead of a live fetch, and this path
  MUST be exercised by tests.

Rationale: upstream league data changes and disappears — scores get corrected, seasons roll over,
free APIs break. Without an archive, Principle I's reproducibility claim is unverifiable the day
after it matters, and a past ranking can never be explained.

### IV. Generated Output Is Static and Accessible

The published artifact is plain static files, and it MUST be usable by everyone in the league.

- Output MUST be static HTML, CSS, and images servable by GitHub Pages. No server-side runtime,
  no build step required at serve time.
- Content MUST render and be fully readable with JavaScript disabled. JavaScript, if present at
  all, MUST be purely additive.
- Markup MUST be semantic: correctly ordered headings, real `<table>` markup for standings and
  rankings with proper `<th>` scope, and landmark elements over unlabeled `<div>`s.
- Text MUST meet a 4.5:1 contrast ratio, and layout MUST be readable from 320px wide upward with
  no horizontal scrolling of the page body.
- Total page weight MUST stay under 500KB compressed, and the page MUST NOT depend on any
  third-party script, font, or stylesheet fetched at page load.
- Templates MUST be data-driven: no league fact may be hardcoded in a template when it is
  available in the input data.

Rationale: a static, dependency-free page is why this architecture was chosen — it costs nothing,
cannot go down between runs, and will still work years from now. Accessibility and a weight budget
are not polish here; the page is read on phones by a congregation of varied ages and devices.

### V. Secrets Stay Out, Member Data Stays Minimal

- Credentials, tokens, cookies, and API keys MUST NOT appear in this repository, in the publish
  repository, in archived data, or in generated HTML. They MUST be supplied by environment
  variables or a secret store at runtime.
- The push credential MUST be scoped to only the publish repository, and MUST be rotatable without
  code changes.
- Generated output MUST contain only league-relevant information: team names, display names,
  scores, standings, and rankings. Email addresses, phone numbers, real-world addresses, and any
  other personal contact information MUST NOT be published.
- Logs and archived snapshots MUST be scrubbed of credentials before being written.
- The page MUST NOT include analytics, tracking, advertising, or any third-party embed that sets
  cookies or profiles visitors.

Rationale: the people on this page did not sign up to be a data subject; they signed up for a
church league. And an unattended job holding a push token is exactly the kind of thing that leaks
a credential into a public repo if the rules are not explicit.

## Technology & Operational Constraints

- **Language and toolchain**: Python, pinned by `.python-version` (currently 3.14), with `uv` for
  dependency and environment management. The lockfile MUST be committed.
- **Entry point**: a single command MUST perform a full run end to end with no manual steps. It
  MUST support a dry-run mode that generates and validates output without pushing, and a mode that
  generates from an archived snapshot instead of a live fetch.
- **Separation of concerns**: fetching, archiving, ranking, rendering, and publishing MUST be
  distinct modules. Ranking and rendering MUST have no network or push access, which is what makes
  Principle I testable.
- **Scheduling**: the weekly trigger MUST be automated and MUST require no interactive input or
  local developer machine. The run MUST be idempotent per Principle II, so a missed or duplicated
  trigger is never an emergency. TODO(SCHEDULER): the trigger mechanism (GitHub Actions scheduled
  workflow, cron on a host, …) is not yet chosen; decide via `/speckit-plan`.
- **Credential renewal**: the rule above governs the *trigger*, not the *lifetime of a credential
  the run depends on*. Where an upstream offers no long-lived unattended credential, a credential
  MAY require periodic interactive renewal by the maintainer, provided all of the following hold:
  1. The renewal cadence is documented where the credential is configured, so the chore is
     predictable rather than a surprise.
  2. An absent, invalid, or expired credential is a Principle II failure: the run MUST publish
     nothing, leave the previously published page untouched, exit non-zero, and notify. It MUST NOT
     be retried within a run, since validity cannot change between attempts.
  3. Renewal MUST be verifiable out of band — against the surface the run actually uses, not merely
     against the upstream's front door — so the maintainer knows a replacement works before the next
     scheduled run rather than after it fails.
  4. A credential that fails verification MUST NOT be stored, so a known-bad credential cannot
     silently replace a working one.
  5. Principle V continues to apply without relaxation: no credential value may reach either
     repository, archived data, generated output, or logs.
  6. Where more than one acquisition path exists, the longer-lived one MUST remain selectable, so a
     restored unattended credential is a configuration change rather than a rewrite.

  This permits a manually renewed credential; it does not permit an unattended run to become an
  attended one. Everything between the trigger and the publish MUST still happen without a human.
- **Timekeeping**: the run's weekly boundary MUST align with the league's matchup week, since
  category totals are only meaningful at that boundary. That boundary and all displayed dates
  MUST use a single explicitly configured timezone, never the host's local time.
- **Upstream resilience**: every network call MUST set an explicit timeout and MUST NOT retry
  indefinitely. Exhausted retries are a Principle II failure: report and publish nothing.
- **Publish target**: generated HTML is pushed to a separate GitHub Pages repository; this
  repository holds only the generator and its archives. TODO(PUBLISH_TARGET): the name of that
  repository and the auth method for pushing to it are not yet recorded; decide via
  `/speckit-plan`.
- **Data source**: TODO(DATA_SOURCE): the league data provider (ESPN, Yahoo, Sleeper, manual
  entry, …) and whether it exposes a stable API are not yet established; decide via
  `/speckit-plan`. Whatever it is, access MUST comply with that provider's terms, and the fetch
  layer MUST be isolated behind an interface so the provider can be replaced without touching
  ranking or rendering code.
- **Dependency restraint**: adding a runtime dependency MUST be justified in the PR against a named
  requirement the standard library cannot meet.

## Development Workflow & Quality Gates

Balanced rigor: tests where they earn their keep, review always, no ceremony for its own sake.

- **Branching**: work happens on a branch; `main` is the branch the scheduled job runs from. Direct
  pushes to `main` are forbidden.
- **Review**: every change MUST be reviewed by at least one person other than the author before
  merge. The reviewer is responsible for checking compliance with the principles above.
- **Testing** — required where the risk is, not everywhere:
  1. Ranking logic MUST have unit tests over fixture data, including ties and incomplete data.
  2. Rendering MUST have a golden-file test asserting byte-identical output for a fixed snapshot
     (this is the enforcement mechanism for Principle I).
  3. The failure path MUST be tested: a simulated fetch or validation failure MUST be shown not to
     push.
  4. Replay from an archived snapshot MUST be tested to confirm no nondeterministic stage is
     invoked (this is the enforcement mechanism for Principle I's regeneration rule).
  5. Every bug fix MUST include a test that fails before the fix and passes after.
  6. No coverage threshold is enforced. Purely cosmetic template or CSS changes do not require new
     unit tests, but MUST have their golden files reviewed as part of the diff.
- **Pre-merge gates** (all MUST pass):
  1. Test suite green.
  2. A dry run against an archived snapshot succeeds and its output passes validation.
  3. Golden-file diffs are reviewed and intentional — an unexplained rendering diff blocks merge.
  4. Rankings algorithm changes include the before/after comparison required by Principle I.
  5. No secret, token, or personal contact information appears in the diff.
- **Observability**: each run MUST log enough to answer, after the fact, whether it ran, what it
  fetched, whether it published, and why not if it did not.
- **Rollback**: because publishing is a commit to the publish repository, rollback is reverting
  that commit. A bad published page MUST be reverted or fixed forward the same day it is noticed.
  Reverting the page MUST NOT require reverting generator code.

## Governance

This constitution supersedes other practices, conventions, and preferences for this project. Where
it conflicts with a habit, a tutorial, or an agent's default behavior, this document wins.

**Authority**: all specs, plans, tasks, reviews, and implementations MUST comply. A reviewer MUST
block a change that violates a principle unless the violation is explicitly justified and recorded
in the PR description under a "Constitution exception" heading.

**Amendment procedure**:

1. Propose the change as a PR editing this file alone, stating the problem the current text causes.
2. The PR MUST include the version bump, the rationale, and a migration note for any work in
   flight that the change invalidates.
3. Approval by the project maintainer is required to merge.
4. On merge the amendment is in force immediately; in-flight work MUST be brought into compliance
   or granted a recorded exception.

**Versioning policy** — semantic versioning of governance:

- **MAJOR**: a principle is removed, or its central guarantee is redefined such that work judged
  compliant under one version would be judged differently under the other — **in either
  direction**, whether the change relaxes a constraint or tightens it. Examples: permitting a
  server-side runtime, dropping the archive requirement, or changing what "deterministic" covers.
- **MINOR**: a principle or section is added, or existing guidance is materially expanded or
  tightened — for example, lowering the page-weight budget or adding a new pre-merge gate.
- **PATCH**: clarification, wording, typo, or formatting change that does not change what is
  required.

Note that this versioning policy governs *this document*. It is independent of the rankings
algorithm version required by Principle I.

**Compliance review**: the pre-merge gates above are the routine compliance mechanism. Beyond that,
this constitution MUST be re-read and either reaffirmed or amended before each new feature's
`/speckit-plan`, and every recorded Constitution exception MUST be revisited at that time — a
recurring exception is evidence that the principle needs amending rather than repeated waiving.

**Version**: 3.0.0 | **Ratified**: 2026-10-17 | **Last Amended**: 2026-10-21
