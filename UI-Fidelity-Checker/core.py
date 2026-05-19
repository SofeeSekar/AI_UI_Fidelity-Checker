"""Shared Spec-to-UI diff logic, used by both the CLI and the web app."""

from __future__ import annotations

import base64
import json
import os

import anthropic
from dotenv import load_dotenv

from figma_client import fetch_design_spec, parse_figma_url

# Load FIGMA_TOKEN / ANTHROPIC_API_KEY from a local .env file if present.
# override=True so the project's .env is the single source of truth.
load_dotenv(override=True)

MODEL = "claude-opus-4-7"

MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}

# Stable instruction prefix — cached so repeated runs in a demo are cheap/fast.
SYSTEM_PROMPT = """You are a UI fidelity reviewer. You are given:
1. A structured design spec extracted from Figma (exact colors, font sizes, \
spacing, positions, text).
2. A screenshot of the running build of that same screen.

Your job: find where the build deviates from the design. Be precise and \
actionable, like a senior engineer doing implementation review.

Rules:
- Compare colors, font size/weight/family, spacing/padding, element position \
and ordering, text content, corner radius, and missing or extra elements.
- Estimate build values from the screenshot; design values come from the spec. \
State both.
- Only report a mismatch when you are reasonably confident it is a real \
deviation a developer should fix. Minor sub-pixel antialiasing is not a \
mismatch.
- Severity: "high" = clearly wrong and user-visible (wrong color, missing \
element, wrong text); "medium" = noticeable (spacing/size off enough to see); \
"low" = subtle polish.
- fix_hint: one short sentence telling the developer what to change.
- box: the location of the issue ON THE BUILD SCREENSHOT, as fractions of \
that image: x and y are the top-left corner (0,0 = top-left of the image; \
1,1 = bottom-right), w and h are width and height, all between 0 and 1. Make \
the box tight around the affected element. If unsure, give your best estimate.
- Also list things that correctly match, so the developer has confidence."""

DIFF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mismatches": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "element": {"type": "string"},
                    "property": {"type": "string"},
                    "design_value": {"type": "string"},
                    "build_value": {"type": "string"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "fix_hint": {"type": "string"},
                    "box": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "w": {"type": "number"},
                            "h": {"type": "number"},
                        },
                        "required": ["x", "y", "w", "h"],
                    },
                },
                "required": [
                    "element",
                    "property",
                    "design_value",
                    "build_value",
                    "severity",
                    "fix_hint",
                    "box",
                ],
            },
        },
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "element": {"type": "string"},
                    "property": {"type": "string"},
                },
                "required": ["element", "property"],
            },
        },
    },
    "required": ["mismatches", "matches"],
}

_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


class DiffError(Exception):
    """User-facing error (bad token, bad URL, refusal, etc.)."""


def media_type_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in MEDIA_TYPES:
        raise DiffError(f"Unsupported screenshot type '.{ext}'. Use png/jpg/webp/gif.")
    return MEDIA_TYPES[ext]


SYSTEM_PROMPT_IMAGES = """You are a UI fidelity reviewer. You are given two \
images of the SAME screen:
1. The intended design (exported/screenshotted from Figma).
2. A screenshot of the running build.

Your job: find where the build deviates from the design. Be precise and \
actionable, like a senior engineer doing implementation review.

Rules:
- Compare colors, font size/weight, spacing/padding, element position and \
ordering, alignment, text content, corner radius, and missing or extra \
elements.
- Both values are estimated from the images; describe them concretely \
(approx hex, "~8px tighter", "left-aligned vs centered", etc.).
- Only report a mismatch when you are reasonably confident it is a real \
deviation a developer should fix. Ignore differences caused only by the two \
images being at different zoom/scale or cropped differently.
- Severity: "high" = clearly wrong and user-visible (wrong color, missing \
element, wrong text); "medium" = noticeable; "low" = subtle polish.
- fix_hint: one short sentence telling the developer what to change.
- box: the location of the issue ON IMAGE 2 (the build screenshot), as \
fractions of that image: x,y = top-left corner (0,0 = top-left, 1,1 = \
bottom-right), w,h = width and height, all between 0 and 1. Keep the box tight \
around the affected element. If unsure, give your best estimate.
- Also list things that correctly match, so the developer has confidence."""


# --- neutral content parts (engine-agnostic) ------------------------------

def _txt(text: str) -> dict:
    return {"kind": "text", "text": text}


