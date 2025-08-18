#!/usr/bin/env python3
r"""
Update in place (creates .bak backup alongside the file):
python "c:\Users\michael\OneDrive - gostepmobile.com\script-lrc\update-lrc-offset.py" "c:\Users\michael\OneDrive - gostepmobile.com\script-lrc\songs\sample.lrc" --in-place
python "update-lrc-offset.py" "songs\benny blanco _ Halsey _ Khalid - Eastside.lrc" --in-place

Print adjusted LRC to console:
python "c:\Users\michael\OneDrive - gostepmobile.com\script-lrc\update-lrc-offset.py" "c:\Users\michael\OneDrive - gostepmobile.com\script-lrc\songs\sample.lrc"

Write to a new file:
python "c:\Users\michael\OneDrive - gostepmobile.com\script-lrc\update-lrc-offset.py" "c:\Users\michael\OneDrive - gostepmobile.com\script-lrc\songs\sample.lrc" -o "c:\Users\michael\Downloads\sample.adjusted.lrc"

Apply the [offset] value in an Enhanced LRC file to all timestamps and reset the offset to zero.

Features:
- Adjusts both line timestamps like [mm:ss.xx] and word-level tags like <mm:ss.xx>.
- Preserves each tag's fractional precision (e.g., .82 stays 2 decimals).
- Leaves header tags such as [length:..] unchanged; only pure time tags are modified.
- Interprets [offset:] as seconds if it contains a decimal point or has small magnitude; otherwise as milliseconds.
- CLI supports in-place editing or writing to a new output file.

Usage:
  python update-lrc-offset.py INPUT.lrc --in-place
  python update-lrc-offset.py INPUT.lrc -o OUTPUT.lrc
  python update-lrc-offset.py INPUT.lrc --units seconds  # force interpret offset as seconds

Notes:
- Negative offsets are supported; timestamps are clamped at 00:00.00 if they would go below zero.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Match, Optional


OFFSET_LINE_RE = re.compile(r"^\[offset:(?P<val>[-+]?\d+(?:\.\d+)?)\]\s*$", re.IGNORECASE)

# Matches both [mm:ss(.fff)] and <mm:ss(.fff)> but NOT things like [length:..] because
# it requires the first char after '[' to be a digit.
TIME_TAG_RE = re.compile(
	r"(?P<open>[\[<])(?P<m>\d{1,3}):(?P<s>\d{2})(?:\.(?P<frac>\d{1,4}))?(?P<close>[\]>])"
)


def parse_offset_seconds(raw: str, units: str = "auto") -> float:
	"""Parse offset string to seconds.

	If units == 'seconds', treat as seconds.
	If units == 'milliseconds', treat as milliseconds.
	If units == 'auto':
		- If a decimal point is present, treat as seconds.
		- Else, if magnitude > 100, treat as milliseconds; otherwise seconds.
	"""
	try:
		val = float(raw)
	except ValueError:
		raise ValueError(f"Invalid offset value: {raw}")

	if units == "seconds":
		return val
	if units == "milliseconds":
		return val / 1000.0

	# auto
	if "." in raw:
		return val
	# Heuristic: large integers are likely milliseconds
	if abs(val) > 100:
		return val / 1000.0
	return val


def apply_offset_to_tag(m: Match[str], offset_seconds: float) -> str:
	open_br = m.group("open")
	close_br = m.group("close")
	# sanity: make sure we don't mismatch brackets (not expected in valid LRC)
	if (open_br == "[" and close_br != "]") or (open_br == "<" and close_br != ">"):
		return m.group(0)

	mm = int(m.group("m"))
	ss = int(m.group("s"))
	frac_str = m.group("frac") or ""
	precision = len(frac_str)
	base = 10 ** precision if precision > 0 else 1

	# total units in this tag's precision
	frac_units = int(frac_str) if precision > 0 else 0
	total_units = ((mm * 60) + ss) * base + frac_units

	# convert offset seconds to this tag's unit resolution
	offset_units = int(round(offset_seconds * base))
	new_units = total_units + offset_units
	if new_units < 0:
		new_units = 0

	# back to mm:ss.frac
	new_total_seconds, new_frac_units = divmod(new_units, base)
	new_mm, new_ss = divmod(new_total_seconds, 60)

	# format fraction preserving precision
	if precision > 0:
		frac_fmt = f"{{:0{precision}d}}"
		frac_part = "." + frac_fmt.format(new_frac_units)
	else:
		frac_part = ""

	return f"{open_br}{new_mm:02d}:{new_ss:02d}{frac_part}{close_br}"


def process_lrc(text: str, units: str = "auto") -> str:
	# Find offset line (first occurrence); if multiple, use the first and zero all of them later
	offset_seconds: float = 0.0
	found_offset_line = None  # type: Optional[str]
	lines = text.splitlines()
	for i, line in enumerate(lines):
		m = OFFSET_LINE_RE.match(line)
		if m:
			found_offset_line = line
			offset_seconds = parse_offset_seconds(m.group("val"), units=units)
			break

	if found_offset_line is None or abs(offset_seconds) < 1e-12:
		# No offset, or effectively zero: still normalize any existing [offset:*] to [offset:0]
		def zero_offset_line(line: str) -> str:
			mm = OFFSET_LINE_RE.match(line)
			return "[offset:0]" if mm else line

		return "\n".join(zero_offset_line(line) for line in lines)

	# Apply the offset to all time tags in all lines
	def sub_fn(m: Match[str]) -> str:
		return apply_offset_to_tag(m, offset_seconds)

	new_lines = [TIME_TAG_RE.sub(sub_fn, line) for line in lines]

	# Reset all [offset:*] lines to zero
	for i, line in enumerate(new_lines):
		if OFFSET_LINE_RE.match(line):
			new_lines[i] = "[offset:0]"

	return "\n".join(new_lines)


def main(argv: Optional[list[str]] = None) -> int:
	p = argparse.ArgumentParser(description=__doc__)
	p.add_argument("input", help="Path to input .lrc file")
	p.add_argument("-o", "--output", help="Write result to this path; if omitted with --in-place, overwrites input")
	p.add_argument(
		"--in-place",
		action="store_true",
		help="Modify the input file in place (creates a .bak backup). Ignored if --output is used.",
	)
	p.add_argument(
		"--units",
		choices=["auto", "seconds", "milliseconds"],
		default="auto",
		help="How to interpret the [offset:] value (default: auto)",
	)

	args = p.parse_args(argv)

	in_path = args.input
	if not os.path.isfile(in_path):
		print(f"Input file not found: {in_path}", file=sys.stderr)
		return 2

	with open(in_path, "r", encoding="utf-8") as f:
		text = f.read()

	out_text = process_lrc(text, units=args.units)

	out_path = args.output
	if out_path:
		os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
		with open(out_path, "w", encoding="utf-8", newline="\n") as f:
			f.write(out_text)
		print(f"Wrote: {out_path}")
		return 0

	if args.in_place:
		backup = in_path + ".bak"
		try:
			# Create a simple backup
			with open(backup, "w", encoding="utf-8", newline="\n") as f:
				f.write(text)
			with open(in_path, "w", encoding="utf-8", newline="\n") as f:
				f.write(out_text)
			print(f"Updated in place. Backup saved to: {backup}")
			return 0
		except Exception as e:
			print(f"Failed to write in place: {e}", file=sys.stderr)
			return 1

	# Default: print to stdout
	sys.stdout.write(out_text)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

