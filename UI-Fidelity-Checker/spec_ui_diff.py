"""Spec-to-UI Diff agent (CLI).

Prefer the web UI for demos:  python app.py

CLI usage:
    python spec_ui_diff.py --figma-url "<figma frame link>" --screenshot build.png

Environment:
    FIGMA_TOKEN        Figma personal access token (file-content read scope)
    ANTHROPIC_API_KEY  Anthropic API key
"""

from __future__ import annotations

import argparse
import os
import sys

from core import DiffError, diff, media_type_for

_C = {
    "red": "\033[91m",
    "yellow": "\033[93m",
    "green": "\033[92m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}
_SEV_COLOR = {"high": "red", "medium": "yellow", "low": "dim"}


def _c(text: str, color: str) -> str:
    return f"{_C[color]}{text}{_C['reset']}"


def print_report(result: dict) -> None:
    mismatches = result["mismatches"]
    matches = result["matches"]

    print()
    print(_c(f"  Spec-to-UI Diff — {result['frame_name'] or 'frame'}", "bold"))
    print(_c("  " + "-" * 52, "dim"))

    if not mismatches:
        print(_c("  No mismatches found — build matches the design.", "green"))
    else:
        print(_c(f"  MISMATCHES ({len(mismatches)})", "bold"))
        for m in mismatches:
            sev = m.get("severity", "low")
            tag = _c(f"[{sev.upper()}]", _SEV_COLOR.get(sev, "dim"))
            print(f"  {tag} {_c(m['element'], 'bold')} — {m['property']}")
            print(f"        design: {m['design_value']}   build: {m['build_value']}")
            print(_c(f"        fix: {m['fix_hint']}", "dim"))

    if matches:
        print()
        print(_c(f"  MATCHES ({len(matches)})  OK", "green"))
        for mt in matches[:15]:
            print(_c(f"    + {mt['element']} — {mt['property']}", "green"))
        if len(matches) > 15:
            print(_c(f"    ... and {len(matches) - 15} more", "dim"))

    u = result["usage"]
    print()
    print(
        _c(
            f"  tokens: in={u['input_tokens']} out={u['output_tokens']} "
            f"cache_read={u['cache_read_input_tokens']}",
            "dim",
        )
    )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diff a Figma design against a screenshot of the build."
    )
    parser.add_argument("--figma-url", required=True, help="Figma frame link.")
    parser.add_argument("--screenshot", required=True, help="PNG/JPG screenshot.")
    args = parser.parse_args()

    if not os.path.isfile(args.screenshot):
        print(f"ERROR: screenshot not found: {args.screenshot}", file=sys.stderr)
        sys.exit(2)

    try:
        with open(args.screenshot, "rb") as f:
            image_bytes = f.read()
        media_type = media_type_for(args.screenshot)
        print("Fetching Figma spec and comparing with claude-opus-4-7 ...")
        result = diff(args.figma_url, image_bytes, media_type)
    except (DiffError, RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  ({result['element_count']} design elements extracted)")
    print_report(result)


if __name__ == "__main__":
    main()
