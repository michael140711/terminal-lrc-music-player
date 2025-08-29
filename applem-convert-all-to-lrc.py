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
CONVERTER_PATH = ROOT / "applem-convert-ttml-to-lrc.py"
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
	return {"mode": "full", "disable_non_dt3": False, "filter_duplicates": False, "replace_censored_stars": False}  # one of: main, both, full


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
	run_idx = len(files) + 1
	print(f"{run_idx}. run")
	print("0. settings")


def run_settings(cfg: dict) -> None:
	while True:
		clear_console()
		print(f"{CYAN}Settings{RESET}")
		print(f"1. Toggle - {mode_label(cfg.get('mode', 'full'))}")
		dn3 = cfg.get("disable_non_dt3", False)
		print(f"2. Disable ALL Non (DisplayType=3) when loading: {'ON' if dn3 else 'OFF'}")
		fd = cfg.get("filter_duplicates", False)
		print(f"3. Filter Duplicates when 'Both' mode: {'ON' if fd else 'OFF'} (delete non-main if identical)")
		rcs = cfg.get("replace_censored_stars", False)
		print(f"4. Replace censored stars to 🥷 : {'ON' if rcs else 'OFF'}")
		print("---")
		print("0. Back")
		choice = input("> ").strip()
		if choice == "0":
			return
		if choice == "1":
			cfg["mode"] = cycle_mode(cfg.get("mode", "full"))
			save_cfg(cfg)
		elif choice == "2":
			cfg["disable_non_dt3"] = not cfg.get("disable_non_dt3", False)
			save_cfg(cfg)
		elif choice == "3":
			cfg["filter_duplicates"] = not cfg.get("filter_duplicates", False)
			save_cfg(cfg)
		elif choice == "4":
			cfg["replace_censored_stars"] = not cfg.get("replace_censored_stars", False)
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
		return [(SONGS_DIR / f"{stem} 1-main.lrc", True)]
	if mode == "both":
		return [
			(SONGS_DIR / f"{stem} 1-main.lrc", True),
			(SONGS_DIR / f"{stem} 2-full.lrc", False),
		]
	# full
	return [(SONGS_DIR / f"{stem}.lrc", False)]


def _postprocess_output(path: Path, replace_censored_stars: bool) -> None:
	try:
		if replace_censored_stars and path.exists():
			txt = path.read_text(encoding="utf-8")
			new_txt = txt.replace("****", "🥷 ")
			if new_txt != txt:
				path.write_text(new_txt, encoding="utf-8")
	except Exception as e:
		print(f"{YELLOW}Post-process failed for {path.name}: {e}{RESET}")


def convert_selected(files: list[Path], on_mask: list[bool], mode: str, filter_duplicates: bool = False, replace_censored_stars: bool = False) -> None:
	total = 0
	ok = 0
	for p, on in zip(files, on_mask):
		if not on:
			continue
		# If in 'both' mode and filtering duplicates, handle pair together
		if mode == "both" and filter_duplicates:
			outputs = output_names_for(p, mode)
			results: list[tuple[Path, bool, bool]] = []  # (path, is_main, success)
			for out_path, main_only in outputs:
				total += 1
				try:
					convert_ttml_to_elrc(p, out_path, main_only=main_only)
					# post-processing replacement if enabled
					_postprocess_output(out_path, replace_censored_stars)
					print(f"Wrote {out_path}")
					ok += 1
					results.append((out_path, main_only, True))
				except Exception as e:
					print(f"{RED}Failed to convert {p.name} → {out_path.name}: {e}{RESET}")
					results.append((out_path, main_only, False))

			# If both succeeded, compare contents and delete non-main if identical
			try:
				main_entry = next((r for r in results if r[1] is True), None)
				full_entry = next((r for r in results if r[1] is False), None)
				if main_entry and full_entry and main_entry[2] and full_entry[2]:
					main_path = main_entry[0]
					full_path = full_entry[0]
					if main_path.exists() and full_path.exists():
						if main_path.read_bytes() == full_path.read_bytes():
							# identical; keep main only
							try:
								full_path.unlink()
								print(f"{YELLOW}Duplicate content detected for '{p.name}'. Kept main only; deleted {full_path.name}.{RESET}")
							except Exception as del_err:
								print(f"{RED}Tried to delete duplicate file {full_path.name} but failed: {del_err}{RESET}")
			except Exception as cmp_err:
				print(f"{RED}Comparison failed for '{p.name}': {cmp_err}{RESET}")
		else:
			for out_path, main_only in output_names_for(p, mode):
				total += 1
				try:
					convert_ttml_to_elrc(p, out_path, main_only=main_only)
					# post-processing replacement if enabled
					_postprocess_output(out_path, replace_censored_stars)
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
	# Preset based on setting when loading
	if cfg.get("disable_non_dt3", False):
		for i, dt in enumerate(display_types):
			if dt != 3:
				on_mask[i] = False

	while True:
		clear_console()
		print_main_menu(files, on_mask, display_types, cfg)
		choice = input("> ").strip()
		# 0 -> settings; (len(files)+1) -> run; numbers in [1..len(files)] toggle
		if choice == "0":
			_prev = cfg.get("disable_non_dt3", False)
			run_settings(cfg)
			_new = cfg.get("disable_non_dt3", False)
			if _prev != _new:
				if _new:
					for i, dt in enumerate(display_types):
						if dt != 3:
							on_mask[i] = False
				else:
					for i, dt in enumerate(display_types):
						if dt != 3:
							on_mask[i] = True
			continue
		# number? toggle OFF/ON or run
		try:
			idx = int(choice)
			run_idx = len(files) + 1
			if idx == run_idx:
				# Run conversions
				clear_console()
				convert_selected(
					files,
					on_mask,
					cfg.get("mode", "full"),
					cfg.get("filter_duplicates", False),
					cfg.get("replace_censored_stars", False),
				)
				break
			if 1 <= idx <= len(files):
				i = idx - 1
				on_mask[i] = not on_mask[i]
			else:
				print("Number out of range.")
		except ValueError:
			print("Enter a number to toggle, 0 for settings, or the last number to run.")


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print("\nExiting.")