def _img(image_bytes: bytes, media_type: str) -> dict:
    return {"kind": "image", "data": image_bytes, "mime": media_type}


def _shape(raw: dict) -> dict:
    result = {"mismatches": raw.get("mismatches", []), "matches": raw.get("matches", [])}
    result["mismatches"].sort(key=lambda m: _SEV_ORDER.get(m.get("severity"), 3))
    return result


# --- Anthropic backend ----------------------------------------------------

def _run_anthropic(system_prompt: str, parts: list[dict]) -> dict:
    content = []
    for p in parts:
        if p["kind"] == "text":
            content.append({"type": "text", "text": p["text"]})
        else:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": p["mime"],
                    "data": base64.standard_b64encode(p["data"]).decode("utf-8"),
                },
            })

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": DIFF_SCHEMA},
        },
        system=[
            {"type": "text", "text": system_prompt,
             "cache_control": {"type": "ephemeral"}}
        ],
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise DiffError("The model refused to produce a diff for this input.")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise DiffError("No structured output returned by the model.")

    out = _shape(json.loads(text))
    u = response.usage
    out["usage"] = {
        "engine": f"anthropic/{MODEL}",
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0),
    }
    return out


# --- Google Gemini backend (free tier) ------------------------------------

import time

# Tried in order; a 503/429 on one falls through to the next. Override the
# first choice with GEMINI_MODEL in .env if you want.
_GEMINI_MODELS = [
    m for m in (
        os.environ.get("GEMINI_MODEL"),
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
    ) if m
]
_GEMINI_RETRYABLE = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded")

_GEMINI_JSON_HINT = (
    "\n\nReturn ONLY a JSON object, no markdown, with exactly this shape "
    "(box = location on the BUILD screenshot as fractions 0..1):\n"
    '{"mismatches":[{"element":str,"property":str,"design_value":str,'
    '"build_value":str,"severity":"high"|"medium"|"low","fix_hint":str,'
    '"box":{"x":number,"y":number,"w":number,"h":number}}],'
    '"matches":[{"element":str,"property":str}]}'
)


def _run_gemini(system_prompt: str, parts: list[dict]) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    contents = []
    for p in parts:
        if p["kind"] == "text":
            contents.append(types.Part.from_text(text=p["text"]))
        else:
            contents.append(
                types.Part.from_bytes(data=p["data"], mime_type=p["mime"])
            )

    cfg = types.GenerateContentConfig(
        system_instruction=system_prompt + _GEMINI_JSON_HINT,
        response_mime_type="application/json",
        temperature=0,
    )

    last_err = None
    for model in _GEMINI_MODELS:
        for attempt in range(3):  # retry transient overloads on this model
            try:
                response = client.models.generate_content(
                    model=model, contents=contents, config=cfg
                )
                text = response.text
                if not text:
                    raise DiffError("Gemini returned no content (possibly blocked).")
                out = _shape(json.loads(text))
                um = getattr(response, "usage_metadata", None)
                out["usage"] = {
                    "engine": f"google/{model} (free)",
                    "input_tokens": getattr(um, "prompt_token_count", 0) if um else 0,
                    "output_tokens": getattr(um, "candidates_token_count", 0) if um else 0,
                    "cache_read_input_tokens": 0,
                }
                return out
            except DiffError:
                raise
            except Exception as e:
                last_err = e
                if any(tok in str(e) for tok in _GEMINI_RETRYABLE):
                    time.sleep(1.5 * (attempt + 1))
                    continue  # retry, then fall to next model
                raise DiffError(f"Gemini request failed: {e}") from e

    raise DiffError(
        "All free Gemini models are overloaded right now (503). This is "
        f"temporary on Google's side — try again in a minute. Last error: {last_err}"
    )


# --- dispatcher -----------------------------------------------------------

def _run(system_prompt: str, parts: list[dict]) -> dict:
    """Use Gemini if GEMINI_API_KEY is set (free), else Anthropic."""
    if os.environ.get("GEMINI_API_KEY"):
        return _run_gemini(system_prompt, parts)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _run_anthropic(system_prompt, parts)
    raise DiffError(
        "No model key found. Set GEMINI_API_KEY (free) or ANTHROPIC_API_KEY "
        "in your .env file."
    )


