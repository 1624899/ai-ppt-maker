from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentDraft:
    draft_id: str
    operation_type: str
    edit_kind: str
    page_no: int | None
    affected_pages: list[int]
    instruction: str
    summary: str
    changes: list[str]
    confidence: str
    needs_confirmation: bool = True
    image_annotations: list[dict[str, Any]] | None = None
