"""Command-line entry point. The project's only external interface.

Exit codes (contracts/cli.md):

    0  success, including a correct no-op and a degraded (rankings-only) publish
    1  acquisition failure        -- nothing published
    2  report generation/validation failure -- nothing published
    3  render/HTML validation failure       -- nothing published
    4  publish failure                      -- previous site intact
    5  notification failure on a run that had something to report

Codes 1-4 all leave the previously published site live and untouched.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from . import config
from .archive.store import ArchiveStore
from .article.generate import ArticleUnavailable  # noqa: F401 -- re-exported
from .fetch.provider import ProviderError
from .fetch.yahoo import YahooProvider
from .models import ValidationError
from .notify import GitHubIssueNotifier, NotifyError, NullNotifier
from .pipeline import execute
from .publish import PublishError, StagedSite, publish
from .render.html import render_page
from .render.validate import PageInvalid, validate_page
from .schedule import build_plan

EXIT_OK = 0
EXIT_ACQUIRE = 1
EXIT_REPORT = 2
EXIT_RENDER = 3
EXIT_PUBLISH = 4
EXIT_NOTIFY = 5

log = logging.getLogger("ccsv_rumble")

DEFAULT_SEASON = "2026-27"
DEFAULT_SEASON_START = date(2026, 10, 20)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stdout,
    )


def _provider_from_env() -> YahooProvider:
    missing = [
        name
        for name in (
            "YAHOO_CLIENT_ID",
            "YAHOO_CLIENT_SECRET",
            "YAHOO_REFRESH_TOKEN",
            "YAHOO_LEAGUE_KEY",
        )
        if not os.environ.get(name)
    ]
    if missing:
        raise ProviderError(f"missing required environment variables: {missing}")
    return YahooProvider(
        client_id=os.environ["YAHOO_CLIENT_ID"],
        client_secret=os.environ["YAHOO_CLIENT_SECRET"],
        refresh_token=os.environ["YAHOO_REFRESH_TOKEN"],
        league_key=os.environ["YAHOO_LEAGUE_KEY"],
    )


def _anthropic_client():
    """None when no key is configured -- the rankings-only path (FR-029)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.info("ANTHROPIC_API_KEY not set; publishing rankings only")
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK unavailable; publishing rankings only")
        return None
    return anthropic.Anthropic()


def _notifier():
    repository = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if repository and token:
        return GitHubIssueNotifier(repository, token)
    log.info("GITHUB_REPOSITORY/GITHUB_TOKEN not set; notifications will not be sent")
    return NullNotifier()


def _store(root: Path | None = None) -> ArchiveStore:
    return ArchiveStore(root or Path("archive"))


# --- commands -----------------------------------------------------------------


def cmd_run(args: argparse.Namespace, *, dry_run: bool = False) -> int:
    store = _store(args.archive)
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d")

    if args.from_archive:
        return _run_from_archive(args, store, generated_at, dry_run=True)

    try:
        provider = _provider_from_env()
    except ProviderError as exc:
        log.error("%s", exc)
        return EXIT_ACQUIRE

    plan = build_plan(
        store,
        args.season,
        DEFAULT_SEASON_START,
        explicit_week=args.week,
        backfill=not args.no_backfill,
        recheck_weeks=args.recheck_weeks,
    )
    log.info(
        "plan: publish weeks %s; re-check %s",
        list(plan.weeks_to_publish),
        list(plan.recheck_weeks),
    )

    try:
        result = execute(
            plan,
            provider=provider,
            store=store,
            anthropic_client=None if dry_run and args.no_article else _anthropic_client(),
            generated_at=generated_at,
            projections_path=Path(args.projections),
        )
    except ProviderError as exc:
        log.error("acquisition failed: %s", exc)
        return EXIT_ACQUIRE
    except (ValidationError, ValueError) as exc:
        log.error("report generation failed: %s", exc)
        return EXIT_REPORT
    except PageInvalid as exc:
        log.error("render validation failed: %s", exc)
        return EXIT_RENDER

    if not result.has_pages:
        log.error("no pages were produced; publishing nothing")
        return EXIT_REPORT

    staged = StagedSite()
    for page in result.pages:
        staged.add_page(page)
    published_weeks = sorted(set(store.archived_weeks(args.season)) | set(result.weeks_published))
    staged.finalize(season=args.season, weeks=published_weeks)

    if dry_run:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in sorted(staged.files.items()):
            (out / name).write_text(content, encoding="utf-8")
        log.info("dry run complete; wrote %s files to %s", len(staged.files), out)
        _report_summary(result)
        return EXIT_OK

    try:
        committed = publish(
            staged,
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            branch=args.branch,
            token=os.environ.get("GITHUB_TOKEN"),
            commit_message=(
                f"Publish weeks {', '.join(str(w) for w in result.weeks_published)}"
            ),
        )
    except PublishError as exc:
        log.error("publish failed: %s", exc)
        return EXIT_PUBLISH

    log.info("published" if committed else "no changes; no commit created")
    _report_summary(result)

    if result.notification.has_content:
        try:
            _notifier().send(result.notification)
        except NotifyError as exc:
            # The page carries no sign of a degraded article (FR-030a), so an
            # unreported event is invisible. Do not call that a success.
            log.error("notification failed after publishing: %s", exc)
            return EXIT_NOTIFY

    return EXIT_OK


