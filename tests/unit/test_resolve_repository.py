"""A local run has no GITHUB_REPOSITORY; publishing must still find its target.

Without a fallback the push URL degraded to `https://github.com/.git` and the
run failed only at the very last step, after all the work was done.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ccsv_rumble.publish import PublishError, resolve_repository


def _repo_with_origin(path: Path, origin: str | None) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if origin is not None:
        subprocess.run(["git", "remote", "add", "origin", origin], cwd=path, check=True)
    return path


def test_the_environment_wins(tmp_path: Path) -> None:
    repo = _repo_with_origin(tmp_path, "https://github.com/someone/else.git")
    assert resolve_repository("owner/name", cwd=repo) == "owner/name"


@pytest.mark.parametrize(
    "origin",
    [
        "https://github.com/dougkang/ccsv-rumble.git",
        "https://github.com/dougkang/ccsv-rumble",
        "git@github.com:dougkang/ccsv-rumble.git",
        "ssh://git@github.com/dougkang/ccsv-rumble.git",
    ],
)
def test_a_local_run_falls_back_to_origin(tmp_path: Path, origin: str) -> None:
    repo = _repo_with_origin(tmp_path, origin)
    assert resolve_repository(None, cwd=repo) == "dougkang/ccsv-rumble"


def test_no_target_is_a_clear_error_not_a_bad_url(tmp_path: Path) -> None:
    repo = _repo_with_origin(tmp_path, None)
    with pytest.raises(PublishError, match="GITHUB_REPOSITORY"):
        resolve_repository("", cwd=repo)
