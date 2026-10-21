"""Deterministic rendering. PURE.

Given an identical snapshot, rendering MUST produce byte-identical HTML. Three
rules enforce that and all three are easy to break by accident:

  1. `generated_at` is an explicit PARAMETER. This module never reads a clock.
  2. Every iteration is over an explicitly ordered sequence.
  3. Rounding happens here, at the display boundary, never mid-computation.

The golden-file test is the enforcement mechanism.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .. import config
from ..models import ArticleContent, Movement, PublishableReport, PublishedPage

TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


@lru_cache(maxsize=1)
def stylesheet() -> str:
    return (TEMPLATE_DIR / "style.css").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def robots_txt() -> str:
    return (TEMPLATE_DIR / "robots.txt").read_text(encoding="utf-8")


def week_path(week: int) -> str:
    """Stable per-week address. Never changes once published (FR-040)."""
    return f"week-{week:02d}.html"


def _move_label(team) -> str:
    if team.movement is Movement.UNAVAILABLE or team.rank_change is None:
        return "new"
    if team.rank_change > 0:
        return f"up {team.rank_change}"
    if team.rank_change < 0:
        return f"down {abs(team.rank_change)}"
    return "even"


def _move_class(team) -> str:
    if team.movement is Movement.UNAVAILABLE or team.rank_change is None:
        return "move-new"
    if team.rank_change > 0:
        return "move-up"
    if team.rank_change < 0:
        return "move-down"
    return "move-flat"


def render_page(
    *,
    report: PublishableReport,
    entry_id: str,
    generated_at: str,
    article: ArticleContent | None = None,
) -> PublishedPage:
    """Render one week.

    When `article` is None the article section is omitted ENTIRELY -- no
    placeholder, no explanatory note, no carried-forward article (FR-030a). The
    page gives the reader no indication that an article was expected, which is
    why the notification channel is the only signal (FR-030b).
    """
    names = {team.team_id: team.team_name for team in report.teams}
    html = _environment().get_template("page.html.j2").render(
        report=report,
        article=article,
        entry_id=entry_id,
        algorithm_version=config.ALGORITHM_VERSION,
        generated_at=generated_at,
        stylesheet=stylesheet(),
        move_label=_move_label,
        move_class=_move_class,
        team_name=lambda team_id: names.get(team_id, team_id),
    )
    return PublishedPage(
        season=report.season,
        week=report.week,
        entry_id=entry_id,
        algorithm_version=config.ALGORITHM_VERSION,
        has_article=article is not None,
        path=week_path(report.week),
        html=html,
    )


@dataclass(frozen=True)
class WeekLink:
    week: int
    path: str


def render_index(*, season: str, weeks: Sequence[int]) -> str:
    """Current-week view plus the per-week link list, newest first."""
    links = [WeekLink(week=w, path=week_path(w)) for w in sorted(weeks, reverse=True)]
    return _environment().get_template("index.html.j2").render(
        season=season,
        weeks=links,
        stylesheet=stylesheet(),
    )
