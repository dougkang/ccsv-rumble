"""Page validation. The gate publishing is conditioned on (Principle II).

Checks structure and budget only -- article CONTENT validation lives in
`article/validate.py`, because a hallucinated trade passes every check here while
being worse than a broken page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from .. import config
from ..models import PublishedPage

_PLACEHOLDER_PATTERNS = (
    re.compile(r"\blorem ipsum\b", re.I),
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\{\{.*?\}\}"),  # an unrendered Jinja expression
)


class PageInvalid(RuntimeError):
    pass


@dataclass(frozen=True)
class _Structure:
    h1_count: int = 0
    table_count: int = 0
    has_robots_noindex: bool = False
    scoped_headers: int = 0
    external_refs: tuple[str, ...] = ()


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.h1 = 0
        self.tables = 0
        self.noindex = False
        self.scoped = 0
        self.external: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag == "h1":
            self.h1 += 1
        elif tag == "table":
            self.tables += 1
        elif tag == "th" and attr.get("scope"):
            self.scoped += 1
        elif (
            tag == "meta"
            and attr.get("name", "").lower() == "robots"
            and "noindex" in attr.get("content", "").lower()
        ):
            self.noindex = True
        for key in ("src", "href"):
            value = attr.get(key, "")
            if value.startswith(("http://", "https://", "//")):
                self.external.append(value)


def inspect(html: str) -> _Structure:
    parser = _Parser()
    parser.feed(html)
    return _Structure(
        h1_count=parser.h1,
        table_count=parser.tables,
        has_robots_noindex=parser.noindex,
        scoped_headers=parser.scoped,
        external_refs=tuple(parser.external),
    )


def validate_page(page: PublishedPage) -> None:
    """Raise `PageInvalid` on anything that must block publication."""
    problems: list[str] = []
    html = page.html

    structure = inspect(html)
    if structure.h1_count != 1:
        problems.append(f"expected exactly one <h1>, found {structure.h1_count}")
    if structure.table_count < 1:
        problems.append("rankings table is missing")
    if not structure.has_robots_noindex:
        problems.append("missing noindex directive (FR-051)")
    if structure.scoped_headers < 1:
        problems.append("table headers lack scope attributes")
    if structure.external_refs:
        problems.append(
            f"page fetches third-party resources at load: {list(structure.external_refs)}"
        )

    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.search(html):
            problems.append(f"placeholder content matched {pattern.pattern!r}")

    # FR-029: no ranking-derived figure in ANY form -- including the places a
    # type-level guarantee cannot reach, like markup comments, data attributes,
    # alt text and tooltips. `PublishableTeam` has no field able to hold one,
    # which stops the ordinary path; this catches a template or a serialized
    # blob that bypassed it.
    lowered = html.lower()
    leaked = [name for name in config.DRAFT_INTERNAL_IDENTIFIERS if name in lowered]
    if leaked:
        problems.append(
            f"ranking-derived identifiers reached the page: {leaked} (FR-029)"
        )

    size = len(html.encode("utf-8"))
    if size > config.PAGE_WEIGHT_BUDGET_BYTES:
        problems.append(
            f"page is {size} bytes, over the {config.PAGE_WEIGHT_BUDGET_BYTES} budget"
        )

    if problems:
        raise PageInvalid(
            f"week {page.week} page failed validation: " + "; ".join(problems)
        )
