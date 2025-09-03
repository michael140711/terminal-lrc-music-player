
from __future__ import annotations

import os
import sys
import random
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

SUPPORTED_EXTS = {".flac", ".ogg", ".aac", ".mp3"}
SONGS_DIRNAME = "songs"
PLAYLISTS_DIRNAME = "playlists"
PLAYLIST_EXT = ".playlist"

# Single config file (settings + playlist)
NOWPLAYING_CFG_FILENAME = "player-config.cfg"


class Settings:
	def __init__(self, shuffle: bool = False, playlist: str = "All songs", audio_delay: float = 0.0):
		self.shuffle = shuffle
		self.playlist = playlist
		self.audio_delay = audio_delay

	@staticmethod
	def load(path: Path) -> "Settings":
		"""Load settings from player-nowplaying.cfg.
		- Shuffle and Playlist from [Player]
		- Audio delay from [BlueTooth Audio Offset]/Offset
		"""
		if not path.exists():
			return Settings()
		# Allow playlist lines without '=' and parse sections safely
		cp = ConfigParser(allow_no_value=True, strict=False)
		try:
			with path.open("r", encoding="utf-8") as f:
				cp.read_file(f)
		except Exception:
			return Settings()
		# Defaults
		shuffle = False
		playlist = "All songs"
		audio_delay = 0.0
		# Player section
		if cp.has_section("Player"):
			# option names are case-insensitive
			if cp.has_option("Player", "shuffle"):
				try:
					shuffle = cp.getboolean("Player", "shuffle")
				except Exception:
					pass
			if cp.has_option("Player", "playlist"):
				try:
					playlist = cp.get("Player", "playlist") or "All songs"
				except Exception:
					pass
		# BlueTooth Audio Offset section
		if cp.has_section("BlueTooth Audio Offset"):
			# option names are case-insensitive
			for key in ("offset", "Offset"):
				if cp.has_option("BlueTooth Audio Offset", key):
					try:
						audio_delay = cp.getfloat("BlueTooth Audio Offset", key)
						break
					except Exception:
						pass
		return Settings(shuffle=shuffle, playlist=playlist, audio_delay=audio_delay)

	def save(self, path: Path, *, playlist_lines: list[str] | None = None) -> None:
		"""Persist settings into player-nowplaying.cfg.
		Writes [Player], [BlueTooth Audio Offset], then [Playlist] (optional if provided).
		"""
		lines: list[str] = []
		lines.append("[Player]")
		lines.append(f"shuffle = {'true' if self.shuffle else 'false'}")
		lines.append(f"playlist = {self.playlist if self.playlist.strip() else 'All songs'}")
		lines.append("")
		lines.append("[BlueTooth Audio Offset]")
		lines.append(f"Offset = {self.audio_delay:.2f}")
		lines.append("")
		lines.append("[Playlist]")
		if playlist_lines:
			lines.extend(playlist_lines)
		content = "\n".join(lines) + "\n"
		with path.open("w", encoding="utf-8") as f:
			f.write(content)


def list_audio_files(songs_dir: Path) -> list[Path]:
	files = []
	for entry in sorted(songs_dir.iterdir(), key=lambda p: p.name.lower()):
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
	cfg_path = base_dir / NOWPLAYING_CFG_FILENAME
	settings = Settings.load(cfg_path)
	while True:
		clear_screen()
		print("== Player Settings ==")
		print(f"🔀 shuffle: {'ON' if settings.shuffle else 'OFF'}")
		print(f"📜 Playlist: {settings.playlist if settings.playlist.strip() else 'All songs'}")
		print(f"🛜  Audio Delay: {settings.audio_delay:.2f}s")
		print("")
		print("== Player Menu ==")
		print(" 1. Run")
		print(" 2. Run (shuffle it)")
		print(" 3. Play All")
		print(" 4. Play a playlist")
		print(" 5. Create a playlist")
		print("")
		print(" 9. settings")
		print(" 0. Exit")
		choice = prompt("Select: ").strip()
		if choice == "1":
			# Directly run the lrc-player without reshuffling or regenerating playlist
			clear_screen()
			print("Starting player (no playlist changes)...")
			launch_lrc_player(base_dir)
			# After returning from player, re-load settings (in case modified elsewhere)
			settings = Settings.load(cfg_path)
		elif choice == "2":
			# One-time shuffle regardless of shuffle setting
			run_with_settings(base_dir, settings, force_shuffle=True)
			settings = Settings.load(cfg_path)
		elif choice == "3":
			# Play all songs (respect current shuffle setting)
			temp_settings = Settings(shuffle=settings.shuffle, playlist="All songs", audio_delay=settings.audio_delay)
			run_with_settings(base_dir, temp_settings)
			settings = Settings.load(cfg_path)
		elif choice == "4":
			# Play from a chosen playlist
			choose_playlist_and_run_flow(base_dir, settings)
			settings = Settings.load(cfg_path)
		elif choice == "5":
			create_playlist_flow(base_dir)
		elif choice == "9":
			# Settings menu (in-memory only; persist on run or exit)
			menu_settings(base_dir, settings)
		elif choice == "0":
			# Save current settings into nowplaying file, preserving existing playlist if present
			persist_settings_only(base_dir, settings)
			clear_screen()
			print("Bye.")
			return
		else:
			# Invalid selection; loop and repaint
			pass


