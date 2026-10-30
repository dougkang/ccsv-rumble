"""Principle II: no commit when the output is unchanged.

Without this, the publish branch accrues an empty commit every single week
forever, and "something changed" stops being a useful signal in its history.

These tests use a local bare repository as the remote, so nothing leaves the
machine.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ccsv_rumble.publish import StagedSite, publish


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "pages", str(remote)], check=True)
    return remote


def _publish(staged: StagedSite, remote: Path, tmp_path: Path, message: str) -> bool:
    # `repository` is interpolated into a URL; a local path works for tests.
    return publish(
        staged,
        repository=str(remote),
        branch="pages",
        token=None,
        commit_message=message,
        workdir=tmp_path / f"work-{message}",
    )


def _site(body: str) -> StagedSite:
    staged = StagedSite()
    staged.files["week-01.html"] = body
    staged.files["index.html"] = "<html>index</html>"
    staged.files["robots.txt"] = "User-agent: *\nDisallow: /\n"
    return staged


def test_first_publish_creates_a_commit(bare_remote: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ccsv_rumble.publish._remote_url", lambda repository, token: repository
    )
    (tmp_path / "work-first").mkdir()
    assert _publish(_site("<html>v1</html>"), bare_remote, tmp_path, "first") is True


def test_republishing_identical_content_creates_no_commit(
    bare_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ccsv_rumble.publish._remote_url", lambda repository, token: repository
    )
    for name in ("first", "second"):
        (tmp_path / f"work-{name}").mkdir()

    assert _publish(_site("<html>v1</html>"), bare_remote, tmp_path, "first") is True
    assert _publish(_site("<html>v1</html>"), bare_remote, tmp_path, "second") is False, (
        "identical output must not create a commit"
    )

    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=bare_remote, capture_output=True, text=True, check=True,
    )
    assert len(log.stdout.strip().splitlines()) == 1


def test_changed_content_does_create_a_commit(
    bare_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ccsv_rumble.publish._remote_url", lambda repository, token: repository
    )
    for name in ("first", "second"):
        (tmp_path / f"work-{name}").mkdir()

    assert _publish(_site("<html>v1</html>"), bare_remote, tmp_path, "first") is True
    assert _publish(_site("<html>v2</html>"), bare_remote, tmp_path, "second") is True


def test_publishing_one_week_keeps_earlier_week_pages(
    bare_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    """A week-1 run stages only week 1; week 0 must survive on the branch."""
    monkeypatch.setattr(
        "ccsv_rumble.publish._remote_url", lambda repository, token: repository
    )
    for name in ("week0", "week1", "check"):
        (tmp_path / f"work-{name}").mkdir()

    week0 = StagedSite()
    week0.files["week-00.html"] = "<html>week 0</html>"
    week0.files["index.html"] = "<html>index 0</html>"
    assert _publish(week0, bare_remote, tmp_path, "week0") is True
    assert _publish(_site("<html>week 1</html>"), bare_remote, tmp_path, "week1") is True

    files = subprocess.run(
        ["git", "ls-tree", "--name-only", "pages"],
        cwd=bare_remote, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "week-00.html" in files
    assert "week-01.html" in files
