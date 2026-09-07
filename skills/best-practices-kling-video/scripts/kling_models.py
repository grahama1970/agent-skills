"""Typed boundary models for Kling video requests (fal.ai lanes).

Every request compiled for or submitted to Kling MUST pass KlingRequestPacket
validation first. Failures are pydantic errors() data, never prose.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MULTI_PROMPT_MAX = 512
SINGLE_PROMPT_MAX = 800

REFERENCE_MODELS = {
    "fal-ai/kling-video/o3/standard/reference-to-video",
    "fal-ai/kling-video/o3/pro/reference-to-video",
}
I2V_MODELS = {
    "fal-ai/kling-video/v3/standard/image-to-video",
    "fal-ai/kling-video/v3/pro/image-to-video",
}
T2V_MODELS = {
    "fal-ai/kling-video/v3/standard/text-to-video",
    "fal-ai/kling-video/v3/pro/text-to-video",
}
KNOWN_MODELS = REFERENCE_MODELS | I2V_MODELS | T2V_MODELS


def _public_url(u: str) -> bool:
    return u.startswith("https://") and "localhost" not in u and "127.0.0.1" not in u


class KlingElement(BaseModel, extra="forbid"):
    frontal_image_url: str | None = None
    reference_image_urls: list[str] | None = None
    video_url: str | None = None

    @model_validator(mode="after")
    def _complete(self) -> "KlingElement":
        if self.video_url:
            return self
        # ponytail: fal 422s on frontal without reference_image_urls; both required
        if not (self.frontal_image_url and self.reference_image_urls):
            raise ValueError(
                "element needs BOTH frontal_image_url and non-empty "
                "reference_image_urls (frontal may repeat), or video_url"
            )
        for u in [self.frontal_image_url, *self.reference_image_urls]:
            if not _public_url(u):
                raise ValueError(f"not a public https URL: {u}")
        return self


class MultiPromptEntry(BaseModel, extra="forbid"):
    prompt: str = Field(max_length=MULTI_PROMPT_MAX)
    duration: str = "5"


class KlingRequest(BaseModel, extra="forbid"):
    prompt: str | None = None
    multi_prompt: list[MultiPromptEntry] | None = None
    elements: list[KlingElement] | None = None
    image_urls: list[str] | None = None
    start_image_url: str | None = None
    end_image_url: str | None = None
    duration: str = "5"
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    generate_audio: bool = False
    negative_prompt: str | None = None
    shot_type: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> "KlingRequest":
        if bool(self.prompt) == bool(self.multi_prompt):
            raise ValueError("exactly one of prompt or multi_prompt required")
        if self.multi_prompt and self.end_image_url:
            raise ValueError("multi_prompt and end_image_url are mutually exclusive")
        if self.prompt and len(self.prompt) > SINGLE_PROMPT_MAX:
            raise ValueError(
                f"prompt {len(self.prompt)} chars > {SINGLE_PROMPT_MAX}; "
                "condense — Kling drops constraints silently on long prompts"
            )
        if self.elements:
            text = self.prompt or " ".join(e.prompt for e in self.multi_prompt or [])
            bound = set(re.findall(r"@Element(\d+)", text))
            expected = {str(i + 1) for i in range(len(self.elements))}
            if not expected <= bound:
                raise ValueError(
                    f"unbound elements: @Element{sorted(expected - bound)} "
                    "not referenced in prompt; unbound elements degrade to style hints"
                )
        for u in self.image_urls or []:
            if not _public_url(u):
                raise ValueError(f"image_urls entry not public https: {u}")
        return self


class KlingRequestPacket(BaseModel, extra="forbid"):
    schema_: str = Field(alias="schema", default="kling_video.request.v1")
    model_id: str
    request: KlingRequest
    seam_validation: dict | None = None

    @model_validator(mode="after")
    def _endpoint(self) -> "KlingRequestPacket":
        if self.model_id not in KNOWN_MODELS:
            raise ValueError(f"unknown model_id {self.model_id}; known: {sorted(KNOWN_MODELS)}")
        r = self.request
        if self.model_id in T2V_MODELS and (r.elements or r.image_urls or r.start_image_url):
            raise ValueError(
                "text-to-video accepts NO image inputs — references would be "
                "silently ignored; use o3 reference-to-video or v3 image-to-video"
            )
        if self.model_id in T2V_MODELS and not (r.elements or r.start_image_url):
            # character work heuristic: warn hard via error when elements absent is fine
            pass
        if self.model_id in REFERENCE_MODELS and not (r.elements or r.image_urls or r.start_image_url):
            raise ValueError("reference-to-video with no references; use text-to-video or add elements")
        if self.model_id in I2V_MODELS and not r.start_image_url:
            raise ValueError("image-to-video requires start_image_url")
        return self