def menu_settings(base_dir: Path, settings: Settings) -> None:
	while True:
		clear_screen()
		print("== Update Settings ==")
		print(f" 1. Suffle: {'ON' if settings.shuffle else 'OFF'}")
		print(f" 2. Audio (lyrics) Delay: {settings.audio_delay:.2f}s")
		print("")
		print(" 0. Go Back")
		sel = prompt("Select: ").strip()
		if sel == "1":
			settings.shuffle = not settings.shuffle
		elif sel == "2":
			clear_screen()
			print("== Settings: Bluetooth Audio Delay Settings ==")
			print(f"Current value: {settings.audio_delay:.2f}s")
			print("")
			print("Delays are usually caused by Bluetooth audio devices, and some other factors.")
			print("This value will be calculated when displaying word-by-word lyrics.")
			print("")
			print("(Click Enter to Save or Go Back)")
			print("")
			val = prompt("Enter new delay (in seconds): ").strip()
			try:
				num = float(val)
				# Clamp to sensible range if desired (optional); keep as is for now
				settings.audio_delay = round(num, 2)
			except ValueError:
				# Just ignore invalid input and repaint
				pass
		elif sel == "0":
			return
		else:
			# ignore invalid and repaint
			pass


def generate_nowplaying(base_dir: Path, settings: Settings, song_names: list[str]) -> Path:
	"""Create player-nowplaying.cfg with [Player], [BlueTooth Audio Offset], and [Playlist]."""
	cfg_path = base_dir / NOWPLAYING_CFG_FILENAME
	lines: list[str] = []
	# [Player]
	lines.append("[Player]")
	lines.append(f"shuffle = {'true' if settings.shuffle else 'false'}")
	lines.append(f"playlist = {settings.playlist if settings.playlist.strip() else 'All songs'}")
	lines.append("")
	# [BlueTooth Audio Offset]
	lines.append("[BlueTooth Audio Offset]")
	lines.append(f"Offset = {settings.audio_delay:.2f}")
	lines.append("")
	# [Playlist]
	lines.append("[Playlist]")
	lines.extend(song_names)
	content = "\n".join(lines) + "\n"
	with cfg_path.open("w", encoding="utf-8") as f:
		f.write(content)
	return cfg_path


def build_song_list(base_dir: Path) -> list[str]:
	"""Return list of song filenames from songs directory (sorted by name)."""
	songs_dir = base_dir / SONGS_DIRNAME
	if not songs_dir.exists():
		return []
	return [p.name for p in list_audio_files(songs_dir)]


def run_with_settings(base_dir: Path, settings: Settings, *, force_shuffle: bool = False) -> None:
	# Determine songs to use
	if settings.playlist.strip() == "All songs":
		songs = build_song_list(base_dir)
	else:
		# Use current [Playlist] from config as the active playlist
		songs = _read_existing_playlist(base_dir)
	if settings.shuffle or force_shuffle:
		random.shuffle(songs)
	# Persist full nowplaying (settings + playlist) before launching
	cfg_path = generate_nowplaying(base_dir, settings, songs)
	# Launch lrc-player.py
	clear_screen()
	print(f"Starting player with {len(songs)} song(s). Now playing config: {cfg_path.name}")
	launch_lrc_player(base_dir)


