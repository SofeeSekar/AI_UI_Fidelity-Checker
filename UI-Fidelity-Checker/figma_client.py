"""Pull a Figma frame via the REST API and flatten it into a compact design spec.

Only reads design data (X-Figma-Token, read scope). The token is taken from the
FIGMA_TOKEN environment variable and never written anywhere.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs

import requests

FIGMA_API = "https://api.figma.com/v1"


_FILE_KEY_RE = re.compile(r"/(?:file|design|proto)/([A-Za-z0-9]+)")


def _resolve_short_link(url: str) -> str:
    """Follow redirects so figmashort.link / figma.com/s/... links expand
    to the canonical /design/<key>?node-id=... URL."""
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (figma-spec-diff)"},
        )
        return resp.url or url
    except requests.RequestException:
        return url


def parse_figma_url(url: str) -> tuple[str, str | None]:
    """Extract (file_key, node_id) from a Figma file/design URL.

    Handles /file/<key>/ and /design/<key>/ forms, the
    ?node-id=45-678 / 45%3A678 query param, and short links
    (figmashort.link, figma.com/s/...) by following redirects.
    """
    m = _FILE_KEY_RE.search(urlparse(url).path)
    if not m:
        # Likely a short link — resolve it and try again.
        url = _resolve_short_link(url)
        m = _FILE_KEY_RE.search(urlparse(url).path)
    if not m:
        raise ValueError(
            "Could not find a Figma file key in that URL. Open the file in "
            "Figma and copy the address-bar URL (it contains /design/<key>), "
            f"or use Share > Copy link. Got: {url}"
        )
    file_key = m.group(1)

    qs = parse_qs(urlparse(url).query)
    node_id = None
    if "node-id" in qs:
        raw = unquote(qs["node-id"][0])
        # Figma uses 45-678 in URLs but 45:678 in the API
        node_id = raw.replace("-", ":")
    return file_key, node_id


def _rgba_to_hex(color: dict[str, float]) -> str:
    r = round(color.get("r", 0) * 255)
    g = round(color.get("g", 0) * 255)
    b = round(color.get("b", 0) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def _first_solid_fill(node: dict[str, Any]) -> str | None:
    for fill in node.get("fills", []) or []:
        if fill.get("type") == "SOLID" and fill.get("visible", True):
            return _rgba_to_hex(fill.get("color", {}))
    return None


def _flatten(node: dict[str, Any], out: list[dict[str, Any]], depth: int) -> None:
    if depth > 12:
        return

    box = node.get("absoluteBoundingBox") or {}
    style = node.get("style") or {}

    element: dict[str, Any] = {
        "name": node.get("name"),
        "type": node.get("type"),
    }
    if box:
        element["box"] = {
            "x": round(box.get("x", 0)),
            "y": round(box.get("y", 0)),
            "w": round(box.get("width", 0)),
            "h": round(box.get("height", 0)),
        }

    text = node.get("characters")
    if text:
        element["text"] = text

    fill = _first_solid_fill(node)
    if fill:
        element["color"] = fill

    if style:
        element["typography"] = {
            k: style[k]
            for k in ("fontFamily", "fontWeight", "fontSize", "lineHeightPx", "textAlignHorizontal")
            if k in style
        }

    for pad in ("paddingLeft", "paddingRight", "paddingTop", "paddingBottom", "itemSpacing"):
        if pad in node:
            element.setdefault("layout", {})[pad] = node[pad]

    if "cornerRadius" in node:
        element["cornerRadius"] = node["cornerRadius"]

    # Only keep nodes that carry visual signal worth diffing.
    if text or fill or style or element.get("layout") or node.get("type") in (
        "FRAME",
        "COMPONENT",
        "INSTANCE",
    ):
        out.append(element)

    for child in node.get("children", []) or []:
        _flatten(child, out, depth + 1)


def fetch_design_spec(file_key: str, node_id: str | None, token: str) -> dict[str, Any]:
    """Return {frame_name, elements:[...]} for the given node (or whole file)."""
    headers = {"X-Figma-Token": token}

    if node_id:
        resp = requests.get(
            f"{FIGMA_API}/files/{file_key}/nodes",
            params={"ids": node_id},
            headers=headers,
            timeout=30,
        )
    else:
        resp = requests.get(f"{FIGMA_API}/files/{file_key}", headers=headers, timeout=30)

    if resp.status_code in (401, 403):
        raise RuntimeError(
            "Figma rejected the token (HTTP %d). The FIGMA_TOKEN is invalid, "
            "expired, or lacks 'File content' read scope. Regenerate it at "
            "figma.com > Settings > Security > personal access tokens."
            % resp.status_code
        )
    if resp.status_code == 404:
        raise RuntimeError(
            f"Figma returned 404 for file {file_key}. Figma returns 404 (not "
            "403) when the token's account cannot access a file. Most likely "
            "this file lives in an organization workspace and the account that "
            "created FIGMA_TOKEN is not a member of it. Fix: open this exact "
            "file in figma.com while logged in as the SAME account whose token "
            "you used — if you can't open it there, you need to be invited to "
            "the file/project, or use a token from an account that has access."
        )
    resp.raise_for_status()
    data = resp.json()

    if node_id:
        nodes = data.get("nodes", {})
        if node_id not in nodes or nodes[node_id] is None:
            raise RuntimeError(
                f"Node {node_id} not found in file {file_key}. "
                "Re-copy the link from Figma (right-click frame > Copy link)."
            )
        document = nodes[node_id]["document"]
    else:
        document = data["document"]

    elements: list[dict[str, Any]] = []
    _flatten(document, elements, 0)
    return {"frame_name": document.get("name"), "elements": elements}
