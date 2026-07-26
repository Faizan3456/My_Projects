"""Turn a free-text agent reply into a memory update.

Agents are asked to end with a fenced json block. Real models sometimes forget,
so parsing degrades in three steps: fenced json -> trailing bare json object ->
heuristic summary of the prose. Memory is never left unwritten because a model
ignored the format.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..models import CONTEXT_STATUSES

FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
TRAILING_JSON = re.compile(r"(\{[^{}]*\"summary\"[^{}]*\})\s*$", re.DOTALL)


@dataclass(slots=True)
class ParsedReply:
    summary: str
    current_task: str | None
    next_step: str | None
    status: str | None
    structured: bool

    @property
    def prose(self) -> str:
        return self.summary


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _summarise_prose(text: str, max_chars: int) -> str:
    # Drop any code fences, then take the first sentences that fit.
    without_code = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    collapsed = " ".join(without_code.split())
    if not collapsed:
        return "(agent returned no text)"
    if len(collapsed) <= max_chars:
        return collapsed
    cut = collapsed[:max_chars]
    boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if boundary > max_chars // 3:
        return cut[: boundary + 1]
    return cut.rstrip() + "…"


def parse_reply(text: str, *, summary_max_chars: int = 600) -> ParsedReply:
    for pattern in (FENCED_JSON, TRAILING_JSON):
        for match in reversed(pattern.findall(text or "")):
            try:
                data = json.loads(match)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            summary = _clean(data.get("summary"))
            if summary is None:
                continue
            status = _clean(data.get("status"))
            if status is not None:
                status = status.lower()
                if status not in CONTEXT_STATUSES:
                    status = None
            return ParsedReply(
                summary=summary[:summary_max_chars],
                current_task=_clean(data.get("current_task")),
                next_step=_clean(data.get("next_step")),
                status=status,
                structured=True,
            )

    return ParsedReply(
        summary=_summarise_prose(text or "", summary_max_chars),
        current_task=None,
        next_step=None,
        status=None,
        structured=False,
    )
