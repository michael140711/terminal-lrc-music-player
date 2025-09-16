"""
Syllables Lyrics Maker
----------------------

Split lyrics into syllables using a hyphenation-based approach with custom overrides for rap/hip-hop lyrics.

Defaults:
- Language: en_US (Pyphen patterns)
- Separator: backtick (`) to avoid conflicts with common punctuation in lyrics
- Custom mappings: custom-syllables.json in the same directory

Usage examples:
- Read from stdin and print to stdout:
    py elrc-generation-tools/syllables-lyrics-maker.py < lyrics/your_lyrics.txt

- Provide text directly:
    py elrc-generation-tools/syllables-lyrics-maker.py --text "All the good girls go to hell"

- Read from file and write to file:
    py elrc-generation-tools/syllables-lyrics-maker.py --in lyrics/input.txt --out temp/output.txt

- Use a different custom mappings file:
    py elrc-generation-tools/syllables-lyrics-maker.py --custom my-custom.json --text "Yeah imma finna drop this"

Custom Syllable Mappings:
- The script automatically looks for custom-syllables.json in the same directory
- Edit this JSON file to add your own word-to-syllable mappings
- Custom mappings override the pyphen dictionary for better rap/hip-hop syllabification
- Words are matched case-insensitively (e.g., "YEAH" matches "yeah" in the file)
- Use the same separator (`) as specified by --sep

Notes:
- For most English lyrics, Pyphen works well. For unknown words/slang, it may leave the word unsplit.
- You can change the separator with --sep (e.g., --sep "·" or --sep "‧").
- Custom mappings are perfect for rap contractions like "imma", "finna", "gonna", etc.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Dict, Iterable

try:
    import pyphen  # type: ignore
except Exception as exc:  # pragma: no cover - runtime guidance if dependency missing
    sys.stderr.write(
        "Pyphen is required. Install with: pip install pyphen (or ask the tool to install it)\n"
    )
    raise


def load_custom_mappings(custom_file: str) -> Dict[str, str]:
    """Load custom syllable mappings from JSON file.

    Returns a dictionary where keys are lowercase words and values are their
    syllabified versions. Returns empty dict if file doesn't exist or has errors.
    """
    if not os.path.exists(custom_file):
        return {}

    try:
        with open(custom_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Filter out JSON comments and instructions (keys starting with _)
        # Convert all keys to lowercase for case-insensitive matching
        mappings = {k.lower(): v for k, v in data.items() if not k.startswith('_')}
        return mappings
    except Exception as ex:
        sys.stderr.write(f"Warning: Could not load custom mappings from {custom_file}: {ex}\n")
        return {}


def syllabify_word(word: str, dic: "pyphen.Pyphen", sep: str, custom_mappings: Dict[str, str]) -> str:
    """Return the word split into syllables using `sep`.

    First checks custom_mappings for the word (case-insensitive). If found, uses that.
    Otherwise falls back to pyphen dictionary. Keeps original casing when possible.
    """
    if not word:
        return word
    # Fast path for non-alpha tokens (numbers/mixed): leave unchanged
    if not any(ch.isalpha() for ch in word):
        return word

    # Check custom mappings first (case-insensitive)
    word_lower = word.lower()
    if word_lower in custom_mappings:
        custom_result = custom_mappings[word_lower]
        # Try to preserve original casing if the custom mapping uses the same separator
        if sep in custom_result:
            # Split both the original word and custom mapping, then try to match casing
            original_parts = word.split() if ' ' in word else [word]  # fallback for complex cases
            custom_parts = custom_result.split(sep)

            # Simple case preservation: if lengths match, copy case from original
            if len(original_parts) == 1 and len(custom_parts) > 1:
                # Apply casing from the original word to each syllable part
                result_parts = []
                char_idx = 0
                for part in custom_parts:
                    if char_idx < len(word):
                        # Copy case character by character
                        new_part = ""
                        for char in part:
                            if char_idx < len(word) and char.isalpha():
                                if word[char_idx].isupper():
                                    new_part += char.upper()
                                else:
                                    new_part += char.lower()
                                char_idx += 1
                            else:
                                new_part += char
                        result_parts.append(new_part)
                    else:
                        result_parts.append(part)
                return sep.join(result_parts)
        return custom_result

    # Fall back to pyphen
    return dic.inserted(word, hyphen=sep)


def syllabify_text(text: str, lang: str = "en_US", sep: str = "`", custom_file: str = None) -> str:
    """Syllabify all words in the given text while preserving whitespace and punctuation.

    Strategy:
    - Load custom mappings if custom_file is provided
    - Walk the text char-by-char, buffering alphabetic runs (including apostrophes) as words.
    - On boundaries, flush word via custom mappings first, then Pyphen; copy all other characters unchanged.
    """
    # Load custom mappings
    custom_mappings = {}
    if custom_file:
        custom_mappings = load_custom_mappings(custom_file)

    dic = pyphen.Pyphen(lang=lang)

    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            word = "".join(buf)
            out.append(syllabify_word(word, dic, sep, custom_mappings))
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
    p.add_argument("--custom", help="Custom syllable mappings JSON file (default: custom-syllables.json in same directory)")

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

    # Determine custom mappings file
    custom_file = args.custom
    if custom_file is None:
        # Default to custom-syllables.json in the same directory as this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        custom_file = os.path.join(script_dir, "custom-syllables.json")

    try:
        result = syllabify_text(src, lang=args.lang, sep=args.sep, custom_file=custom_file)
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
