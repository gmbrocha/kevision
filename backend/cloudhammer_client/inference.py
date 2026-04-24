from __future__ import annotations

from typing import Protocol

import fitz

from ..revision_state.models import SheetVersion
from .schemas import CloudDetection


class CloudInferenceClient(Protocol):
    """Boundary between backend orchestration and CloudHammer inference."""

    def detect(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudDetection]:
        ...


class NullCloudInferenceClient:
    """Default placeholder until the local CloudHammer model is wired in."""

    name = "disabled"

    def detect(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudDetection]:
        return []
