"""The import rule that makes purity architectural rather than conventional.

Constitution Principle I requires the ranking computation to be "a pure function
of the input snapshot ... free of I/O, network, and filesystem access". A comment
saying so decays; an assertion does not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "ccsv_rumble"

#: Packages that must not appear in a pure module's import graph.
FORBIDDEN = ("fetch", "archive", "publish", "notify", "cli", "pipeline")

PURE_PACKAGES = ("rank", "render", "report")


def _module_files() -> list[Path]:
    files: list[Path] = []
    for package in PURE_PACKAGES:
        files.extend(sorted((SRC / package).rglob("*.py")))
    return files


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.lstrip("."))
            if node.level and not node.module:
                names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level or isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: p.name)
def test_pure_modules_do_not_import_impure_packages(path: Path) -> None:
    offenders = sorted(
        name
        for name in _imported_names(path)
        if any(name == bad or name.startswith(f"{bad}.") for bad in FORBIDDEN)
    )
    assert not offenders, (
        f"{path.relative_to(SRC)} imports {offenders}. Ranking, reporting, and "
        "rendering must stay pure functions of the snapshot (Principle I)."
    )


def test_render_never_reads_a_clock() -> None:
    """`generated_at` is an explicit parameter; render must not call datetime.now."""
    for path in sorted((SRC / "render").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "datetime.now" not in source, (
            f"{path.name} reads a clock. `generated_at` is passed in so that "
            "rendering is byte-identical across runs."
        )


def test_article_package_cannot_reach_the_internal_report() -> None:
    """FR-015: the article stage receives only the publishable report.

    Checks the IMPORT GRAPH, not raw text -- these modules legitimately discuss
    the internal report in prose explaining why they must not import it.
    """
    for path in sorted((SRC / "article").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported: set[str] = set()
            if isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").lstrip("."))
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            offenders = sorted(
                name
                for name in imported
                if name == "InternalReport" or name.endswith("report.internal")
            )
            assert not offenders, (
                f"{path.name} imports {offenders}. If the model is never given "
                "the component metrics, it cannot leak them (FR-015)."
            )
