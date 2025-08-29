
from __future__ import annotations

import os
import sys
import random
from configparser import ConfigParser
from pathlib import Path

SUPPORTED_EXTS = {".flac", ".ogg", ".aac", ".mp3"}
SONGS_DIRNAME = "songs"

# Single config/nowplaying file (settings + playlist)
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
		cp = ConfigParser(allow_no_value=True)
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


def run_with_settings(base_dir: Path, settings: Settings) -> None:
	# Determine songs to use
	if settings.playlist == "All songs":
		songs = build_song_list(base_dir)
	else:
		# Playlist features not implemented; fall back to all songs
		songs = build_song_list(base_dir)
	if settings.shuffle:
		random.shuffle(songs)
	# Persist full nowplaying (settings + playlist) before launching
	cfg_path = generate_nowplaying(base_dir, settings, songs)
	# Launch lrc-player.py
	clear_screen()
	print(f"Starting player with {len(songs)} song(s). Now playing config: {cfg_path.name}")
	# Defer to main to actually spawn the process via terminal if desired
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


if __name__ == "__main__":
	main()