def _report_summary(result) -> None:
    log.info("weeks published: %s", result.weeks_published)
    if result.notification.backfilled_weeks:
        log.info("backfilled: %s", result.notification.backfilled_weeks)
    if result.notification.corrections:
        log.info("corrections: %s", result.notification.corrections)
    if result.notification.article_failures:
        log.info("article failures: %s", result.notification.article_failures)


def _run_from_archive(
    args: argparse.Namespace, store: ArchiveStore, generated_at: str, *, dry_run: bool
) -> int:
    """Validate against archived data with no network and no model."""
    weeks = store.archived_weeks(args.season)
    if args.week:
        weeks = [w for w in weeks if w <= args.week]
    if not weeks:
        log.error("no archived weeks for season %s", args.season)
        return EXIT_REPORT
    try:
        page = _render_archived(store, args.season, weeks[-1], generated_at, None)
    except (PageInvalid, ValidationError, ValueError) as exc:
        log.error("archive dry run failed: %s", exc)
        return EXIT_RENDER
    log.info("archive dry run OK for week %s (%s bytes)", page.week, len(page.html))
    return EXIT_OK


def _render_archived(
    store: ArchiveStore,
    season: str,
    week: int,
    generated_at: str,
    entry_id: str | None,
):
    """Rebuild one week's page from the archive. No network, no model."""
    from .pipeline import build_week_page

    weeks = [w for w in store.archived_weeks(season) if w <= week]
    history = [store.latest_entry(season, w) for w in weeks[:-1]]
    final = (
        store.entry(season, week, entry_id)
        if entry_id
        else store.latest_entry(season, week)
    )
    history.append(final)

    previous_ranks = None
    if len(history) > 1:
        from .rank.score import build_ranking

        # `execute` threads previous_ranks forward week by week; this computes
        # the prior week's ranks in one shot. The two agree because
        # previous_ranks only annotates movement -- it never influences the
        # computed ORDER, which is a pure function of the history. If that ever
        # stops being true, test_replay_matches_execute_output will fail.
        previous_ranks = {
            e.team_id: e.rank
            for e in build_ranking(history[:-1]).entries
        }

    archived_article = store.read_article(season, week, final.entry_id)
    content = (
        archived_article.content
        if archived_article and archived_article.is_publishable
        else None
    )

    from .notify import Notification
    from .rank.events import derive_events
    from .rank.score import build_ranking as _br
    from .report import internal as _ir
    from .report import publishable as _pr

    ranking = _br(history, previous_ranks=previous_ranks)
    events = derive_events(final, history[:-1])
    ir = _ir.build(
        season=season, week=week, entry_id=final.entry_id, ranking=ranking, events=events
    )

    # Presentation flags are properties of the RUN that published the page, not
    # of the snapshot -- a week published late carries a "published late" badge
    # forever. Recover them from the archived publishable report rather than
    # recomputing, or replay silently re-renders a backfilled week as current
    # and SC-005's byte-identity claim fails.
    archived_flags = store.read_publishable_raw(season, week, final.entry_id) or {}
    pr = _pr.build(
        internal=ir,
        history=history,
        is_projection=bool(archived_flags.get("is_projection", False)),
        is_current_week=bool(archived_flags.get("is_current_week", True)),
        is_provisional=bool(archived_flags.get("is_provisional", False)),
    )
    page = render_page(
        report=pr,
        entry_id=final.entry_id,
        generated_at=generated_at,
        article=content,
    )
    validate_page(page)
    _ = Notification, build_week_page  # keep imports meaningful for callers
    return page


def cmd_replay(args: argparse.Namespace) -> int:
    """Regenerate a past week from the archive. No network. No model."""
    store = _store(args.archive)
    entry_id = args.entry
    if args.latest:
        entry_id = None
    elif entry_id is None:
        entry_id = _published_entry_id(args) or None

    try:
        page = _render_archived(
            store, args.season, args.week, args.generated_at, entry_id
        )
    except (PageInvalid, ValidationError, ValueError) as exc:
        log.error("replay failed: %s", exc)
        return EXIT_RENDER

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / page.path).write_text(page.html, encoding="utf-8")
    log.info("replayed week %s from %s -> %s", page.week, page.entry_id, out / page.path)
    return EXIT_OK


