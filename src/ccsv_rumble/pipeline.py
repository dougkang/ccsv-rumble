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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .archive import diff as archive_diff
from .archive.store import ArchiveStore
from .article.generate import generate_article
from .article.validate import validate_article
from .fetch.normalize import build_snapshot
from .fetch.provider import LeagueDataProvider
from .models import Article, PublishedPage, Snapshot, TeamId
from .notify import Notification
from .rank.events import derive_events
from .rank.prior import load_player_values, roster_prior
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

    @property
    def has_pages(self) -> bool:
        return bool(self.pages)


def acquire_week(
    provider: LeagueDataProvider,
    store: ArchiveStore,
    *,
    season: str,
    week: int,
    stat_map: dict[str, str],
    notification: Notification,
) -> Snapshot:
    """Fetch a week and archive it, as a new entry only when it actually differs.

    Returns the snapshot now considered current for that week.
    """
    raw = provider.fetch_week(season, week)
    acquired_at = datetime.now(UTC)

    existing: Snapshot | None = None
    if store.has_week(season, week):
        existing = store.latest_entry(season, week)

    candidate_id = store.next_entry_id(season, week)
    candidate = build_snapshot(
        entry_id=candidate_id,
        acquired_at=acquired_at,
        season=season,
        week=week,
        scoreboard=raw,
        stat_map=stat_map,
        supersedes=existing.entry_id if existing else None,
    )

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
    store.write_raw(paths, raw)
    store.write_snapshot(paths, candidate)
    return candidate


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
    projections_path: Path,
) -> tuple[PublishedPage, dict[TeamId, int]]:
    """Rank, report, write, validate, render one week. Returns the page and ranks.

    An article failure degrades THIS week only; the caller continues to the next
    (FR-044). A report or render failure raises, which aborts the whole run.
    """
    current = history[-1]
    player_values = load_player_values(projections_path)
    prior = roster_prior(current, player_values)
    is_projection = len(history) <= 1 and prior is not None

    ranking = build_ranking(
        history, previous_ranks=previous_ranks, roster_prior=prior
    )
    events = derive_events(current, history[:-1])

    report_internal = internal_report.build(
        season=season,
        week=week,
        entry_id=current.entry_id,
        ranking=ranking,
        events=events,
    )
    report_public = publishable_report.build(
        internal=report_internal,
        history=history,
        is_projection=is_projection,
        is_current_week=is_current_week,
    )

    paths = store.paths(season, week, current.entry_id)
    if paths.root.is_dir():
        store.write_internal(paths, report_internal)
        store.write_publishable(paths, report_public)

    article: Article | None = None
    if anthropic_client is not None:
        article = generate_article(report_public, anthropic_client)
        if article.content is not None:
            outcome = validate_article(article.content, report_public)
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
    )
    validate_page(page)

    ranks = {entry.team_id: entry.rank for entry in ranking.entries}
    return page, ranks


def execute(
    plan: RunPlan,
    *,
    provider: LeagueDataProvider,
    store: ArchiveStore,
    anthropic_client: Any | None,
    generated_at: str,
    projections_path: Path,
) -> RunResult:
    """Run the full sequence for one invocation."""
    result = RunResult()
    season = plan.season
    stat_map = provider.fetch_stat_category_map(season)

    # 1-2. Corrections first -- they change the history every later ranking uses.
    for week in plan.recheck_weeks:
        acquire_week(
            provider, store, season=season, week=week,
            stat_map=stat_map, notification=result.notification,
        )

    # 3. Then gaps and the current week, ascending.
    history: list[Snapshot] = []
    previous_ranks: dict[TeamId, int] | None = None
    publish_weeks = set(plan.weeks_to_publish)
    all_weeks = sorted(set(store.archived_weeks(season)) | publish_weeks)

    for week in all_weeks:
        if week in publish_weeks:
            snapshot = acquire_week(
                provider, store, season=season, week=week,
                stat_map=stat_map, notification=result.notification,
            )
        elif store.has_week(season, week):
            # Corrections feed forward: ranking always reads the LATEST entry.
            snapshot = store.latest_entry(season, week)
        else:
            continue

        history.append(snapshot)

        if week not in publish_weeks:
            # Still rank it, to carry `previous_ranks` forward correctly.
            previous_ranks = {
                e.team_id: e.rank
                for e in build_ranking(history, previous_ranks=previous_ranks).entries
            }
            continue

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
            projections_path=projections_path,
        )
        previous_ranks = ranks
        result.pages.append(page)
        result.weeks_published.append(week)
        if week != plan.current_week:
            result.notification.backfilled_weeks.append(week)

    return result
