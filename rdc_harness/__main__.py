"""CLI entry point: run the harness on a saved Layer-1 frame summary JSON.

Usage:
    python -m rdc_harness frame.json [--compact]
    python -m rdc_harness -             # read JSON from stdin

Prints the auto-detected red flags and the full L1 deterministic report.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .rules import detect_red_flags, run_deterministic
from .summarize import compact_frame, estimate_tokens


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m rdc_harness",
        description="Run the deterministic verification layer on a frame summary JSON.",
    )
    parser.add_argument(
        "frame_json",
        help="path to a Layer-1 frame summary JSON, or '-' to read from stdin",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="also print the token-compact frame directory",
    )
    args = parser.parse_args(argv)

    if args.frame_json == "-":
        raw = sys.stdin.read()
    else:
        # utf-8-sig transparently strips a UTF-8 BOM, which many Windows tools
        # prepend when writing JSON.
        with open(args.frame_json, encoding="utf-8-sig") as f:
            raw = f.read()

    frame = json.loads(raw)

    report = run_deterministic(frame)
    print(json.dumps({
        "red_flags": [a.to_dict() for a in detect_red_flags(frame)],
        "l1": report.to_dict(),
    }, indent=2))

    if args.compact:
        print("\n--- compact frame directory ---")
        text = compact_frame(frame)
        print(text)
        print(f"\n[~{estimate_tokens(text)} tokens]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