def _read_existing_playlist(base_dir: Path) -> list[str]:
	"""Read any existing [Playlist] entries from player-nowplaying.cfg if present."""
	cfg_path = base_dir / NOWPLAYING_CFG_FILENAME
	if not cfg_path.exists():
		return []
	try:
		with cfg_path.open("r", encoding="utf-8") as f:
			lines = f.read().splitlines()
	except Exception:
		return []
	playlist_lines: list[str] = []
	in_playlist = False
	for line in lines:
		if line.strip().startswith("[") and line.strip().endswith("]"):
			in_playlist = (line.strip() == "[Playlist]")
			continue
		if in_playlist:
			if line.strip() == "":
				# keep blank lines out of playlist
				continue
			playlist_lines.append(line)
	return playlist_lines


def persist_settings_only(base_dir: Path, settings: Settings) -> None:
	"""Save only [Player] and [BlueTooth Audio Offset], preserving [Playlist] content if any."""
	existing_playlist = _read_existing_playlist(base_dir)
	settings.save(base_dir / NOWPLAYING_CFG_FILENAME, playlist_lines=existing_playlist)


def launch_lrc_player(base_dir: Path) -> None:
	# We simply execute the Python script using subprocess (no shell) to avoid cmd quoting issues
	import subprocess

	script_path = base_dir / "lrc-player.py"
	if not script_path.exists():
		print("lrc-player.py not found.")
		prompt("Press Enter to return...")
		return

	try:
		# Run with the same interpreter; no shell => no cmd quoting problems
		result = subprocess.run(
			[sys.executable, str(script_path)],
			cwd=str(base_dir),
			check=False
		)
		if result.returncode != 0:
			print(f"lrc-player exited with code {result.returncode}")
			prompt("Press Enter to return...")
	except Exception as e:
		print(f"Failed to start lrc-player: {e}")
		prompt("Press Enter to return...")

def main():
	base_dir = Path(__file__).resolve().parent
	try:
		menu_main(base_dir)
	except KeyboardInterrupt:
		print("\nInterrupted.")
		sys.exit(0)


# ===== Playlist features =====

# ANSI color helpers (simple). If unsupported, they'll just render as-is.
ANSI_RED = "\033[31m"
ANSI_RESET = "\033[0m"


def ensure_playlists_dir(base_dir: Path) -> Path:
	d = base_dir / PLAYLISTS_DIRNAME
	d.mkdir(parents=True, exist_ok=True)
	return d


def list_playlist_files(base_dir: Path) -> list[Path]:
	d = ensure_playlists_dir(base_dir)
	files = [p for p in sorted(d.iterdir(), key=lambda p: p.name.lower()) if p.is_file() and p.suffix == PLAYLIST_EXT]
	return files


def parse_playlist_file(path: Path) -> tuple[str, list[str]]:
	"""Return (name, songs) from a .playlist file. If name missing, use stem."""
	name = path.stem  # Always use filename as playlist name
	songs: list[str] = []
	try:
		with path.open("r", encoding="utf-8") as f:
			lines = f.read().splitlines()
	except Exception:
		return (name, songs)

	in_playlist = False
	for line in lines:
		s = line.strip()
		if s.startswith("[") and s.endswith("]"):
			in_playlist = (s == "[Playlist]")
			continue
		if in_playlist and s != "" and not s.startswith("["):
			songs.append(line)
	return (name, songs)


