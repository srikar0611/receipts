"""Optional GPT-powered review tour with a deterministic offline fallback."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from importlib import resources
from typing import Any


SAMPLE_LABEL = "sample output (generated with GPT-5.6)"


def sample_tour() -> str:
    return resources.files("receipts").joinpath("demo_data", "sample_tour.md").read_text(encoding="utf-8")


def _response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    texts: list[str] = []
    for item in payload.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    return "\n".join(texts)


def request_tour(manifest: dict[str, Any], api_key: str) -> str:
    prompt = """You are a senior code reviewer. Produce a concise, risk-ranked review tour from this Receipts manifest. Do not claim evidence absent from the manifest. Include: (1) what to inspect first, (2) why it is risky, (3) exact files and session evidence, and (4) a reviewer question.\n\nManifest:\n""" + json.dumps(manifest, indent=2)
    body = json.dumps({"model": "gpt-5.6", "input": prompt, "store": False}).encode("utf-8")
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=body, method="POST", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        text = _response_text(json.loads(response.read().decode("utf-8")))
    if not text:
        raise RuntimeError("OpenAI response contained no output text")
    return text


def get_tour(manifest: dict[str, Any]) -> tuple[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return SAMPLE_LABEL, sample_tour()
    try:
        return "live output (GPT-5.6)", request_tour(manifest, api_key)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError, json.JSONDecodeError) as error:
        return f"{SAMPLE_LABEL}; live request unavailable: {error}", sample_tour()
