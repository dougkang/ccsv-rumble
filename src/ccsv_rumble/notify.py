"""Failure and degradation notifications.

Because the page omits a failed article silently (FR-030a), the page carries no
signal that anything went wrong. That makes this channel the ONLY signal, which
is why FR-030b treats a successful publish with a failed notification as a
non-success rather than a warning.

Opens or updates a single GitHub issue per notification kind, so a recurring
failure does not produce a pile of duplicates.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

ISSUE_LABEL = "automated-run"


class NotifyError(RuntimeError):
    """The notification could not be delivered."""


@dataclass
class Notification:
    """Everything one run needs to report."""

    backfilled_weeks: list[int] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    article_failures: list[str] = field(default_factory=list)
    run_failure: str | None = None

    @property
    def has_content(self) -> bool:
        return bool(
            self.backfilled_weeks
            or self.corrections
            or self.article_failures
            or self.run_failure
        )

    def title(self) -> str:
        if self.run_failure:
            return "Rankings run failed"
        return "Rankings run: degraded or notable"

    def body(self) -> str:
        lines: list[str] = []
        if self.run_failure:
            lines += ["## Run failed", "", self.run_failure, ""]
        if self.article_failures:
            lines += ["## Article failures", ""]
            lines += [f"- {item}" for item in self.article_failures]
            lines += [
                "",
                "_The page published with rankings only. It shows no sign of this_",
                "_(FR-030a), so this notification is the only signal._",
                "",
            ]
        if self.backfilled_weeks:
            weeks = ", ".join(str(w) for w in sorted(self.backfilled_weeks))
            lines += ["## Backfilled weeks", "", f"- {weeks}", ""]
        if self.corrections:
            lines += ["## Upstream corrections detected", ""]
            lines += [f"- {item}" for item in self.corrections]
            lines += [
                "",
                "_Corrected data feeds current and future rankings. The already-_",
                "_published page for that week was intentionally left unchanged._",
                "",
            ]
        return "\n".join(lines).strip() + "\n"


class Notifier(Protocol):
    def send(self, notification: Notification) -> None: ...


class NullNotifier:
    """Used in tests and local dry runs. Records instead of sending."""

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


class FailingNotifier:
    """Test double for the FR-030b path."""

    def send(self, notification: Notification) -> None:
        raise NotifyError("notification channel unavailable")


class GitHubIssueNotifier:
    """Opens or updates an issue using the Actions-provided token.

    No stored PAT: the workflow's built-in GITHUB_TOKEN carries `issues: write`
    and is rotated per run.
    """

    def __init__(self, repository: str, token: str, api_base: str = "https://api.github.com") -> None:
        self._repository = repository
        self._token = token
        self._api = api_base.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None) -> list | dict:
        url = f"{self._api}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode() or "null")
        except urllib.error.URLError as exc:
            raise NotifyError(f"GitHub API {method} {path} failed: {exc}") from exc

    def send(self, notification: Notification) -> None:
        if not notification.has_content:
            return
        title = notification.title()
        existing = self._request(
            "GET", f"/repos/{self._repository}/issues?state=open&labels={ISSUE_LABEL}"
        )
        match = None
        if isinstance(existing, list):
            match = next((i for i in existing if i.get("title") == title), None)

        if match:
            self._request(
                "POST",
                f"/repos/{self._repository}/issues/{match['number']}/comments",
                {"body": notification.body()},
            )
        else:
            self._request(
                "POST",
                f"/repos/{self._repository}/issues",
                {
                    "title": title,
                    "body": notification.body(),
                    "labels": [ISSUE_LABEL],
                },
            )
