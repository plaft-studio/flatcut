#!/usr/bin/env python3
"""Trim a GitHub release body to what extensions.blender.org accepts.

The platform caps release notes at 1024 characters, which a release body
easily exceeds. Cut at a paragraph break and link out to the full notes.

Reads RELEASE_NOTES, RELEASE_URL and GITHUB_SHA from the environment and
prints the result.
"""

import os
import sys

LIMIT = 1024


def build_notes(raw: str, link: str, sha: str) -> str:
    raw = raw.strip()

    if not raw:
        return f"Manual upload from {sha[:7]}." if sha else "Manual upload."

    if len(raw) <= LIMIT:
        return raw

    suffix = f"\n\nFull release notes: {link}" if link else "\n\n(truncated)"
    head = raw[: LIMIT - len(suffix)]

    # Prefer a paragraph break, but never throw away most of the text
    cut = head.rsplit("\n\n", 1)[0]
    if len(cut) < len(head) // 2:
        cut = head

    return cut.rstrip() + suffix


def main() -> int:
    notes = build_notes(
        os.environ.get("RELEASE_NOTES", ""),
        os.environ.get("RELEASE_URL", ""),
        os.environ.get("GITHUB_SHA", ""),
    )

    if len(notes) > LIMIT:
        print(f"Trimmed notes are still {len(notes)} characters", file=sys.stderr)
        return 1

    print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
