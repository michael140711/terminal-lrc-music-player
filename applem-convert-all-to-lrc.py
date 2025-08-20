#!/usr/bin/env python3
# Interactive batch converter for Apple Music TTML/JSON → LRC
# - Lists all JSON/XML/TTML files in ./lyrics
# - Lets you toggle which ones to convert (ON/OFF)
# - Settings: Main-only | Both | Full, saved in applem-convert.cfg
# - Uses the converter functions from applem-convert-ttml-to-lrc.py.py

from __future__ import annotations

import json
import sys
import runpy
from pathlib import Path
import os

# ANSI colors (basic). On modern Windows terminals, ANSI is supported.
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"

ROOT = Path(__file__).resolve().parent
LYRICS_DIR = ROOT / "lyrics"
SONGS_DIR = ROOT / "lyrics"
CFG_PATH = ROOT / "applem-convert.cfg"

# Load converter functions from script with a non-importable filename
CONVERTER_PATH = ROOT / "applem-convert-ttml-to-lrc.py.py"
mod = runpy.run_path(str(CONVERTER_PATH))
convert_ttml_to_elrc = mod["convert_ttml_to_elrc"]
coerce_to_ttml_input = mod["coerce_to_ttml_input"]


def load_cfg() -> dict:
	if CFG_PATH.exists():
		try:
			return json.loads(CFG_PATH.read_text(encoding="utf-8"))
		except Exception:
			pass
	# default: Only Full Lyrics
	return {"mode": "full"}  # one of: main, both, full


def save_cfg(cfg: dict) -> None:
	CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def cycle_mode(mode: str) -> str:
	order = ["main", "both", "full"]
	try:
		i = order.index(mode)
	except ValueError:
		i = 2  # default to "full"
	return order[(i + 1) % len(order)]


def mode_label(mode: str) -> str:
	if mode == "main":
		return "Main Lyrics Only"
	if mode == "both":
		return "Both Lyrics Mode (2 files)"
	return "Only Full Lyrics"


def gather_lyrics_files() -> list[Path]:
	patterns = ["*.json", "*.xml", "*.ttml"]
	files: list[Path] = []
	for pat in patterns:
		files.extend(sorted(LYRICS_DIR.glob(pat)))
	return files


def get_display_type(p: Path) -> int | None:
	try:
		_, dt = coerce_to_ttml_input(p)
		return dt
	except Exception:
		return None


def clear_console() -> None:
	"""Clear console on Windows and other platforms."""
	try:
		if os.name == "nt":
			os.system("cls")
		else:
			# ANSI clear screen and move cursor home
			print("\033[2J\033[H", end="")
	except Exception:
		# Fallback: print several newlines
		print("\n" * 100)


def print_main_menu(files: list[Path], on_mask: list[bool], display_types: list[int | None], cfg: dict) -> None:
	print()
	print(f"{CYAN}Apple Music → LRC batch converter{RESET}")
	print(f"Lyrics folder: {LYRICS_DIR}")
	print(f"Output folder: {SONGS_DIR}")
	print(f"Mode: {YELLOW}{mode_label(cfg.get('mode', 'full'))}{RESET}")
	print()
	for idx, (p, on, dt) in enumerate(zip(files, on_mask, display_types), start=1):
		status = f"{GREEN}ON{RESET}" if on else f"{YELLOW}OFF{RESET}"
		extra = ""
		if dt is None:
			extra = f" {RED}(displayType=?){RESET}"
		elif dt != 3:
			extra = f" {RED}(displayType={dt}){RESET}"
		print(f"{idx}. {p.name} : {status}{extra}")
	print()
	print("0: Run")
	print("S: Settings")


def run_settings(cfg: dict) -> None:
	while True:
		clear_console()
		print(f"{CYAN}Settings{RESET}")
		print(f"1. {mode_label(cfg.get('mode', 'full'))}")
		print("0. back")
		choice = input("> ").strip()
		if choice == "0":
			return
		if choice == "1":
			cfg["mode"] = cycle_mode(cfg.get("mode", "full"))
			save_cfg(cfg)
		else:
			print("Unknown option. Use 1 to toggle mode, or 0 to go back.")


def ensure_dirs() -> None:
	if not LYRICS_DIR.exists():
		raise SystemExit(f"Lyrics folder not found: {LYRICS_DIR}")
	SONGS_DIR.mkdir(parents=True, exist_ok=True)


def output_names_for(p: Path, mode: str) -> list[tuple[Path, bool]]:
	"""Return a list of (output_path, main_only_flag)."""
	stem = p.stem
	if mode == "main":
		return [(SONGS_DIR / f"{stem} (main).lrc", True)]
	if mode == "both":
		return [
			(SONGS_DIR / f"{stem} (main).lrc", True),
			(SONGS_DIR / f"{stem}.lrc", False),
		]
	# full
	return [(SONGS_DIR / f"{stem}.lrc", False)]


def convert_selected(files: list[Path], on_mask: list[bool], mode: str) -> None:
	total = 0
	ok = 0
	for p, on in zip(files, on_mask):
		if not on:
			continue
		for out_path, main_only in output_names_for(p, mode):
			total += 1
			try:
				convert_ttml_to_elrc(p, out_path, main_only=main_only)
				print(f"Wrote {out_path}")
				ok += 1
			except Exception as e:
				print(f"{RED}Failed to convert {p.name} → {out_path.name}: {e}{RESET}")
	print()
	print(f"Done: {ok}/{total} successful.")


def main() -> None:
	ensure_dirs()
	cfg = load_cfg()
	files = gather_lyrics_files()
	if not files:
		print(f"No JSON/XML/TTML files found in {LYRICS_DIR}")
		return
	display_types = [get_display_type(p) for p in files]
	on_mask = [True for _ in files]

	while True:
		clear_console()
		print_main_menu(files, on_mask, display_types, cfg)
		choice = input("> ").strip()
		if choice.lower() == "s":
			run_settings(cfg)
			continue
		if choice == "0":
			# Run conversions
			clear_console()
			convert_selected(files, on_mask, cfg.get("mode", "full"))
			break
		# number? toggle OFF/ON
		try:
			idx = int(choice)
			if 1 <= idx <= len(files):
				on_mask[idx - 1] = not on_mask[idx - 1]
			else:
				print("Number out of range.")
		except ValueError:
			print("Enter a number to toggle, 0 to run, or S for settings.")


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print("\nExiting.")

