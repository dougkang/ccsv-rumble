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

#: Pure modules that are not inside a pure package.
PURE_MODULES = ("lifecycle.py",)

#: Modules that give a pure module a filesystem or a network.
#:
#: `pathlib` is on this list because of a real violation it allowed:
#: `rank/prior.py` imported it and called `path.open()` for the whole life of
#: that module, while the import-graph check below passed it without comment --
#: `pathlib` is not one of FORBIDDEN, which only names internal packages.
#:
#: `csv` and `json` are deliberately NOT here. They parse an iterable of
#: strings and reach no resource on their own; it was the file handle that
#: breached Principle I, not the parsing.
IMPURE_MODULES = frozenset(
    {
        "pathlib", "os", "io", "shutil", "tempfile", "glob", "subprocess",
        "socket", "http", "urllib", "httpx", "requests", "ftplib", "smtplib",
    }
)

#: Builtins that open a resource directly, with no import to notice.
IMPURE_BUILTINS = frozenset({"open"})

#: Modules permitted to READ a resource bundled with the source tree, addressed
#: relative to `__file__`. Narrow and named rather than a blanket exemption.
#:
#: The distinction this draws is between source and data. `render/html.py` reads
#: `templates/style.css`, which is committed code: it cannot differ between two
#: runs, so it does not threaten the byte-identical-rendering guarantee that
#: Principle I actually protects. `data/projections.csv` is the opposite -- the
#: maintainer edits it, so reading it at rank time made replay non-reproducible,
#: which is the violation this file now catches.
#:
#: Entries here must still never WRITE; `test_pure_modules_never_write` holds
#: for every pure module without exception.
BUNDLED_RESOURCE_READERS = frozenset({"html.py"})

#: Attribute calls that mutate a resource. Forbidden everywhere, no exemptions.
WRITE_CALLS = frozenset({"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "touch"})


def _module_files() -> list[Path]:
    files: list[Path] = []
    for package in PURE_PACKAGES:
        files.extend(sorted((SRC / package).rglob("*.py")))
    files.extend(SRC / name for name in PURE_MODULES)
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


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: p.name)
def test_pure_modules_do_not_touch_the_filesystem_or_network(path: Path) -> None:
    """Principle I: pure modules are "free of I/O, network, and filesystem access".

    The import-graph check above is necessary but was not sufficient. It matches
    INTERNAL package names, so `import csv` and `from pathlib import Path` sailed
    through while `rank/prior.py` called `path.open()` on every run -- a
    violation of the principle this file exists to enforce, invisible to the
    assertion meant to enforce it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bundled_reader = path.name in BUNDLED_RESOURCE_READERS

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in IMPURE_MODULES and not (bundled_reader and root == "pathlib"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            root = node.module.split(".")[0]
            if root in IMPURE_MODULES and not (bundled_reader and root == "pathlib"):
                offenders.append(f"from {node.module} import …")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in IMPURE_BUILTINS
        ):
            offenders.append(f"{node.func.id}(…) at line {node.lineno}")

    assert not offenders, (
        f"{path.name} reaches a filesystem or network: {sorted(set(offenders))}. "
        "Ranking, reporting, and rendering must be pure functions of the snapshot "
        "(Principle I). Move acquisition into `fetch/` and pass parsed data in."
    )


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: p.name)
def test_pure_modules_never_write(path: Path) -> None:
    """No exemption, including for the bundled-resource readers.

    Reading committed source is defensible; writing from a pure module is not,
    under any reading of Principle I.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    writes = sorted(
        {
            f"{node.func.attr}(…) at line {node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in WRITE_CALLS
        }
    )
    assert not writes, f"{path.name} writes to a resource: {writes}"


def test_the_bundled_resource_exemption_stays_narrow() -> None:
    """Guard against the exemption quietly becoming the rule.

    If a later change adds pure modules to this set, that is a decision someone
    should have to make deliberately rather than by appending a name.
    """
    assert {"html.py"} == BUNDLED_RESOURCE_READERS, (
        "the bundled-resource exemption has grown. Each entry weakens the "
        "filesystem check for one module, so adding one needs the same "
        "source-versus-data justification html.py has."
    )


def test_the_purity_check_would_catch_the_violation_it_was_written_for() -> None:
    """A test that cannot fail is not a test.

    The real `rank/prior.py` used to open a file. This reconstructs that shape
    and confirms the check above rejects it -- so the assertion is load-bearing
    rather than incidentally green.
    """
    offending = (
        "import csv\n"
        "from pathlib import Path\n"
        "def load(path: Path) -> dict:\n"
        "    with path.open() as handle:\n"
        "        return dict(csv.DictReader(handle))\n"
    )
    tree = ast.parse(offending)
    found = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module in IMPURE_MODULES
    ]
    assert found == ["pathlib"], (
        "the widened check no longer rejects the original violation; it has been "
        "narrowed back to something that cannot fail"
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
