"""
Get plain text lyrics from LRC / Enhanced LRC
---------------------------------------------

This script reads an .lrc (classic or enhanced with per-word timing) and writes
plain text lyrics by stripping timestamps/metadata while preserving punctuation
and spacing.

Usage (PowerShell):
  # From a file to stdout
  py elrc-generation-tools/get-lyrics-from-lrc.py --in 'lyrics/Some Song 1-main.lrc'

  # From a file to another file
  py elrc-generation-tools/get-lyrics-from-lrc.py --in 'songs/Some Song 0-enhanced.lrc' --out 'temp/Some Song.txt'

  # From stdin to stdout
  Get-Content 'lyrics/Some Song 1-main.lrc' | py elrc-generation-tools/get-lyrics-from-lrc.py
"""

from __future__ import annotations

import argparse
import io
import subprocess
import re
import sys
from typing import Iterable


# Patterns:
# - LRC time tags like [mm:ss] or [mm:ss.xxx] or [mm:ss.xxxx]
BRACKET_TIME = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,4}))?\]")
# - Enhanced LRC word tags like <mm:ss> or <mm:ss.xxx>
ANGLE_TIME = re.compile(r"<(\d{1,2}):(\d{2})(?:\.(\d{1,4}))?>")
# - Metadata-only lines like [ar:Artist], [ti:Title], [length:02:10.10], etc.
METADATA_LINE = re.compile(r"^\s*\[[A-Za-z][^:\]]*:[^\]]*\]\s*$")


def is_metadata_line(line: str) -> bool:
    return bool(METADATA_LINE.match(line))


def strip_timestamps(line: str) -> str:
    """Remove any [mm:ss(.ms)] and <mm:ss(.ms)> tags from the line.

    Leaves all other characters intact. Does not try to reflow punctuation.
    """
    line = BRACKET_TIME.sub("", line)
    line = ANGLE_TIME.sub("", line)
    return line


def process_lines(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip("\n\r")
        if not line.strip():
            # Preserve paragraph breaks: keep an empty line when present
            out.append("")
            continue
        if is_metadata_line(line):
            # Drop metadata-only lines entirely
            continue
        text = strip_timestamps(line)
        # Normalize spaces around the removed tags
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text)
        else:
            # If a line becomes empty after stripping, skip it
            # (except we already handled explicit blank lines above)
            pass
    return out


def read_clipboard_text() -> str:
    """Read text from clipboard.

    Prefers pyperclip if available; falls back to PowerShell Get-Clipboard on Windows.
    """
    try:
        import pyperclip  # type: ignore

        return pyperclip.paste() or ""
    except Exception:
        pass

    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode == 0:
            return completed.stdout
    except Exception:
        pass

    raise RuntimeError(
        "Unable to read clipboard. Install 'pyperclip' or ensure PowerShell Get-Clipboard works."
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Extract plain text lyrics from LRC/Enhanced LRC.")
    p.add_argument("--in", dest="infile", help="Input LRC file (or omit to read from stdin)")
    p.add_argument("--out", dest="outfile", help="Output text file (otherwise prints to stdout)")
    p.add_argument("--clip", action="store_true", help="Read input from the clipboard")
    args = p.parse_args(argv)

    # Acquire input
    if args.infile:
        with open(args.infile, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    elif args.clip:
        try:
            clip = read_clipboard_text()
        except Exception as ex:
            sys.stderr.write(f"Clipboard read failed: {ex}\n")
            return 2
        lines = clip.splitlines(True)
    else:
        if sys.stdin.isatty():
            sys.stderr.write("No input provided. Use --in <file>, --clip, or pipe text via stdin.\n")
            return 2
        lines = sys.stdin.read().splitlines(True)

    result_lines = process_lines(lines)
    result_text = "\n".join(result_lines) + ("\n" if result_lines else "")

    # Write output
    if args.outfile:
        with open(args.outfile, "w", encoding="utf-8") as f:
            f.write(result_text)
    else:
        # Write to stdout without extra transformations
        sys.stdout.write(result_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
