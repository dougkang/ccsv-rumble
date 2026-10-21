"""Publishing: stage every week, diff, then ONE commit and ONE push.

Two rules from Principle II shape this module:

  All-or-nothing. Every week a run produced is staged before anything is pushed,
  so a partial backfill is never visible. A failure before this point publishes
  nothing and leaves the previous site live.

  No commit when unchanged. A run whose staged output is byte-identical to what
  is published must not create a commit, or the publish branch accrues an empty
  commit every week forever.

The target is a BRANCH of this same repository, not a separate repo, so the
Actions-provided GITHUB_TOKEN suffices -- there is no stored PAT to rotate.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .models import PublishedPage
from .render.html import render_index, robots_txt


class PublishError(RuntimeError):
    pass


@dataclass
class StagedSite:
    """The complete site content for this run, keyed by published path."""

    files: dict[str, str] = field(default_factory=dict)

    def add_page(self, page: PublishedPage) -> None:
        self.files[page.path] = page.html

    def finalize(self, *, season: str, weeks: Sequence[int]) -> None:
        self.files["index.html"] = render_index(season=season, weeks=weeks)
        self.files["robots.txt"] = robots_txt()
        # Disable Jekyll so files beginning with _ are served verbatim.
        self.files.setdefault(".nojekyll", "")


def _git(args: Sequence[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PublishError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def _remote_url(repository: str, token: str | None) -> str:
    if token:
        return f"https://x-access-token:{token}@github.com/{repository}.git"
    return f"https://github.com/{repository}.git"


def publish(
    staged: StagedSite,
    *,
    repository: str,
    branch: str,
    token: str | None,
    commit_message: str,
    author_name: str = "github-actions[bot]",
    author_email: str = "41898282+github-actions[bot]@users.noreply.github.com",
    workdir: Path | None = None,
) -> bool:
    """Push the staged site. Returns True if a commit was created.

    Returns False -- without erroring -- when the staged output matches what is
    already published.
    """
    temp_root = Path(tempfile.mkdtemp(prefix="ccsv-publish-")) if workdir is None else workdir
    checkout = temp_root / "site"
    try:
        url = _remote_url(repository, token)
        try:
            _git(
                ["clone", "--depth", "1", "--branch", branch, url, str(checkout)],
                cwd=temp_root,
            )
        except PublishError:
            # The branch does not exist yet -- create it as an orphan.
            checkout.mkdir(parents=True, exist_ok=True)
            _git(["init", "-q", "-b", branch], cwd=checkout)
            _git(["remote", "add", "origin", url], cwd=checkout)

        # Replace tracked content wholesale so a removed page actually disappears.
        for existing in checkout.iterdir():
            if existing.name == ".git":
                continue
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()

        for relative, content in sorted(staged.files.items()):
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        _git(["add", "-A"], cwd=checkout)
        status = _git(["status", "--porcelain"], cwd=checkout).strip()
        if not status:
            return False

        _git(["-c", f"user.name={author_name}", "-c", f"user.email={author_email}",
              "commit", "-q", "-m", commit_message], cwd=checkout)
        _git(["push", "origin", f"HEAD:{branch}"], cwd=checkout)
        return True
    finally:
        if workdir is None:
            shutil.rmtree(temp_root, ignore_errors=True)