def _scope_part(focus: str | None) -> dict | None:
    """A strong user-turn instruction to compare only one section."""
    if not focus or focus.strip().lower() in ("", "whole screen", "all"):
        return None
    f = focus.strip()
    return _txt(
        f"SCOPE — IMPORTANT: Only evaluate the **{f}** area of the screen. "
        f"Completely ignore every other part of the UI. Do NOT report any "
        f"mismatch or match outside the {f}. Every box you return must fall "
        f"inside the {f} region of the build screenshot."
    )


def diff(
    figma_url: str,
    image_bytes: bytes,
    media_type: str,
    focus: str | None = None,
) -> dict:
    """Figma-API mode: pull the spec via the API, diff against a screenshot."""
    figma_token = os.environ.get("FIGMA_TOKEN")
    if not figma_token:
        raise DiffError("FIGMA_TOKEN environment variable is not set.")

    file_key, node_id = parse_figma_url(figma_url)
    spec = fetch_design_spec(file_key, node_id, figma_token)

    parts = [
        _txt("DESIGN SPEC (from Figma):\n" + json.dumps(spec, indent=1)),
        _img(image_bytes, media_type),
        _txt("The image above is a screenshot of the running build. "
             "Diff it against the design spec."),
    ]
    scope = _scope_part(focus)
    if scope:
        parts.append(scope)

    result = _run(SYSTEM_PROMPT, parts)
    result["frame_name"] = spec.get("frame_name")
    result["element_count"] = len(spec["elements"])
    result["focus"] = focus or "Whole screen"
    return result


def diff_images(
    design_bytes: bytes,
    design_media_type: str,
    build_bytes: bytes,
    build_media_type: str,
    focus: str | None = None,
) -> dict:
    """No-API mode: compare a design image directly against a build screenshot."""
    parts = [
        _txt("IMAGE 1 — the intended design (Figma):"),
        _img(design_bytes, design_media_type),
        _txt("IMAGE 2 — the running build:"),
        _img(build_bytes, build_media_type),
        _txt("Diff image 2 (build) against image 1 (design)."),
    ]
    scope = _scope_part(focus)
    if scope:
        parts.append(scope)

    result = _run(SYSTEM_PROMPT_IMAGES, parts)
    result["frame_name"] = "Design vs Build (image comparison)"
    result["element_count"] = None
    result["focus"] = focus or "Whole screen"
    return result


# --- dynamic section detection -------------------------------------------

_SECTIONS_SYS = (
    "You are a UI reviewer. Look at this product screen and list the distinct "
    "major visual sections a reviewer would compare separately (e.g. header "
    "bar, KPI summary cards, a specific chart, a sidebar, a button group). "
    "Use short human labels of 2-5 words. Give between 4 and 12 sections, "
    "ordered top-to-bottom / left-to-right. Be specific to THIS screen."
)
_SECTIONS_HINT = '\n\nReturn ONLY JSON, no markdown: {"sections":["...","..."]}'


def _clean_sections(raw: list) -> list[str]:
    seen, out = set(), []
    for s in raw or []:
        s = str(s).strip()
        k = s.lower()
        if s and k not in seen:
            seen.add(k)
            out.append(s)
    return out[:12]


def detect_sections(image_bytes: bytes, media_type: str) -> list[str]:
    """One cheap model call: list the major UI sections in a design image."""
    if os.environ.get("GEMINI_API_KEY"):
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        cfg = types.GenerateContentConfig(
            system_instruction=_SECTIONS_SYS + _SECTIONS_HINT,
            response_mime_type="application/json",
            temperature=0,
        )
        contents = [types.Part.from_bytes(data=image_bytes, mime_type=media_type)]
        last = None
        for model in _GEMINI_MODELS:
            try:
                r = client.models.generate_content(
                    model=model, contents=contents, config=cfg
                )
                return _clean_sections(json.loads(r.text).get("sections", []))
            except Exception as e:  # noqa: BLE001
                last = e
                if any(t in str(e) for t in _GEMINI_RETRYABLE):
                    continue
                break
        raise DiffError(f"Section detection failed: {last}")

    if os.environ.get("ANTHROPIC_API_KEY"):
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "sections": {
                                "type": "array",
                                "items": {"type": "string"},
                            }
                        },
                        "required": ["sections"],
                    },
                }
            },
            system=_SECTIONS_SYS,
            messages=[{
                "role": "user",
                "content": [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(image_bytes).decode(),
                    },
                }],
            }],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        return _clean_sections(json.loads(text).get("sections", []))

    raise DiffError("No model key found for section detection.")
