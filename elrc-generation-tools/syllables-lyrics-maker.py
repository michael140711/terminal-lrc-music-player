"""
Syllables Lyrics Maker
----------------------

Split lyrics into syllables using a hyphenation-based approach.

Defaults:
- Language: en_US (Pyphen patterns)
- Separator: backtick (`) to avoid conflicts with common punctuation in lyrics

Usage examples:
- Read from stdin and print to stdout:
    py elrc-generation-tools/syllables-lyrics-maker.py < lyrics/your_lyrics.txt

- Provide text directly:
    py elrc-generation-tools/syllables-lyrics-maker.py --text "All the good girls go to hell"

- Read from file and write to file:
    py elrc-generation-tools/syllables-lyrics-maker.py --in lyrics/input.txt --out temp/output.txt

Notes:
- For most English lyrics, Pyphen works well. For unknown words/slang, it may leave the word unsplit.
- You can change the separator with --sep (e.g., --sep "·" or --sep "‧").
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Iterable

try:
    import pyphen  # type: ignore
except Exception as exc:  # pragma: no cover - runtime guidance if dependency missing
    sys.stderr.write(
        "Pyphen is required. Install with: pip install pyphen (or ask the tool to install it)\n"
    )
    raise


def syllabify_word(word: str, dic: "pyphen.Pyphen", sep: str) -> str:
    """Return the word split into syllables using `sep`.

    Keeps original casing. If no split points are known, returns the word unchanged.
    """
    if not word:
        return word
    # Fast path for non-alpha tokens (numbers/mixed): leave unchanged
    if not any(ch.isalpha() for ch in word):
        return word
    return dic.inserted(word, hyphen=sep)


def syllabify_text(text: str, lang: str = "en_US", sep: str = "`") -> str:
    """Syllabify all words in the given text while preserving whitespace and punctuation.

    Strategy:
    - Walk the text char-by-char, buffering alphabetic runs (including apostrophes) as words.
    - On boundaries, flush word via Pyphen; copy all other characters unchanged.
    """
    dic = pyphen.Pyphen(lang=lang)

    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            word = "".join(buf)
            out.append(syllabify_word(word, dic, sep))
            buf.clear()

    apostrophes = {"'", "’"}  # ASCII and Unicode right single quote
    for ch in text:
        if ch.isalpha() or ch in apostrophes:
            buf.append(ch)
        else:
            flush()
            out.append(ch)
    flush()
    return "".join(out)


def iter_stdin_lines() -> Iterable[str]:
    for line in sys.stdin:
        yield line


def read_clipboard_text() -> str:
    """Read text from clipboard.

    Prefers pyperclip if available; falls back to PowerShell Get-Clipboard on Windows.
    """
    # Try pyperclip first if installed
    try:
        import pyperclip  # type: ignore

        return pyperclip.paste() or ""
    except Exception:
        pass

    # Windows PowerShell fallback
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
    p = argparse.ArgumentParser(description="Split lyrics into syllables with a chosen separator.")
    p.add_argument("--lang", default="en_US", help="Language for Pyphen patterns (default: en_US)")
    p.add_argument("--sep", default="`", help="Syllable separator (default: backtick `)")
    p.add_argument("--in", dest="infile", help="Input file (otherwise reads stdin unless --text is given)")
    p.add_argument("--out", dest="outfile", help="Output file (otherwise prints to stdout)")
    p.add_argument("--text", help="Process this text directly (overrides --in/stdin)")
    p.add_argument("--clip", action="store_true", help="Read input from the clipboard")

    args = p.parse_args(argv)

    if args.text is not None:
        src = args.text
    elif args.infile:
        with open(args.infile, "r", encoding="utf-8") as f:
            src = f.read()
    elif args.clip:
        try:
            src = read_clipboard_text()
        except Exception as ex:
            sys.stderr.write(f"Clipboard read failed: {ex}\n")
            return 2
    else:
        # Read everything from stdin
        if sys.stdin.isatty():
            # No stdin piped; provide hint and exit
            sys.stderr.write(
                "No input provided. Use --text, --in <file>, or pipe text via stdin.\n"
            )
            return 2
        src = sys.stdin.read()

    try:
        result = syllabify_text(src, lang=args.lang, sep=args.sep)
    except KeyError as e:
        sys.stderr.write(
            f"Language '{args.lang}' not found in Pyphen patterns. Try en_US or see pyphen docs.\n"
        )
        return 2

    if args.outfile:
        with open(args.outfile, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
