from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ChangeItem, VerificationRecord
from .utils import stable_id
from .workspace import WorkspaceStore


@dataclass
class VerificationProvider:
    name: str = "disabled"

    @property
    def enabled(self) -> bool:
        return False

    def verify_change(self, change_item_id: str, context_bundle: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Verification is disabled. Set OPENAI_API_KEY to enable it.")


class OpenAIVerificationProvider(VerificationProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        super().__init__(name="openai")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_VERIFY_MODEL", "gpt-4.1-mini")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def verify_change(self, change_item_id: str, context_bundle: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Verification is disabled. Set OPENAI_API_KEY to enable it.")

        request_payload = self._build_payload(context_bundle)
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI verification failed: {exc.code} {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI verification failed: {exc.reason}") from exc

        output_text = self._extract_output_text(raw_response)
        parsed = self._parse_output(output_text)
        parsed["provider_raw_response"] = raw_response
        parsed["request_payload"] = request_payload
        return parsed

    def _build_payload(self, context_bundle: dict[str, Any]) -> dict[str, Any]:
        user_content = [
            {
                "type": "input_text",
                "text": (
                    "Verify or clarify this construction drawing change candidate. "
                    "Do not invent scope. If the evidence is ambiguous, say so. "
                    "Return JSON only."
                ),
            },
            {
                "type": "input_text",
                "text": json.dumps(context_bundle, indent=2),
            },
        ]
        for key in ("crop_image_path", "page_image_path"):
            image_path = context_bundle.get(key)
            if image_path and Path(image_path).exists():
                user_content.append(
                    {
                        "type": "input_image",
                        "image_url": self._data_url(Path(image_path)),
                    }
                )

        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You are reviewing construction drawing revision candidates. "
                                "You may only verify, clarify, or flag ambiguity in an existing candidate. "
                                "You must not invent new change items. "
                                "Respond as compact JSON with keys: verdict, corrected_text, reasoning, confidence, warnings."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        }

    def _extract_output_text(self, payload: dict[str, Any]) -> str:
        output = payload.get("output", [])
        for item in output:
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    return content.get("text", "")
        return payload.get("output_text", "")

    def _parse_output(self, text: str) -> dict[str, Any]:
        if not text:
            return {
                "verdict": "ambiguous",
                "corrected_text": "",
                "reasoning": "No output returned by the model.",
                "confidence": 0.0,
                "warnings": ["empty_output"],
            }
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "verdict": "ambiguous",
                "corrected_text": "",
                "reasoning": text.strip(),
                "confidence": 0.0,
                "warnings": ["non_json_output"],
            }

    def _data_url(self, image_path: Path) -> str:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"


def build_context_bundle(store: WorkspaceStore, change_item: ChangeItem) -> dict[str, Any]:
    sheet = store.get_sheet(change_item.sheet_version_id)
    cloud = store.get_cloud(change_item.cloud_candidate_id) if change_item.cloud_candidate_id else None
    verifications = [record.response_payload for record in store.change_verifications(change_item.id)]
    return {
        "change_item_id": change_item.id,
        "sheet_id": change_item.sheet_id,
        "detail_ref": change_item.detail_ref,
        "raw_text": change_item.raw_text,
        "reviewer_text": change_item.reviewer_text,
        "reviewer_notes": change_item.reviewer_notes,
        "sheet_title": sheet.sheet_title,
        "sheet_status": sheet.status,
        "issue_date": sheet.issue_date,
        "revision_entries": sheet.revision_entries,
        "page_image_path": sheet.render_path,
        "crop_image_path": cloud.image_path if cloud else "",
        "nearby_text": cloud.nearby_text if cloud else "",
        "cloud_bbox": cloud.bbox if cloud else None,
        "previous_verifications": verifications,
    }


def create_verification_record(change_item_id: str, provider: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> VerificationRecord:
    return VerificationRecord(
        id=stable_id(change_item_id, provider, datetime.now(timezone.utc).isoformat()),
        change_item_id=change_item_id,
        provider=provider,
        created_at=datetime.now(timezone.utc).isoformat(),
        request_payload=request_payload,
        response_payload=response_payload,
    )
