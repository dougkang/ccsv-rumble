"""Run orchestration.

The ordering here is load-bearing: corrections are acquired BEFORE any ranking is
computed, because a correction to week 5 changes the recency-weighted history
that week 6's ranking is built from.

Correction and backfill are deliberately separate paths:

    backfill   -> week ABSENT from the archive -> acquire, rank, and PUBLISH a page
    correction -> week CHANGED upstream        -> acquire and archive only, never republish

Collapsing them into one branch implements FR-038 and FR-048 as a contradiction.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import config
from .archive import diff as archive_diff
from .archive.store import ArchiveStore, EntryPaths
from .article.generate import generate_article, generate_draft_recap
from .article.validate import validate_article, validate_draft_recap
from .fetch import draft as draft_source
from .fetch import rosters as roster_source
from .fetch.normalize import build_snapshot
from .fetch.projection_provider import ProjectionError
from .fetch.projections import LocalFileProjectionProvider
from .fetch.projections import acquire as acquire_projections
from .fetch.captured import CapturedProvider, build_capture_snapshot
from .fetch.provider import LeagueDataProvider, ProviderError, WeekNotCaptured
from .lifecycle import classify, classify_rosters
from .models import (
    Article,
    CategoryLine,
    DraftResults,
    LifecycleState,
    LifecycleVerdict,
    ProjectionSnapshot,
    PublishedPage,
    Snapshot,
    Team,
    TeamId,
)
from .notify import Notification
from .rank import draft_score as draft_scoring
from .rank import projected as projected_grid
from .rank.events import derive_events
from .rank.score import build_ranking
from .render.html import render_page
from .render.validate import validate_page
from .report import internal as internal_report
from .report import publishable as publishable_report
from .schedule import RunPlan

log = logging.getLogger("ccsv_rumble")


@dataclass
class RunResult:
    pages: list[PublishedPage] = field(default_factory=list)
    notification: Notification = field(default_factory=Notification)
    weeks_published: list[int] = field(default_factory=list)
    #: Set when the lifecycle gate withheld publication deliberately.
    #:
    #: This is the THIRD run outcome, distinct from both success and failure:
    #: publish nothing, exit ZERO, notify no one (FR-004). An undrafted league is
    #: a normal state, and reporting it as a failure every week until draft night
    #: would train the maintainer to ignore the only channel Principle II has.
    #:
    #: The reason is always recorded (FR-008), because a deliberately silent
    #: outcome is indistinguishable from a broken one without it.
    withheld: LifecycleVerdict | None = None

    @property
    def has_pages(self) -> bool:
        return bool(self.pages)


def played(history: Sequence[Snapshot]) -> list[Snapshot]:
    """The weeks with real results: everything but week 0 (FR-019).

    Week 0 is a projection with all-zero totals. Left in a ranking history it
    counts as a completed week and averages a week of nothing but ties into
    every team's EMW and CAW -- the order survives, which is why it went
    unnoticed, but every score is dragged toward .500.
    """
    return [snapshot for snapshot in history if snapshot.week > 0]


def published_ranks(store: ArchiveStore, season: str, week: int) -> dict[TeamId, int] | None:
    """The ranks readers were SHOWN for `week`, which the next week's movement
    is measured against (FR-020). None when the week was never published.

    Not a recomputation. Week 0 would rank all-zero totals, an order no reader
    ever saw; and any later week was published with a roster prior that a bare
    `build_ranking(history)` leaves out -- at one played week the prior is 75%
    of the score, so the two orders differ widely.

    Read from the newest entry that HAS a published report: a correction is
    archived without republishing, so the newest entry may have none.
    """
    if not store.has_week(season, week):
        return None
    for entry_id in reversed(store.list_entry_ids(season, week)):
        ranks = store.read_publishable_ranks(season, week, entry_id)
        if ranks is not None:
            return ranks
    return None


def carried_ranks(
    store: ArchiveStore,
    season: str,
    week: int,
    history: Sequence[Snapshot],
    previous_ranks: dict[TeamId, int] | None,
) -> dict[TeamId, int] | None:
    """Ranks to carry past an archived week this run does not republish."""
    ranks = published_ranks(store, season, week)
    if ranks is not None:
        return ranks
    if week == 0:
        log.warning("week 0 is archived but was never published; week 1 has no movement")
        return None
    # Never published (archives from before reports were kept): the best
    # available is a recomputation, as before.
    return {
        e.team_id: e.rank
        for e in build_ranking(played(history), previous_ranks=previous_ranks).entries
    }


@dataclass(frozen=True)
class LeagueSource:
    """Where weeks >= 1 come from: a provider paired with its normalizer.

    One per run (FR-003). The provider returns raw data; `build` turns it into a
    Snapshot; `archive_raw` and `quarantine` keep that raw data in its own
    format. Pairing them here is the seam `fetch/provider.py` describes --
    swapping providers changes the provider and the normalizer, and nothing in
    the archive, correction, or quarantine logic below.
    """

    name: str
    provider: LeagueDataProvider
    #: (raw, *, entry_id, acquired_at, season, week, stat_map, supersedes,
    #: existing) -> Snapshot. `existing` is the latest archived entry, if any.
    build: Callable[..., Snapshot]
    archive_raw: Callable[[ArchiveStore, EntryPaths, Any], None]
    quarantine: Callable[[ArchiveStore, str, int, datetime, Any], Path]


def _yahoo_build(raw: Any, *, existing: Snapshot | None = None, **kwargs: Any) -> Snapshot:
    # `build_snapshot` is resolved from this module at CALL time, so tests that
    # monkeypatch `ccsv_rumble.pipeline.build_snapshot` still reach it.
    return build_snapshot(scoreboard=raw, **kwargs)


def yahoo_source(provider: LeagueDataProvider) -> LeagueSource:
    return LeagueSource(
        name="yahoo",
        provider=provider,
        build=_yahoo_build,
        archive_raw=lambda store, paths, raw: store.write_raw(paths, raw),
        quarantine=lambda store, season, week, at, raw: store.quarantine_raw(
            season, week, at, raw
        ),
    )


def _capture_build(
    raw: Any, *, existing: Snapshot | None = None, week: int, stat_map: Any = None, **kwargs: Any
) -> Snapshot:
    capture = raw["capture"]
    if capture.week != week:
        raise ProviderError(f"capture returned week {capture.week} for week {week}")
    return build_capture_snapshot(
        capture, roster_capture=raw["rosters"], existing=existing, **kwargs
    )


def capture_source(provider: CapturedProvider) -> LeagueSource:
    """The committed capture. The raw input archived is the CSV rows, verbatim."""
    return LeagueSource(
        name="capture",
        provider=provider,
        build=_capture_build,
        archive_raw=lambda store, paths, raw: store.write_raw_text(
            paths.raw_matchups, raw["text"]
        ),
        quarantine=lambda store, season, week, at, raw: store.quarantine_text(
            season, week, at, raw["text"]
        ),
    )


def acquire_week(
    source: LeagueSource | LeagueDataProvider,
    store: ArchiveStore,
    *,
    season: str,
    week: int,
    stat_map: dict[str, str],
    notification: Notification,
) -> Snapshot:
    """Fetch a week and archive it, as a new entry only when it actually differs.

    Returns the snapshot now considered current for that week. A bare provider
    is treated as the Yahoo source, which is what every caller passed before
    sources existed.
    """
    if not isinstance(source, LeagueSource):
        source = yahoo_source(source)
    raw = source.provider.fetch_week(season, week)
    acquired_at = datetime.now(UTC)

    existing: Snapshot | None = None
    if store.has_week(season, week):
        existing = store.latest_entry(season, week)

    candidate_id = store.next_entry_id(season, week)
    try:
        candidate = source.build(
            raw,
            entry_id=candidate_id,
            acquired_at=acquired_at,
            season=season,
            week=week,
            stat_map=stat_map,
            supersedes=existing.entry_id if existing else None,
            existing=existing,
        )
    except Exception:
        # Quarantine the raw payload before re-raising.
        #
        # Archiving happens after parsing, so without this a parse failure
        # discards the very payload needed to diagnose it -- and the payload
        # most likely to break the parser is the FIRST real one, which by
        # definition cannot be reproduced from a fixture. Quarantine rather
        # than archive: an entry without a snapshot would become `latest_entry`
        # and corrupt every later read.
        quarantined = source.quarantine(store, season, week, acquired_at, raw)
        log.error(
            "week %s failed to parse; raw payload saved to %s", week, quarantined
        )
        raise

    if existing is not None:
        delta = archive_diff.compare(existing, candidate)
        if not delta:
            # Unchanged. Creating an entry here would append a junk directory
            # every single run, because Yahoo payloads carry volatile fields.
            return existing
        notification.corrections.append(
            f"week {week}: {'; '.join(delta.reasons)} (archived as {candidate_id})"
        )
        log.info("week %s changed upstream: %s", week, "; ".join(delta.reasons))

    paths = store.create_entry(season, week, candidate_id)
    source.archive_raw(store, paths, raw)
    store.write_snapshot(paths, candidate)
    return candidate


def acquire_week_zero(
    store: ArchiveStore,
    *,
    season: str,
    capture: roster_source.RosterCapture,
    stat_map: dict[str, str],
) -> Snapshot:
    """Build the week-0 snapshot from ROSTERS, with no scoreboard.

    `acquire_week` cannot serve week 0: it calls `build_snapshot`, which requires
    scoreboard totals for 18 teams, and week 0 has no scoreboard because no game
    has been played. Category totals are therefore zeroed -- genuinely zero, not
    missing -- and the ranking comes from the projected grid instead.

    Team names come from the roster capture rather than a provider, because
    there is no scoreboard to read them from -- and labelling every team by its
    id would be technically correct and useless to a reader.
    """
    acquired_at = datetime.now(UTC)
    rosters = capture.rosters
    teams = tuple(
        Team(
            team_id=team_id,
            name=capture.team_names.get(team_id, team_id),
            manager_display_name=capture.managers.get(team_id, ""),
        )
        for team_id in sorted(rosters)
    )
    if len(teams) != config.TEAM_COUNT:
        raise ProjectionError(
            f"week 0 needs rosters for all {config.TEAM_COUNT} teams, found "
            f"{len(teams)}. Capture the rest with tools/yahoo_roster_capture.js."
        )

    entry_id = store.next_entry_id(season, 0)
    return Snapshot(
        entry_id=entry_id,
        acquired_at=acquired_at,
        season=season,
        week=0,
        week_start=acquired_at.date(),
        week_end=acquired_at.date(),
        teams=teams,
        # Zero, not absent: no game has been played, so every total really is 0.
        category_totals=dict.fromkeys((t.team_id for t in teams), CategoryLine()),
        rosters=rosters,
        stat_category_map=dict(stat_map),
        completed_scored_weeks=0,
        raw_source="rosters.csv",
    )


def _draft_entries(
    snapshot: Snapshot,
    projections: ProjectionSnapshot | None,
    *,
    require_coverage: bool,
) -> dict[TeamId, draft_scoring.DraftScoreEntry] | None:
    """Projected grid -> DraftScore, or None when there is no usable signal.

    `require_coverage` distinguishes the two situations the thresholds mean
    different things in:

    * **Week 0** (True): the draft score IS the published ranking, so coverage
      below either floor is a Principle II failure -- publish nothing (FR-026,
      FR-038). A ranking computed from mostly-missing inputs is a broken page,
      not a degraded one.
    * **In-season** (False): the score is only the forward-looking TERM of a
      ranking carried by real results. Thin coverage degrades that term to
      absent, which lets realized performance take full weight, rather than
      taking the whole page down over one input.
    """
    if projections is None or not projections.projections or not snapshot.rosters:
        return None

    grid = projected_grid.build_projected_grid(snapshot.rosters, projections)
    verdict = projected_grid.check_coverage(grid)
    if not verdict.ok:
        if require_coverage:
            raise ProjectionError(
                f"projection coverage is insufficient to publish: {verdict.reason}"
            )
        log.warning(
            "projection coverage too thin for a roster prior (%s); "
            "realized performance will carry full weight",
            verdict.reason,
        )
        return None
    return draft_scoring.score(grid)


def build_week_page(
    store: ArchiveStore,
    *,
    season: str,
    week: int,
    history: Sequence[Snapshot],
    previous_ranks: dict[TeamId, int] | None,
    is_current_week: bool,
    generated_at: str,
    anthropic_client: Any | None,
    notification: Notification,
    projections: ProjectionSnapshot | None,
    is_week_zero: bool = False,
    draft_results: DraftResults | None = None,
) -> tuple[PublishedPage, dict[TeamId, int]]:
    """Rank, report, write, validate, render one week. Returns the page and ranks.

    An article failure degrades THIS week only; the caller continues to the next
    (FR-044). A report or render failure raises, which aborts the whole run.
    """
    current = history[-1]
    results = played(history)
    draft_entries = _draft_entries(current, projections, require_coverage=is_week_zero)
    prior = draft_scoring.as_prior(draft_entries) if draft_entries else None

    # Two different "not a settled ranking" states:
    #   week 0 -> a DRAFT-BASED PROJECTION: there are no results at all
    #   week 1 -> PROVISIONAL: one week of real results, which is thin enough
    #             that the page must say so
    #
    # Week 1 is never a projection, even with a roster prior. Its games have
    # been played, and calling it a projection makes the page and the article
    # claim no games have happened.
    #
    # Counted over PLAYED weeks: an archived week 0 must not make week 1 look
    # like a second week of results (FR-021).
    is_projection = is_week_zero
    is_provisional = not is_week_zero and len(results) <= 1

    if is_week_zero:
        # No played results exist, so there is no history to rank over.
        if draft_entries is None:
            # NOT an assertion. `_draft_entries` returns None -- rather than
            # raising -- when there is no projection file at all or no rosters,
            # and an AssertionError here would escape `cli.py`'s handlers as an
            # uncaught traceback instead of a clean Principle II failure.
            raise ProjectionError(
                f"week {week} needs projections to rank, and none are usable: "
                "either the projections file is absent or no rosters were "
                "acquired. See contracts/projection-source.md for the schema."
            )
        ranking = draft_scoring.build_draft_ranking(draft_entries, week=week)
    else:
        ranking = build_ranking(results, previous_ranks=previous_ranks, roster_prior=prior)
    events = derive_events(current, results[:-1])

    report_internal = internal_report.build(
        season=season,
        week=week,
        entry_id=current.entry_id,
        ranking=ranking,
        events=events,
    )
    report_public = publishable_report.build(
        internal=report_internal,
        history=history if is_week_zero else results,
        is_projection=is_projection,
        is_current_week=is_current_week,
        is_provisional=is_provisional,
    )

    paths = store.paths(season, week, current.entry_id)
    if paths.root.is_dir():
        store.write_internal(paths, report_internal)
        store.write_publishable(paths, report_public)

    # Week 0 gets the draft recap (FR-041); every other week gets the column.
    #
    # FR-049 is handled by the `draft_results is None` arm: with no usable board
    # the page publishes the ranking and no article at all, rather than a recap
    # written from rosters alone. The log line is deliberate -- the page itself
    # gives no sign the section is missing.
    write_recap = is_week_zero and draft_results is not None
    # Only a notification when an article was actually possible. On a
    # rankings-only deployment -- no ANTHROPIC_API_KEY -- there was never going
    # to be a recap, so reporting its absence would fire every run and train
    # the maintainer to ignore the one channel Principle II has.
    if is_week_zero and draft_results is None and anthropic_client is not None:
        log.warning(
            "week 0 draft results unavailable or incomplete; publishing the "
            "ranking with no article (FR-049)"
        )
        notification.article_failures.append(
            "week 0: no usable draft results, article omitted"
        )

    article: Article | None = None
    if anthropic_client is not None and (write_recap or not is_week_zero):
        article = (
            generate_draft_recap(report_public, draft_results, anthropic_client)
            if write_recap and draft_results is not None
            else generate_article(report_public, anthropic_client)
        )
        if article.content is not None:
            outcome = (
                validate_draft_recap(article.content, report_public, draft_results)
                if write_recap and draft_results is not None
                else validate_article(article.content, report_public)
            )
            article = Article(
                week=article.week,
                model=article.model,
                generated_at=article.generated_at,
                content=article.content,
                validation=outcome,
            )
        if paths.root.is_dir():
            # Archive rejected articles too, with their reasons (FR-027).
            store.write_article(paths, article)
        if not article.is_publishable:
            reasons = "; ".join(f.message for f in article.validation.failures)
            notification.article_failures.append(f"week {week}: {reasons}")
            log.warning("week %s article not published: %s", week, reasons)

    content = article.content if article and article.is_publishable else None
    page = render_page(
        report=report_public,
        entry_id=current.entry_id,
        generated_at=generated_at,
        article=content,
        draft_algorithm_version=ranking.draft_algorithm_version,
    )
    validate_page(page)

    ranks = {entry.team_id: entry.rank for entry in ranking.entries}
    return page, ranks


def execute(
    plan: RunPlan,
    *,
    provider: LeagueDataProvider | None = None,
    source: LeagueSource | None = None,
    store: ArchiveStore,
    anthropic_client: Any | None,
    generated_at: str,
    projections_path: Path,
    rosters_path: Path | None = None,
    draft_results_path: Path | None = None,
) -> RunResult:
    """Run the full sequence for one invocation.

    League data for weeks >= 1 comes from `source`. A bare `provider` is
    wrapped as the Yahoo source, which is what callers passed before sources
    existed. Both may be None when only week 0 is in play: that week is
    assembled from rosters and projections and never calls the league API.
    """
    if source is None and provider is not None:
        source = yahoo_source(provider)
    result = RunResult()
    season = plan.season
    # Only scoreboard parsing needs the category map, and week 0 has no
    # scoreboard, so this is skipped rather than failing for want of a token.
    stat_map = (
        source.provider.fetch_stat_category_map(season) if source is not None else {}
    )

    # 1-2. Corrections first -- they change the history every later ranking uses.
    for week in plan.recheck_weeks:
        try:
            acquire_week(
                source, store, season=season, week=week,
                stat_map=stat_map, notification=result.notification,
            )
        except WeekNotCaptured:
            # Only here. The archive already holds a valid version of a
            # re-checked week, so a capture that no longer carries it is not a
            # failure; a gap or the current week has nothing to fall back on
            # and must still fail (research R4).
            log.info("week %s not re-checked: not in capture; archived entry stands", week)

    # 3. Then gaps and the current week, ascending.
    history: list[Snapshot] = []
    previous_ranks: dict[TeamId, int] | None = None
    publish_weeks = set(plan.weeks_to_publish)
    all_weeks = sorted(set(store.archived_weeks(season)) | publish_weeks)

    # How many weeks with real results the archive already holds. The archive
    # knows this; a single snapshot does not.
    scored_weeks_archived = len([w for w in store.archived_weeks(season) if w > 0])

    # Rosters: league data, a separate input from projections (research D12).
    # A projections file cannot define rosters, because FR-025 needs rostered
    # players who have NO projection and a projections file omits exactly those.
    acquired_capture = roster_source.RosterCapture({}, {})
    if rosters_path is not None and rosters_path.is_file():
        acquired_capture = roster_source.load(rosters_path)
        log.info(
            "acquired rosters for %s teams (%s players)",
            len(acquired_capture.rosters),
            sum(len(v) for v in acquired_capture.rosters.values()),
        )
    acquired_rosters = acquired_capture.rosters

    # The draft board. Needed only by the recap, and resolved against the roster
    # capture's team names so the rest of the pipeline only ever sees `t.01`
    # style ids. Loaded here rather than inside the publish loop because the
    # resolution depends on rosters, which are acquired above.
    draft_results: DraftResults | None = None
    if draft_results_path is not None and acquired_capture.team_names:
        draft_results = draft_source.load_or_none(
            draft_results_path, season, acquired_capture.team_names
        )
        if draft_results is not None:
            log.info(
                "acquired %s draft picks from %s",
                len(draft_results.picks),
                draft_results_path,
            )

    projections: ProjectionSnapshot | None = None
    raw_projection_text = ""
    if projections_path.is_file():
        # Acquired ONCE per run, during acquisition, and passed into ranking as
        # data. It used to be read inside `rank/`, which both breached
        # Principle I and made replay non-reproducible -- editing the file
        # silently changed the result of replaying a past week.
        raw_projection_text = projections_path.read_text(encoding="utf-8")
        projections = acquire_projections(
            LocalFileProjectionProvider(projections_path),
            season,
            plan.current_week,
        )
        log.info(
            "acquired %s projections from %s",
            len(projections.projections),
            projections.source_id,
        )

    for week in all_weeks:
        if week in publish_weeks:
            if week == 0:
                # The pre-draft decision comes from rosters alone, because a
                # Snapshot cannot be built without all 18 teams and week 0 has
                # no scoreboard to supply them. Absent rosters are a normal
                # pre-draft state (FR-002), not an acquisition failure.
                roster_verdict = classify_rosters(acquired_rosters)
                if roster_verdict is not None:
                    log.info(
                        "lifecycle: %s -- %s",
                        roster_verdict.state.value,
                        roster_verdict.reason,
                    )
                    result.withheld = roster_verdict
                    return result
                snapshot = acquire_week_zero(
                    store, season=season,
                    capture=acquired_capture, stat_map=stat_map,
                )
                paths = store.create_entry(season, 0, snapshot.entry_id)
                store.write_snapshot(paths, snapshot)
            else:
                if source is None:
                    raise ProjectionError(
                        f"week {week} needs league data, and no source is "
                        "configured. Capture the week into data/matchups.csv, "
                        "or run week 0 only, which needs rosters and projections."
                    )
                snapshot = acquire_week(
                    source, store, season=season, week=week,
                    stat_map=stat_map, notification=result.notification,
                )
            if week == plan.current_week:
                # FR-002: the state is determined and LOGGED every run.
                verdict = classify(
                    snapshot, completed_scored_weeks=scored_weeks_archived
                )
                log.info("lifecycle: %s -- %s", verdict.state.value, verdict.reason)
                if verdict.state is LifecycleState.PRE_DRAFT:
                    # The third outcome: nothing published, exit zero, no
                    # notification. The reason above is the only signal.
                    #
                    # Reachable only at week 0 -- `classify` treats any week >= 1
                    # as in-season, because games have been played by then.
                    # Without that, a mid-season week whose provider supplied no
                    # roster data would classify pre-draft and silently stop
                    # publishing, which is the exact failure this gate exists to
                    # prevent rather than cause.
                    result.withheld = verdict
                    return result
        elif store.has_week(season, week):
            # Corrections feed forward: ranking always reads the LATEST entry.
            snapshot = store.latest_entry(season, week)
        else:
            continue

        history.append(snapshot)

        if week not in publish_weeks:
            # Still rank it, to carry `previous_ranks` forward correctly.
            previous_ranks = carried_ranks(store, season, week, history, previous_ranks)
            continue

        # Archive the projection snapshot into this week's entry, so replay
        # reads it rather than the live file (FR-011, FR-012).
        if projections is not None:
            entry_paths = store.paths(season, week, snapshot.entry_id)
            if entry_paths.root.is_dir() and not entry_paths.projections.is_file():
                store.write_projections(entry_paths, projections, raw_projection_text)

        # FR-042: archive the draft results immutably as an input, so the
        # recap is replayed from the archive and never re-reads the live file.
        if week == 0 and draft_results is not None:
            entry_paths = store.paths(season, week, snapshot.entry_id)
            if entry_paths.root.is_dir() and not entry_paths.draft_results.is_file():
                store.write_draft_results(entry_paths, draft_results)

        page, ranks = build_week_page(
            store,
            season=season,
            week=week,
            history=history,
            previous_ranks=previous_ranks,
            is_current_week=(week == plan.current_week),
            generated_at=generated_at,
            anthropic_client=anthropic_client,
            notification=result.notification,
            projections=projections,
            is_week_zero=(week == 0),
            draft_results=draft_results if week == 0 else None,
        )
        previous_ranks = ranks
        result.pages.append(page)
        result.weeks_published.append(week)
        if week != plan.current_week:
            result.notification.backfilled_weeks.append(week)

    return result