def _published_entry_id(args: argparse.Namespace) -> str | None:
    """Read the entry_id recorded in the published page, if reachable."""
    if not args.against:
        return None
    candidate = Path(args.against) / f"week-{args.week:02d}.html"
    if not candidate.is_file():
        return None
    import re

    match = re.search(r"provenance: entry=(\S+)", candidate.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def cmd_leagues(args: argparse.Namespace) -> int:
    """List the leagues this account can actually see, with their exact keys."""
    from .diagnose import explain_403, list_leagues

    try:
        provider = _provider_from_env()
    except ProviderError as exc:
        log.error("%s", exc)
        return EXIT_ACQUIRE

    try:
        leagues = list_leagues(provider)
    except ProviderError as exc:
        log.error("could not list leagues: %s", exc)
        return EXIT_ACQUIRE

    configured = os.environ.get("YAHOO_LEAGUE_KEY", "")
    if not leagues:
        log.error("Yahoo returned no NBA leagues for this account.")
    for league in leagues:
        marker = "  <-- YAHOO_LEAGUE_KEY" if league["league_key"] == configured else ""
        log.info(
            "%s  %s (%s season, %s teams, %s)%s",
            league["league_key"],
            league["name"] or "(unnamed)",
            league["season"] or "?",
            league["teams"] or "?",
            league["scoring"] or "?",
            marker,
        )

    for note in explain_403(configured, leagues):
        log.warning("%s", note)

    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    """Compare a replayed week byte-for-byte against what is published."""
    if not args.against:
        log.error("verify needs --against <path> to a checkout of the pages branch")
        return EXIT_RENDER
    published = Path(args.against) / f"week-{args.week:02d}.html"
    if not published.is_file():
        log.error("no published page at %s", published)
        return EXIT_RENDER

    store = _store(args.archive)
    entry_id = _published_entry_id(args)
    try:
        page = _render_archived(
            store, args.season, args.week, args.generated_at, entry_id
        )
    except (PageInvalid, ValidationError, ValueError) as exc:
        log.error("verify failed to render: %s", exc)
        return EXIT_RENDER

    if page.html == published.read_text(encoding="utf-8"):
        log.info("week %s matches what is published", args.week)
        return EXIT_OK
    log.error("week %s differs from what is published", args.week)
    return EXIT_RENDER


# --- argument parsing ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccsv-rumble")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--season", default=DEFAULT_SEASON)
        p.add_argument("--archive", type=Path, default=Path("archive"))
        p.add_argument("--projections", default="data/projections.csv")

    run = sub.add_parser("run", help="fetch, rank, write, and publish")
    common(run)
    run.add_argument("--week", type=int)
    run.add_argument("--no-backfill", action="store_true")
    run.add_argument("--recheck-weeks", type=int, default=None)
    run.add_argument("--branch", default=config.PUBLISH_BRANCH_DEFAULT)
    run.set_defaults(from_archive=False, no_article=False, out="build")

    dry = sub.add_parser("dry-run", help="everything except publishing")
    common(dry)
    dry.add_argument("--week", type=int)
    dry.add_argument("--no-backfill", action="store_true")
    dry.add_argument("--recheck-weeks", type=int, default=None)
    dry.add_argument("--from-archive", action="store_true")
    dry.add_argument("--no-article", action="store_true")
    dry.add_argument("--out", default="build")
    dry.set_defaults(branch=config.PUBLISH_BRANCH_DEFAULT)

    replay = sub.add_parser("replay", help="regenerate a past week from the archive")
    common(replay)
    replay.add_argument("--week", type=int, required=True)
    group = replay.add_mutually_exclusive_group()
    group.add_argument("--entry", help="render this specific archived entry")
    group.add_argument(
        "--latest",
        action="store_true",
        help="render the newest entry; output is NOT expected to match what was published",
    )
    replay.add_argument("--against", type=Path, default=None)
    replay.add_argument("--out", default="build")
    replay.add_argument("--generated-at", dest="generated_at", default="")

    sub.add_parser(
        "leagues",
        help="list the leagues this account can see, with their exact league keys",
    )

    verify = sub.add_parser("verify", help="compare a replay against the published page")
    common(verify)
    verify.add_argument("--week", type=int, required=True)
    verify.add_argument("--against", type=Path, required=True)
    verify.add_argument("--generated-at", dest="generated_at", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args, dry_run=False)
    if args.command == "dry-run":
        return cmd_run(args, dry_run=True)
    if args.command == "leagues":
        return cmd_leagues(args)
    if args.command == "replay":
        return cmd_replay(args)
    if args.command == "verify":
        return cmd_verify(args)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