def write_playlist_file(base_dir: Path, playlist_name: str, songs: list[str]) -> Path:
	folder = ensure_playlists_dir(base_dir)
	filename = f"{playlist_name}{PLAYLIST_EXT}"
	path = folder / filename
	lines: list[str] = []
	lines.append("[Playlist_Property]")
	lines.append(f"createdDateTime = \"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"")
	lines.append("")
	lines.append("[Playlist]")
	lines.extend(songs)
	content = "\n".join(lines) + "\n"
	with path.open("w", encoding="utf-8") as f:
		f.write(content)
	return path


def _display_song_selection(title: str, items: list[str]) -> list[str] | None:
	"""Interactive toggle UI. Returns selected items or None if canceled.
	- Initially all NOT Adding (False)
	- User can toggle by entering an index.
	- N+1 => Add ALL; N+2 => Confirm; 0 => Cancel
	"""
	if not items:
		clear_screen()
		print(f"{title}\n")
		print("No songs found.")
		prompt("Press Enter to go back...")
		return None

	selected = [False] * len(items)
	while True:
		clear_screen()
		print(title)
		print("")
		for i, name in enumerate(items, 1):
			if selected[i - 1]:
				display_name = name
				flag = "Adding"
			else:
				display_name = f"{ANSI_RED}{name}{ANSI_RESET}"
				flag = f"{ANSI_RED}NOT Adding{ANSI_RESET}"
			print(f" {i}. {display_name}: {flag}")
		print(" ---")
		add_all_num = len(items) + 1
		not_add_all_num = len(items) + 2
		confirm_num = len(items) + 3
		print(f" {add_all_num}. Add ALL")
		print(f" {not_add_all_num}. Not Adding ALL")
		print(f" {confirm_num}. Confirm and Add selected")
		print(" 0. Cancel and go back")
		inp = prompt("Select (toggle index / action, use space to toggle multiple ones): ").strip()
		if not inp:
			continue
		if inp == ":x":
			# quick back during creation flow
			return None
		# Multi-toggle support: when spaces present or multiple tokens, toggle indices only
		if " " in inp:
			tokens = inp.split()
			indices: set[int] = set()
			for t in tokens:
				try:
					n = int(t)
				except ValueError:
					continue
				if 1 <= n <= len(items):
					indices.add(n)
			# apply unique toggles
			for n in sorted(indices):
				selected[n - 1] = not selected[n - 1]
			continue
		# Single-action handling
		if inp == "0":
			return None
		try:
			num = int(inp)
		except ValueError:
			continue
		if 1 <= num <= len(items):
			selected[num - 1] = not selected[num - 1]
		elif num == add_all_num:
			selected = [True] * len(items)
		elif num == not_add_all_num:
			selected = [False] * len(items)
		elif num == confirm_num:
			result = [name for ok, name in zip(selected, items) if ok]
			if not result:
				# nothing selected, confirm?
				sure = prompt("No songs selected. Confirm empty? (y/N): ").strip().lower()
				if sure != "y":
					continue
			return result
		# else ignore and repaint


def _prompt_new_playlist_name(base_dir: Path) -> str | None:
	ensure_playlists_dir(base_dir)
	while True:
		clear_screen()
		name = prompt("Enter New Playlist Name: ").strip()
		if not name:
			return None
		if name == ":x":
			return None
		# invalid character check for Windows filenames
		invalid = set('\\/:*?"<>|')
		if any(ch in invalid for ch in name):
			clear_screen()
			print("Playlist name contains invalid characters: \\ / : * ? \" < > |")
			print("Please enter a valid name without those characters.")
			print("")
			prompt("Press Enter to enter a new name...")
			continue
		# duplicate check
		folder = base_dir / PLAYLISTS_DIRNAME
		target = folder / f"{name}{PLAYLIST_EXT}"
		if target.exists():
			clear_screen()
			print(f"A playlist named '{name}' already exists at '{target.name}'.")
			print("Please enter a different name, or delete the existing playlist file first.")
			print("")
			prompt("Press Enter to enter a new name...")
			continue
		choice = prompt(f"\nContinue (0, default), or change it (1)? ").strip()
		if choice == "0":
			return name
		elif choice == "1":
			continue
		else:
			# assume continue if user just presses enter
			if choice == "":
				return name
			continue


def create_playlist_flow(base_dir: Path) -> None:
	"""Implements Option 4: Create a playlist."""
	pl_name = _prompt_new_playlist_name(base_dir)
	if not pl_name:
		return

	# Choose how to add songs
	while True:
		clear_screen()
		print("Add songs to playlist by...")
		print(" 1. Choosing from ALL songs")
		print(" 2. Choosing songs from a playlist")
		print(" 3. Adding ALL songs from a playlist")
		print("")
		print(" 0. Cancel and go back")
		sel = prompt("Select: ").strip()
		if sel == "0":
			return
		if sel == ":x":
			return
		elif sel == "1":
			items = build_song_list(base_dir)
			chosen = _display_song_selection("Choose songs from ALL songs", items)
			if chosen is None:
				continue
			write_playlist_file(base_dir, pl_name, chosen)
			clear_screen()
			print(f"Playlist '{pl_name}' saved with {len(chosen)} song(s).")
			prompt("Press Enter to go back...")
			return
		elif sel == "2":
			# Pick a source playlist, then choose subset
			files = list_playlist_files(base_dir)
			chosen_path = _choose_playlist_file_menu(base_dir, files, title="Choose a source playlist")
			if chosen_path is None:
				continue
			_name, songs = parse_playlist_file(chosen_path)
			chosen = _display_song_selection(f"Choose songs from playlist: {_name}", songs)
			if chosen is None:
				continue
			write_playlist_file(base_dir, pl_name, chosen)
			clear_screen()
			print(f"Playlist '{pl_name}' saved with {len(chosen)} song(s).")
			prompt("Press Enter to go back...")
			return
		elif sel == "3":
			files = list_playlist_files(base_dir)
			chosen_path = _choose_playlist_file_menu(base_dir, files, title="Choose a playlist to import ALL songs")
			if chosen_path is None:
				continue
			_name, songs = parse_playlist_file(chosen_path)
			write_playlist_file(base_dir, pl_name, songs)
			clear_screen()
			print(f"Playlist '{pl_name}' saved with {len(songs)} song(s).")
			prompt("Press Enter to go back...")
			return
		else:
			continue


def _choose_playlist_file_menu(base_dir: Path, files: list[Path], *, title: str) -> Path | None:
	while True:
		clear_screen()
		print(title)
		print("")
		if not files:
			print("No playlists found.")
			print("")
			print(" 0. Cancel and go back")
			sel = prompt("Select: ").strip()
			return None
		for i, p in enumerate(files, 1):
			name, _ = parse_playlist_file(p)
			print(f" {i}. {name}")
		print(" ---")
		print(" 0. Cancel and go back")
		sel = prompt("Select: ").strip()
		if sel == "0":
			return None
		if sel == ":x":
			return None
		try:
			num = int(sel)
		except ValueError:
			continue
		if 1 <= num <= len(files):
			return files[num - 1]


def choose_playlist_and_run_flow(base_dir: Path, settings: Settings) -> None:
	"""Implements Option 3: Play from a playlist with menu and Settings available."""
	while True:
		clear_screen()
		print("== Player Settings ==")
		print(f"🔀 shuffle: {'ON' if settings.shuffle else 'OFF'}")
		print(f"📜 Playlist: {settings.playlist if settings.playlist.strip() else 'All songs'}")
		print(f"🛜  Audio Delay: {settings.audio_delay:.2f}s")
		print("")
		print("== Choose Playlist Menu ==")

		entries: list[tuple[str, str]] = []  # (kind, identifier). kind: 'current' or 'file'

		# Add Current Playlist if the config exists and has entries
		current_cfg = base_dir / NOWPLAYING_CFG_FILENAME
		current_playlist_lines = _read_existing_playlist(base_dir) if current_cfg.exists() else []
		idx = 1
		if current_playlist_lines:
			print(f" {idx}. Current Playlist.")
			entries.append(("current", "current"))
			idx += 1

		# List saved playlists
		files = list_playlist_files(base_dir)
		for p in files:
			name, _ = parse_playlist_file(p)
			print(f" {idx}. {name}")
			entries.append(("file", str(p)))
			idx += 1

		if not entries:
			print("You don't have any playlist")

		print("\n---")
		print(" 9. Settings")
		print(" 0. Go Back.")

		sel = prompt("Select: ").strip()
		if sel == "0":
			return
		if sel == "9":
			menu_settings(base_dir, settings)
			# continue loop with potentially updated settings
			continue
		try:
			num = int(sel)
		except ValueError:
			continue
		if num < 1 or num > len(entries):
			continue
		kind, ident = entries[num - 1]
		if kind == "current":
			# Same as choosing Run
			run_with_settings(base_dir, settings)
			return
		else:
			# Load playlist, update config, and run
			path = Path(ident)
			name, songs = parse_playlist_file(path)
			play_songs = songs[:]
			if settings.shuffle:
				random.shuffle(play_songs)
			# Update settings with selected playlist name
			selected_settings = Settings(shuffle=settings.shuffle, playlist=name, audio_delay=settings.audio_delay)
			cfg_path = generate_nowplaying(base_dir, selected_settings, play_songs)
			clear_screen()
			print(f"Starting player with {len(play_songs)} song(s). Now playing config: {cfg_path.name}")
			launch_lrc_player(base_dir)
			return


if __name__ == "__main__":
	main()
