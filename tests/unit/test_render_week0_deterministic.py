"""Golden-file test for the week-0 page (Principle I's enforcement mechanism).

The week-0 page takes a different ranking path from every other week -- ordered
by DraftScore rather than by played results -- so the existing week-01 golden
file does not cover it. A rendering diff here blocks merge.

The cross-process run is the part that earns its keep: the projected grid sorts
rosters, slot candidates and teams, and a missing sort would be invisible inside
one interpreter because PYTHONHASHSEED is fixed per process.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

from ccsv_rumble import config
from ccsv_rumble.fetch.projections import LocalFileProjectionProvider
from ccsv_rumble.fetch.projections import acquire as acquire_projections
from ccsv_rumble.rank import draft_score as draft_scoring
from ccsv_rumble.rank import projected as projected_grid
from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.render.html import render_page
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from tests.conftest import make_post_draft_snapshot

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "golden" / "week-00.html"
FIXTURE = REPO / "tests" / "fixtures" / "projections-valid.csv"


def render_week_zero_page() -> str:
    snapshot = make_post_draft_snapshot()
    projections = acquire_projections(
        LocalFileProjectionProvider(FIXTURE, source_id="golden-fixture"),
        "2026-27",
        0,
        now=datetime(2026, 10, 22, 12, 0, tzinfo=UTC),
    )
    grid = projected_grid.build_projected_grid(snapshot.rosters, projections)
    entries = draft_scoring.score(grid)
    ranking = draft_scoring.build_draft_ranking(entries, week=0)

    report = internal_report.build(
        season="2026-27", week=0, entry_id="entry-001",
        ranking=ranking, events=derive_events(snapshot),
    )
    public = publishable_report.build(
        internal=report, history=[snapshot], is_projection=True
    )
    return render_page(
        report=public,
        entry_id="entry-001",
        generated_at="2026-10-22",
        draft_algorithm_version=config.DRAFT_ALGORITHM_VERSION,
    ).html


def test_two_renders_in_one_process_are_byte_identical() -> None:
    assert render_week_zero_page() == render_week_zero_page()


def test_week_zero_render_is_stable_across_processes() -> None:
    """Catches an unsorted collection in the projected grid or slot filling."""
    script = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, "src")
        sys.path.insert(0, ".")
        from tests.unit.test_render_week0_deterministic import render_week_zero_page
        sys.stdout.write(render_week_zero_page())
        """
    )
    runs = []
    for seed in ("0", "1", "random"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO,
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 0, result.stderr
        runs.append(result.stdout)

    assert runs[0] == runs[1] == runs[2], (
        "week-0 rendering differs across hash seeds -- the projected grid or the "
        "slot filling iterates an unordered collection without an explicit sort"
    )


def test_matches_the_golden_file() -> None:
    """An unexplained diff blocks merge (constitution pre-merge gate 3)."""
    rendered = render_week_zero_page()
    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(rendered, encoding="utf-8")
    assert rendered == GOLDEN.read_text(encoding="utf-8"), (
        "rendered output no longer matches tests/golden/week-00.html. If the "
        "change is intentional, review the diff and update the golden file."
    )


def test_the_golden_page_leaks_no_ranking_figure() -> None:
    """Belt and braces on the committed artifact itself.

    The golden file is the one page a reviewer actually reads, so it is worth
    asserting directly rather than only through the renderer.
    """
    html = render_week_zero_page().lower()
    for identifier in config.DRAFT_INTERNAL_IDENTIFIERS:
        assert identifier not in html, f"{identifier!r} is in the week-0 page"
    assert "draft-algorithm=draft-v1" in html
