"""player.py

Interactive console menu for preparing audio playback.

What's new:
- Clear screen on each page and only show current content.
- Show current player settings at the top of the main menu.
- Persist settings in player.cfg (Shuffle, Playlist, Audio Delay).
- "Run" creates player-nowplaying.cfg matching sample format and starts lrc-player.py.
- "Play All" runs with all songs (ignoring playlist selection), same as Run otherwise.

Supported audio extensions: .flac, .ogg, .aac, .mp3
"""

from __future__ import annotations

import os
import sys
import random
from configparser import ConfigParser
from pathlib import Path

SUPPORTED_EXTS = {".flac", ".ogg", ".aac", ".mp3"}
SONGS_DIRNAME = "songs"

# Config files
USER_CFG_FILENAME = "player.cfg"  # persists user settings
NOWPLAYING_CFG_FILENAME = "player-nowplaying.cfg"  # consumed by lrc-player.py


class Settings:
	def __init__(self, shuffle: bool = False, playlist: str = "All songs", audio_delay: float = 0.0):
		self.shuffle = shuffle
		self.playlist = playlist
		self.audio_delay = audio_delay

	@staticmethod
	def load(path: Path) -> "Settings":
		if not path.exists():
			# Defaults when no config exists yet
			return Settings()
		cp = ConfigParser()
		try:
			with path.open("r", encoding="utf-8") as f:
				cp.read_file(f)
		except Exception:
			# If file is malformed, fallback to defaults
			return Settings()
		shuffle = cp.getboolean("Player", "Shuffle", fallback=False)
		playlist = cp.get("Player", "Playlist", fallback="All songs")
		audio_delay = cp.getfloat("Player", "AudioDelay", fallback=0.0)
		return Settings(shuffle=shuffle, playlist=playlist, audio_delay=audio_delay)

	def save(self, path: Path) -> None:
		cp = ConfigParser()
		cp["Player"] = {
			"Shuffle": "true" if self.shuffle else "false",
			"Playlist": self.playlist,
			"AudioDelay": f"{self.audio_delay:.2f}",
		}
		with path.open("w", encoding="utf-8") as f:
			cp.write(f)


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
	cfg_path = base_dir / USER_CFG_FILENAME
	settings = Settings.load(cfg_path)
	while True:
		clear_screen()
		print("== Player Settings ==")
		print(f"🔀shuffle: {'ON' if settings.shuffle else 'OFF'}")
		print(f"📜Playlist: {settings.playlist if settings.playlist.strip() else 'All songs'}")
		print(f"🛜Audio Delay: {settings.audio_delay:.2f}s")
		print("")
		print("== Player Menu ==")
		print(" 1. Run")
		print(" 2. Play All")
		print(" 3 Play a play list (not available)")
		print(" 4. Create a play list (not available)")
		print("")
		print(" 9. settings")
		print(" 0. Exit")
		choice = prompt("Select: ").strip()
		if choice == "1":
			# Run using current settings
			run_with_settings(base_dir, settings)
			# After returning from player, re-load settings (in case modified elsewhere)
			settings = Settings.load(cfg_path)
		elif choice == "2":
			# Force playlist to all songs and run
			temp_settings = Settings(shuffle=settings.shuffle, playlist="All songs", audio_delay=settings.audio_delay)
			run_with_settings(base_dir, temp_settings)
			settings = Settings.load(cfg_path)
		elif choice == "3":
			# Not available
			clear_screen()
			print("Feature not yet available.\n")
			prompt("Press Enter to go back...")
		elif choice == "4":
			clear_screen()
			print("Feature not yet available.\n")
			prompt("Press Enter to go back...")
		elif choice == "9":
			# Settings menu (updates and persists)
			menu_settings(base_dir, settings)
			# Re-load in case file was changed externally
			settings = Settings.load(cfg_path)
		elif choice == "0":
			clear_screen()
			print("Bye.")
			return
		else:
			# Invalid selection; loop and repaint
			pass


def menu_settings(base_dir: Path, settings: Settings) -> None:
	cfg_path = base_dir / USER_CFG_FILENAME
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
			# persist immediately
			settings.save(cfg_path)
		elif sel == "2":
			val = prompt("Enter delay in seconds (e.g., 1.23): ").strip()
			try:
				num = float(val)
				# Clamp to sensible range if desired (optional); keep as is for now
				settings.audio_delay = round(num, 2)
				settings.save(cfg_path)
			except ValueError:
				# Just ignore invalid input and repaint
				pass
		elif sel == "0":
			return
		else:
			# ignore invalid and repaint
			pass


def generate_nowplaying(base_dir: Path, song_names: list[str], audio_delay: float) -> Path:
	"""Create player-nowplaying.cfg following the provided sample format."""
	cfg_path = base_dir / NOWPLAYING_CFG_FILENAME
	lines = []
	lines.append("[BlueTooth Audio Offset]")
	lines.append(f"Offset = {audio_delay:.2f}")
	lines.append("")
	lines.append("[Playlist]")
	# Write one filename per line as-is (relative to songs directory)
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


def run_with_settings(base_dir: Path, settings: Settings) -> None:
	# Determine songs to use
	if settings.playlist == "All songs":
		songs = build_song_list(base_dir)
	else:
		# Playlist features not implemented; fall back to all songs
		songs = build_song_list(base_dir)
	if settings.shuffle:
		random.shuffle(songs)
	cfg_path = generate_nowplaying(base_dir, songs, settings.audio_delay)
	# Launch lrc-player.py
	clear_screen()
	print(f"Starting player with {len(songs)} song(s). Now playing config: {cfg_path.name}")
	# Defer to main to actually spawn the process via terminal if desired
	launch_lrc_player(base_dir)


def launch_lrc_player(base_dir: Path) -> None:
	# We simply execute the Python script; rely on user's environment PATH
	# Use os.system for a simple handoff
	script_path = base_dir / "lrc-player.py"
	if not script_path.exists():
		print("lrc-player.py not found.")
		prompt("Press Enter to return...")
		return
	# On Windows cmd/powershell, this will run and return when process exits
	exit_code = os.system(f'"{sys.executable}" "{script_path}"')
	if exit_code != 0:
		print(f"lrc-player exited with code {exit_code}")
		prompt("Press Enter to return...")


def main():
	base_dir = Path(__file__).resolve().parent
	try:
		menu_main(base_dir)
	except KeyboardInterrupt:
		print("\nInterrupted.")
		sys.exit(0)


if __name__ == "__main__":
	main()
