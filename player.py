"""player.py

Interactive console menu for preparing audio playback.

Features implemented now:
1. Play All: Lists all supported audio files in ./songs. User can remove files by selecting their number; choosing 0 saves remaining list to player-temp.cfg.
2/3. Playlist features: placeholders (not yet implemented).
9. Settings: placeholder.
0. Exit.

Supported audio extensions: .flac, .ogg, .aac, .mp3

Output file format (player-temp.cfg): one relative filename per line (relative to songs directory).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SUPPORTED_EXTS = {".flac", ".ogg", ".aac", ".mp3"}
CFG_FILENAME = "player-temp.cfg"
SONGS_DIRNAME = "songs"


def list_audio_files(songs_dir: Path) -> list[Path]:
	files = []
	for entry in sorted(songs_dir.iterdir()):
		if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTS:
			files.append(entry)
	return files


def clear_screen():  # simple cross-platform clear
	os.system("cls" if os.name == "nt" else "clear")


def prompt(msg: str) -> str:
	try:
		return input(msg)
	except EOFError:
		return ""


def menu_main(base_dir: Path):
	while True:
		print("=== Player Menu ===")
		print("1. Play All")
		print("2. Play a playlist (not available)")
		print("3. Create a playlist (not available)")
		print("9. Settings")
		print("0. Exit")
		choice = prompt("Select: ").strip()
		if choice == "1":
			handle_play_all(base_dir)
		elif choice == "2":
			print("Feature not yet available.\n")
		elif choice == "3":
			print("Feature not yet available.\n")
		elif choice == "9":
			print("Settings not yet available.\n")
		elif choice == "0":
			print("Bye.")
			return
		else:
			print("Invalid selection.\n")


def handle_play_all(base_dir: Path):
	songs_dir = base_dir / SONGS_DIRNAME
	if not songs_dir.exists():
		print(f"Songs directory not found: {songs_dir}")
		return
	remaining = list_audio_files(songs_dir)
	removed: list[Path] = []
	while True:
		print("\n=== Play All - Select files to REMOVE (0 to finish) ===")
		if not remaining:
			print("(No files left. Type 0 to save an empty list or 'b' to go back.)")
		for idx, f in enumerate(remaining, start=1):
			print(f"{idx}. {f.name}")
		print("0. Play Them! (save list)")
		print("r. Reset (restore removed)")
		print("b. Back to main menu without saving")
		sel = prompt("Select number to remove / option: ").strip().lower()
		if sel == "0":
			save_cfg(base_dir, [f.name for f in remaining])
			print(f"Saved {len(remaining)} file(s) to {CFG_FILENAME}.\n")
			return
		if sel == "b":
			print("Returning without saving.\n")
			return
		if sel == "r":
			remaining.extend(removed)
			remaining.sort(key=lambda p: p.name.lower())
			removed.clear()
			clear_screen()
			continue
		if not sel.isdigit():
			print("Invalid input.")
			continue
		idx = int(sel)
		if 1 <= idx <= len(remaining):
			removed_file = remaining.pop(idx - 1)
			removed.append(removed_file)
			clear_screen()
		else:
			print("Number out of range.")


def save_cfg(base_dir: Path, filenames: list[str]):
	cfg_path = base_dir / CFG_FILENAME
	with cfg_path.open("w", encoding="utf-8") as f:
		for name in filenames:
			f.write(name + "\n")


def main():
	base_dir = Path(__file__).resolve().parent
	try:
		menu_main(base_dir)
	except KeyboardInterrupt:
		print("\nInterrupted.")
		sys.exit(0)


if __name__ == "__main__":
	main()
