"""Article generation -- the one nondeterministic stage.

It is confined to ACQUISITION: its output is archived into the snapshot and
replayed from there, so rendering stays deterministic and regeneration never
calls a model (constitution Principle I).

This module accepts only `PublishableReport`. `InternalReport` must never become
importable here -- if the model is not given the component metrics, it cannot
leak them no matter how the prompt is worded.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .. import config
from ..models import (
    Article,
    ArticleContent,
    PublishableReport,
    TeamNote,
    ValidationFailure,
    ValidationOutcome,
)
from .prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT, build_user_message


class ArticleUnavailable(RuntimeError):
    """Generation failed. Handled as a degraded publish, never as a crash."""


def _failed(week: int, reason: str, model: str = config.ARTICLE_MODEL) -> Article:
    now = datetime.now(UTC)
    return Article(
        week=week,
        model=model,
        generated_at=now,
        content=None,
        validation=ValidationOutcome(
            passed=False,
            checked_at=now,
            failures=(ValidationFailure(check="generation", message=reason),),
        ),
    )


def parse_content(payload: dict[str, Any]) -> ArticleContent:
    return ArticleContent(
        headline=str(payload["headline"]).strip(),
        intro=str(payload["intro"]).strip(),
        outro=str(payload["outro"]).strip(),
        team_notes=tuple(
            TeamNote(
                team_id=str(note["team_id"]),
                prose=str(note["prose"]).strip(),
                attributed_event_ids=tuple(note.get("attributed_event_ids") or ()),
            )
            for note in payload["team_notes"]
        ),
    )


def generate_article(report: PublishableReport, client: Any) -> Article:
    """Ask Claude for the week's column.

    Never raises on an upstream problem: every failure becomes an Article with
    `content=None` and a recorded reason, because FR-029 makes a missing article
    a degraded publish rather than a failed run.
    """
    try:
        response = client.beta.messages.create(
            model=config.ARTICLE_MODEL,
            max_tokens=config.ARTICLE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(report)}],
            output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            betas=[config.ARTICLE_FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:  # noqa: BLE001 -- any upstream failure degrades, never crashes
        return _failed(report.week, f"{type(exc).__name__}: {exc}")

    # Check stop_reason BEFORE touching content. A refusal returns HTTP 200 with
    # possibly empty content, so indexing content[0] unconditionally would crash
    # the run rather than degrading it.
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        return _failed(report.week, f"model declined the request (category={category})")
    if stop_reason == "max_tokens":
        return _failed(report.week, "response hit max_tokens and is incomplete")

    blocks = getattr(response, "content", None) or []
    text = next(
        (getattr(b, "text", None) for b in blocks if getattr(b, "type", "") == "text"),
        None,
    )
    if not text:
        return _failed(report.week, f"no text content in response (stop={stop_reason})")

    try:
        content = parse_content(json.loads(text))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return _failed(report.week, f"unparseable response: {type(exc).__name__}: {exc}")

    now = datetime.now(UTC)
    return Article(
        week=report.week,
        model=getattr(response, "model", config.ARTICLE_MODEL),
        generated_at=now,
        content=content,
        # Content validation runs separately and replaces this outcome.
        validation=ValidationOutcome(passed=True, checked_at=now),
    )
