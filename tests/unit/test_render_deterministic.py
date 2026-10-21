"""The golden-file test the constitution names as Principle I's enforcement.

Renders the same snapshot twice in one process, and again in a SUBPROCESS. The
subprocess run is what catches hash-seed-dependent iteration, which is invisible
within a single interpreter because PYTHONHASHSEED is fixed per process.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from ccsv_rumble.rank.events import derive_events
from ccsv_rumble.rank.score import build_ranking
from ccsv_rumble.render.html import render_page
from ccsv_rumble.report import internal as internal_report
from ccsv_rumble.report import publishable as publishable_report
from tests.conftest import make_snapshot

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "golden" / "week-01.html"


def render_fixture_page() -> str:
    snapshot = make_snapshot(1)
    ranking = build_ranking([snapshot])
    events = derive_events(snapshot)
    report = internal_report.build(
        season="2026-27", week=1, entry_id="entry-001", ranking=ranking, events=events
    )
    public = publishable_report.build(
        internal=report, history=[snapshot], is_projection=False
    )
    return render_page(
        report=public, entry_id="entry-001", generated_at="2026-10-27"
    ).html


def test_two_renders_in_one_process_are_byte_identical() -> None:
    assert render_fixture_page() == render_fixture_page()


def test_render_is_stable_across_processes() -> None:
    """Catches unsorted-set iteration, which varies with the hash seed."""
    script = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, "src")
        sys.path.insert(0, ".")
        from tests.unit.test_render_deterministic import render_fixture_page
        sys.stdout.write(render_fixture_page())
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
        "rendering differs across hash seeds -- something iterates an unordered "
        "collection without an explicit sort"
    )


def test_matches_the_golden_file() -> None:
    """An unexplained diff here blocks merge (constitution pre-merge gate 3)."""
    rendered = render_fixture_page()
    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(rendered, encoding="utf-8")
    assert rendered == GOLDEN.read_text(encoding="utf-8"), (
        "rendered output no longer matches tests/golden/week-01.html. If the "
        "change is intentional, review the diff and update the golden file."
    )
