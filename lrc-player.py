"""
lrc-player 8/18/2025 5:18 PM
"""

version = "3.6.0"
author = "Michael"

import os
import sys
import time
import threading
from pathlib import Path
import re
from typing import List, Tuple, Optional
import msvcrt  # Windows-specific for keyboard input
import math  # <-- add this

try:
    import pygame
except ImportError:
    print("pygame is required. Install with: pip install pygame")
    sys.exit(1)

try:
    from colorama import init, Fore, Back, Style
    init()  # Initialize colorama for Windows
except ImportError:
    print("colorama is recommended for better display. Install with: pip install colorama")
    # Fallback to no colors
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Back:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Style:
        DIM = NORMAL = BRIGHT = RESET_ALL = ""

CFG_FILENAME = "player-temp.cfg"
SONGS_DIRNAME = "songs"



class LyricWord:
    def __init__(self, timestamp: float, text: str, end_timestamp: Optional[float] = None):
        self.timestamp = timestamp
        self.text = text
        # Optional explicit end time for this word (e.g., <start>word<end>)
        self.end_timestamp = end_timestamp

    def __repr__(self):
        return f"LyricWord({self.timestamp:.3f}, '{self.text}')"


class LyricLine:
    def __init__(self, timestamp: float, text: str, words: List['LyricWord'] = None):
        self.timestamp = timestamp
        self.text = text
        self.words = words or []
        self.is_precise = len(self.words) > 0

    def __repr__(self):
        return f"LyricLine({self.timestamp:.3f}, '{self.text}', words={len(self.words)})"


class LRCParser:
    @staticmethod
    def parse_timestamp(timestamp_str: str) -> float:
        """Parse LRC timestamp like [00:08.987] or <00:08.987> to seconds"""
        # Remove brackets/angle brackets and parse mm:ss.sss
        time_part = timestamp_str.strip('[]<>')
        if ':' not in time_part:
            return 0.0

        try:
            parts = time_part.split(':')
            minutes = int(parts[0])
            seconds_parts = parts[1].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1].ljust(3, '0')[:3]) if len(seconds_parts) > 1 else 0

            return minutes * 60 + seconds + milliseconds / 1000.0
        except (ValueError, IndexError):
            return 0.0

    @staticmethod
    def parse_precise_lrc_line(line: str) -> Tuple[float, List[LyricWord]]:
        """Parse a precise LRC line with word-by-word timing"""
        words: List[LyricWord] = []

        # Pattern to match any tag and the text until the next tag or end-of-line.
        # If the text is empty, we treat this as a closing tag for the previous word's end.
        word_pattern = r'<(\d{2}:\d{2}\.\d{2,3})>([^<]*?)(?=<|$)'

        last_word: Optional[LyricWord] = None
        for match in re.finditer(word_pattern, line):
            timestamp_str = match.group(1)
            segment_text = match.group(2)
            ts = LRCParser.parse_timestamp(f'<{timestamp_str}>')

            if segment_text == "":
                # This is most likely an end timestamp like <mm:ss.xx> immediately before
                # the next word or end-of-line; attach to the previous word if present.
                if last_word is not None:
                    last_word.end_timestamp = ts
                continue

            # Normal case: this is a new word (text can include spaces we want to preserve)
            w = LyricWord(ts, segment_text)
            words.append(w)
            last_word = w

        # Return the timestamp of the first word and all words
        first_timestamp = words[0].timestamp if words else 0.0
        return first_timestamp, words

    @staticmethod
    def parse_lrc_file(lrc_path: Path) -> List[LyricLine]:
        """Parse LRC file and return list of LyricLine objects (supports both standard and precise LRC)"""
        lyrics = []

        if not lrc_path.exists():
            return lyrics

        try:
            with open(lrc_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Pattern to match LRC lines: [timestamp] text
            line_pattern = r'\[(\d{2}:\d{2}\.\d{2,3})\]\s*(.*)'

            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue

                match = re.match(line_pattern, line)
                if match:
                    timestamp_str = match.group(1)
                    text_content = match.group(2).strip()

                    # Skip empty text or metadata lines
                    if text_content and not text_content.startswith('[') and not text_content.startswith('tool:'):
                        line_timestamp = LRCParser.parse_timestamp(f'[{timestamp_str}]')

                        # Check if this line contains precise word timing
                        if '<' in text_content and '>' in text_content:
                            # Parse precise timing
                            first_word_timestamp, words = LRCParser.parse_precise_lrc_line(text_content)
                            # Use the line timestamp if available, otherwise use first word timestamp
                            lyric_line = LyricLine(line_timestamp, text_content, words)
                        else:
                            # Standard LRC line
                            lyric_line = LyricLine(line_timestamp, text_content)

                        lyrics.append(lyric_line)

            # Sort by timestamp
            lyrics.sort(key=lambda x: x.timestamp)

        except Exception as e:
            print(f"Error parsing LRC file {lrc_path}: {e}")

        return lyrics


class MusicPlayer:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.songs_dir = base_dir / SONGS_DIRNAME
        self.cfg_path = base_dir / CFG_FILENAME
        self.current_song_index = 0
        self.playlist = []
        self.is_playing = False
        self.is_paused = False
        self.current_lyrics = []
        self.current_lyric_index = 0
        self.start_time = 0.0
        self.pause_start_time = 0.0
        self.total_pause_time = 0.0
        # seeking and timing helpers
        self.seek_offset = 0.0  # kept for compatibility; not used for seek math
        self._audio_lock = threading.RLock()  # serialize audio ops
        self._last_seek_at = 0.0
        self._min_seek_interval = 0.12  # debounce rapid arrow taps ~120ms
        self._song_duration_cache = {}
        self.navigation_action = None  # 'next' | 'previous' | 'quit' | None
        self.quit_confirmation_time = 0.0
        self.quit_message_displayed = False

        # Initialize pygame mixer
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)

    def load_playlist(self) -> bool:
        """Load playlist from player-temp.cfg"""
        if not self.cfg_path.exists():
            print(f"Config file not found: {self.cfg_path}")
            return False

        try:
            with open(self.cfg_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            self.playlist = []
            for line in lines:
                filename = line.strip()
                if filename:
                    song_path = self.songs_dir / filename
                    if song_path.exists():
                        self.playlist.append(song_path)
                    else:
                        print(f"Warning: Song file not found: {song_path}")

            print(f"Loaded {len(self.playlist)} songs from playlist")
            return len(self.playlist) > 0

        except Exception as e:
            print(f"Error loading playlist: {e}")
            return False

    def find_partial_lyrics_match(self, song_stem: str) -> Optional[Path]:
        """Find LRC file that partially matches the song name"""
        if not self.songs_dir.exists():
            return None

        # Get all LRC files in the songs directory
        lrc_files = list(self.songs_dir.glob("*.lrc"))

        if not lrc_files:
            return None

        # Normalize the song name for comparison
        normalized_song = self.normalize_filename(song_stem)

        best_match = None
        best_score = 0

        for lrc_file in lrc_files:
            lrc_stem = lrc_file.stem
            normalized_lrc = self.normalize_filename(lrc_stem)

            # Calculate match score
            score = self.calculate_match_score(normalized_song, normalized_lrc)

            if score > best_score and score >= 0.7:  # Minimum 70% match
                best_score = score
                best_match = lrc_file

        return best_match

    def normalize_filename(self, filename: str) -> str:
        """Normalize filename for better matching"""
        # Convert to lowercase
        normalized = filename.lower()

        # Replace various separators with space
        normalized = re.sub(r'[_\-\(\)\[\]]', ' ', normalized)

        # Remove extra information commonly found in LRC files
        # Remove BPM info (e.g., "- 209 -")
        normalized = re.sub(r'\s*-\s*\d{2,3}\s*-\s*', ' ', normalized)

        # Remove "_qm" suffix
        normalized = re.sub(r'\s*qm\s*$', '', normalized)

        # Remove "explicit" tags
        normalized = re.sub(r'\s*explicit\s*', ' ', normalized)

        # Remove "feat" variations
        normalized = re.sub(r'\s*feat[^a-z]*\s*', ' feat ', normalized)

        # Normalize multiple spaces to single space
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def calculate_match_score(self, song_name: str, lrc_name: str) -> float:
        """Calculate how well two normalized filenames match"""
        # Split into words
        song_words = song_name.split()
        lrc_words = lrc_name.split()

        if not song_words or not lrc_words:
            return 0.0

        # Check if the beginning of the LRC matches the song
        matching_words = 0
        min_length = min(len(song_words), len(lrc_words))

        for i in range(min_length):
            if song_words[i] == lrc_words[i]:
                matching_words += 1
            else:
                break

        # Calculate score based on:
        # 1. How many words match from the beginning
        # 2. What percentage of the song name is matched
        if matching_words == 0:
            return 0.0

        # Score is the percentage of song words that match
        score = matching_words / len(song_words)

        # Bonus if we match a significant portion of the LRC name too
        lrc_match_ratio = matching_words / len(lrc_words)
        if lrc_match_ratio >= 0.5:
            score += 0.1  # Small bonus

        return min(1.0, score)

    def load_lyrics(self, song_path: Path) -> List[LyricLine]:
        """Load lyrics for the given song with support for partial name matching"""
        # First, try exact match (current behavior)
        lrc_path = song_path.with_suffix('.lrc')
        if lrc_path.exists():
            lyrics = LRCParser.parse_lrc_file(lrc_path)
            if lyrics:
                precise_count = sum(1 for lyric in lyrics if lyric.is_precise)
                if precise_count > 0:
                    print(f"Detected precise LRC with word-by-word timing ({precise_count} lines)")
                print(f"Found exact match: {lrc_path.name}")
                return lyrics

        # If exact match not found, try partial matching
        song_stem = song_path.stem
        best_match = self.find_partial_lyrics_match(song_stem)

        if best_match:
            lyrics = LRCParser.parse_lrc_file(best_match)
            if lyrics:
                precise_count = sum(1 for lyric in lyrics if lyric.is_precise)
                if precise_count > 0:
                    print(f"Detected precise LRC with word-by-word timing ({precise_count} lines)")
                print(f"Found partial match: {best_match.name}")
                return lyrics

        print(f"No lyrics found for: {song_path.name}")
        return []

    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def hide_cursor(self):
        """Hide the terminal cursor"""
        print('\033[?25l', end='', flush=True)

    def show_message(self, message: str, duration: float = 2.0):
        """Show a temporary message for a specified duration"""
        self.move_cursor_home()

        # Display player info (keep the header)
        info_lines = [
            f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}",
            f"{Fore.GREEN}Version: {version} | Author: {author}{Style.RESET_ALL}",
            f"{Fore.YELLOW}🎵 {message}{Style.RESET_ALL}",
            f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        for line in info_lines:
            self.print_line_clean(line)

    def show_cursor(self):
        """Show the terminal cursor"""
        print('\033[?25h', end='', flush=True)

    def move_cursor_home(self):
        """Move cursor to top-left without clearing screen"""
        print('\033[H', end='', flush=True)

    def clear_current_line(self):
        """Clear the current line completely"""
        print('\033[K', end='', flush=True)

    def print_line_clean(self, text: str):
        """Print a line and clear any remaining characters"""
        print(text, end='')
        print('\033[K')  # Clear from cursor to end of line

    def get_current_lyric_index(self) -> int:
        """Get the index of the current lyric line"""
        if not self.current_lyrics:
            return -1

        current_time = self.get_playback_position()
        current_index = -1
        for i, lyric in enumerate(self.current_lyrics):
            if lyric.timestamp <= current_time:
                current_index = i
            else:
                break
        return current_index

    def display_lyrics(self):
        """Display lyrics with current line highlighted and word-by-word for precise LRC"""
        if not self.current_lyrics:
            return []

        # Get current playback position
        current_time = self.get_playback_position()

        # Find current lyric line
        current_index = -1
        for i, lyric in enumerate(self.current_lyrics):
            if lyric.timestamp <= current_time:
                current_index = i
            else:
                break

        # Display lyrics window (show 5 lines: 2 before, current, 2 after)
        window_size = 5
        start_index = max(0, current_index - 2)
        end_index = min(len(self.current_lyrics), start_index + window_size)

        # Adjust start if we're near the end
        if end_index - start_index < window_size and start_index > 0:
            start_index = max(0, end_index - window_size)

        lyrics_display = []
        for i in range(start_index, end_index):
            lyric = self.current_lyrics[i]

            if i == current_index:
                # Current line - handle word-by-word highlighting for precise LRC
                if lyric.is_precise and lyric.words:
                    # Provide the next line timestamp to refine last-word duration
                    next_line_timestamp = None
                    if current_index + 1 < len(self.current_lyrics):
                        next_line_timestamp = self.current_lyrics[current_index + 1].timestamp
                    line_text = self.format_precise_lyric_line(lyric, current_time, next_line_timestamp)
                    line = f"♪ {line_text}"
                else:
                    # Standard highlighting for non-precise lines - use white instead of background
                    line = f"{Fore.WHITE}♪ {lyric.text}{Style.RESET_ALL}"
            elif i == current_index + 1:
                # Next line - use same color as other lines (cyan)
                if lyric.is_precise and lyric.words:
                    # For next line, show clean text without timing highlights
                    clean_text = self.get_clean_text_from_words(lyric.words)
                    line = f"{Fore.CYAN}  {clean_text}{Style.RESET_ALL}"
                else:
                    line = f"{Fore.CYAN}  {lyric.text}{Style.RESET_ALL}"
            else:
                # Other lines
                if lyric.is_precise and lyric.words:
                    clean_text = self.get_clean_text_from_words(lyric.words)
                    line = f"{Fore.CYAN}  {clean_text}{Style.RESET_ALL}"
                else:
                    line = f"{Fore.CYAN}  {lyric.text}{Style.RESET_ALL}"

            lyrics_display.append(line)

        return lyrics_display

    def format_precise_lyric_line(self, lyric: LyricLine, current_time: float, next_line_timestamp: Optional[float] = None) -> str:
        """Format a precise lyric line with smooth color transitions and character-by-character animation.

        Duration of the active word is derived from the timestamp gap to the next word. For the last
        word in the line, we use either the next line's timestamp (if provided) or fall back to the
        median gap of the line (and finally a small default) to keep animation smooth.
        """
        if not lyric.words:
            return f"{Fore.WHITE}{lyric.text}{Style.RESET_ALL}"

        formatted_parts = []
        current_word_index = -1

    # Find the current word being sung
        for i, word in enumerate(lyric.words):
            if word.timestamp <= current_time:
                current_word_index = i
            else:
                break

        # Format each word with smooth transitions
        for i, word in enumerate(lyric.words):
            if i < current_word_index:
                # Already sung words - white
                formatted_parts.append(f"{Fore.WHITE}{word.text}{Style.RESET_ALL}")
            elif i == current_word_index:
                # Currently singing word - animate character by character
                # Compute dynamic duration using the gap to the next word; clamp to reasonable bounds
                # to avoid flicker (too small) or sluggishness (too large).
                min_dur, max_dur = 0.05, 2.5
                # Prefer explicit end timestamp when available
                raw_duration: float
                if word.end_timestamp is not None:
                    raw_duration = max(0.0, word.end_timestamp - word.timestamp)
                elif i + 1 < len(lyric.words):
                    raw_duration = max(0.0, lyric.words[i + 1].timestamp - word.timestamp)
                else:
                    # Last word: use next line start if provided, otherwise median inter-word gap or default
                    if next_line_timestamp is not None:
                        raw_duration = max(0.0, next_line_timestamp - word.timestamp)
                    else:
                        gaps = [
                            max(0.0, lyric.words[j + 1].timestamp - lyric.words[j].timestamp)
                            for j in range(len(lyric.words) - 1)
                        ]
                        if gaps:
                            sorted_gaps = sorted(gaps)
                            mid = len(sorted_gaps) // 2
                            raw_duration = (
                                (sorted_gaps[mid] if len(sorted_gaps) % 2 == 1 else
                                 (sorted_gaps[mid - 1] + sorted_gaps[mid]) / 2.0)
                            )
                        else:
                            raw_duration = 0.5

                duration = max(min_dur, min(max_dur, raw_duration if raw_duration > 0 else 0.5))
                animated_word = self.animate_word_reveal(word, current_time, duration)
                formatted_parts.append(animated_word)
            else:
                # Future words - blue
                formatted_parts.append(f"{Fore.BLUE}{word.text}{Style.RESET_ALL}")

        return "".join(formatted_parts)

    def animate_word_reveal(self, word: LyricWord, current_time: float, duration: Optional[float] = None) -> str:
        """Create character-by-character reveal animation for current word.

        duration: The computed duration for revealing this word. If None, defaults to 0.5s.
        """
        word_duration = duration if duration is not None else 0.5
        # Protect against zero/negative durations
        if word_duration <= 0:
            word_duration = 0.5

        # Shrink the word duration when the duration is way too long, using a curve to scale it down
        L = 2.0 # max duration for compression
        Curve = 0.95  # Compression factor
        compressed = L * (1 - math.exp(-word_duration / L * Curve))
        word_duration = min(word_duration, compressed)
        word_duration = max(0.05, word_duration)  # Ensure minimum duration

        word_progress = min(1.0, max(0.0, (current_time - word.timestamp) / word_duration))

        # Calculate how many characters should be revealed
        chars_to_reveal = int(len(word.text) * word_progress)

        # Split the word into revealed and unrevealed parts
        revealed_part = word.text[:chars_to_reveal]
        unrevealed_part = word.text[chars_to_reveal:]

        # Create the animated display
        animated_text = f"{Fore.WHITE}{revealed_part}{Style.RESET_ALL}{Fore.BLUE}{unrevealed_part}{Style.RESET_ALL}"

        return animated_text

    def get_clean_text_from_words(self, words: List[LyricWord]) -> str:
        """Extract clean text from word list for display"""
        return "".join(word.text for word in words)

    def get_playback_position(self) -> float:
        """Get current playback position in seconds"""
        if self.is_paused:
            # When paused, return the time at which we paused
            return max(0, self.pause_start_time - self.start_time - self.total_pause_time + self.seek_offset)
        else:
            # When playing, return current time minus start time and total pause time plus seek offset
            return max(0, time.time() - self.start_time - self.total_pause_time + self.seek_offset)

    def _get_current_song(self) -> Optional[Path]:
        if 0 <= self.current_song_index < len(self.playlist):
            return self.playlist[self.current_song_index]
        return None

    def _estimate_duration_from_lyrics(self) -> Optional[float]:
        # Fallback: use last precise timestamp or last line timestamp if available
        if not self.current_lyrics:
            return None
        try:
            last_ts = max((line.words[-1].timestamp if line.is_precise and line.words else line.timestamp)
                          for line in self.current_lyrics)
            # Add small tail to approximate track end beyond last lyric
            return max(0.0, last_ts + 3.0)
        except Exception:
            return None

    def get_song_duration(self, song_path: Path) -> Optional[float]:
        """Return song duration in seconds if determinable; caches per path."""
        try:
            if song_path in self._song_duration_cache:
                return self._song_duration_cache[song_path]

            # Try using pygame Sound (may not support all formats; can be memory heavy for very large files)
            duration = None
            try:
                snd = pygame.mixer.Sound(str(song_path))
                duration = float(snd.get_length())
            except Exception:
                duration = None

            if duration is None or duration <= 0:
                duration = self._estimate_duration_from_lyrics()

            if duration is not None and duration > 0:
                self._song_duration_cache[song_path] = duration
                return duration
        except Exception:
            pass
        return None

    def seek_audio(self, delta_seconds: float):
        """Seek by delta seconds with clamping [0, duration-2], robust against rapid taps and modifiers."""
        with self._audio_lock:
            now = time.time()
            if (now - self._last_seek_at) < self._min_seek_interval:
                # debounce rapid repeated seeks
                return
            self._last_seek_at = now

            current_song = self._get_current_song()
            if not current_song:
                return

            # Determine current and target positions
            current_pos = self.get_playback_position()

            # Clamp bounds
            duration = self.get_song_duration(current_song)
            min_pos = 0.0
            max_pos = None
            if duration is not None and duration > 0:
                max_pos = max(0.0, duration - 2.0)  # guard 2s before end

            target_pos = current_pos + float(delta_seconds)
            if target_pos < min_pos:
                target_pos = min_pos
            if max_pos is not None and target_pos > max_pos:
                target_pos = max_pos

            # No-op if change is negligible
            if abs(target_pos - current_pos) < 0.01:
                return

            was_paused = self.is_paused
            try:
                # Restart playback from target position
                pygame.mixer.music.stop()
                pygame.mixer.music.load(str(current_song))
                # pygame's start parameter is in seconds for OGG/MP3; may vary by codec but works for our set
                pygame.mixer.music.play(start=target_pos)

                # Reset timing references against new start
                now2 = time.time()
                self.start_time = now2 - target_pos
                # zero pause accumulator since we realigned to absolute timeline
                self.total_pause_time = 0
                self.seek_offset = 0

                if was_paused:
                    # Re-apply pause state accurately
                    self.pause_start_time = now2
                    pygame.mixer.music.pause()
            except Exception as e:
                print(f"Error seeking: {e}")
                # best-effort: do not alter timing further
                return

    def display_player_info(self, song_path: Path):
        """Display current song info and controls"""
        song_name = song_path.stem

        # Get playback time
        current_time = self.get_playback_position()
        current_min = int(current_time // 60)
        current_sec = current_time % 60

        status = "⏸️  PAUSED " if self.is_paused else "▶️  PLAYING"

        info_lines = [
            f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}",
            f"{Fore.GREEN}Version: {version} | Author: {author}{Style.RESET_ALL}",
            f"{Fore.YELLOW}🎵 Now Playing: {song_name}{Style.RESET_ALL}",
            # f"{Fore.BLUE}📀 Track {self.current_song_index + 1} of {len(self.playlist)}{Style.RESET_ALL}",
            f"{Fore.MAGENTA}{status} |{Fore.BLUE}📀 Track {self.current_song_index + 1} of {len(self.playlist)} | Time: {current_min:02d}:{current_sec:05.2f}{Style.RESET_ALL}",
            f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}",
            "",
        ]

        return info_lines

    def display_controls(self):
        """Display control instructions"""
        # Check if we should show quit confirmation message
        if self.quit_confirmation_time > 0:
            if time.time() - self.quit_confirmation_time <= 3.0:
                # Show quit confirmation message
                controls = [
                    "",
                    f"{Fore.WHITE}{'─'*60}{Style.RESET_ALL}",
                    f"{Fore.RED}Press 'Q' again to quit (within 3 seconds){Style.RESET_ALL}",
                    f"{Fore.WHITE}{'─'*60}{Style.RESET_ALL}",
                ]
                return controls
            else:
                # Timeout reached, reset quit confirmation
                self.quit_confirmation_time = 0
                self.quit_message_displayed = False

        # Normal controls display
        controls = [
            "",
            # UNCOMMENT THIS TO SHOW CONTROLS
            f"{Fore.WHITE}{'─'*60}{Style.RESET_ALL}",
            f"{Fore.CYAN} [SPACE] Pause | [N] Next | [P] Previous | [←/→] Seek | [Q] Quit{Style.RESET_ALL}",
            f"{Fore.WHITE}{'─'*60}{Style.RESET_ALL}",
        ]
        return controls

    def play_song(self, song_path: Path):
        """Play a single song with lyrics display"""
        try:
            print(f"Loading: {song_path.name}")

            # Load the song
            pygame.mixer.music.load(str(song_path))

            # Load lyrics
            self.current_lyrics = self.load_lyrics(song_path)
            print(f"Loaded {len(self.current_lyrics)} lyric lines")

            # Start playing
            pygame.mixer.music.play()
            self.is_playing = True
            self.is_paused = False
            self.start_time = time.time()
            self.total_pause_time = 0
            self.seek_offset = 0  # Reset seek offset for new song
            # prime duration cache for clamping
            try:
                _ = self.get_song_duration(song_path)
            except Exception:
                pass

            # Initial display setup
            self.clear_screen()
            self.hide_cursor()  # Hide cursor for clean display
            last_lyric_index = -1
            last_pause_state = False
            last_display_time = 0

            # Start input handler thread AFTER is_playing is True
            input_thread = threading.Thread(target=self.handle_input, daemon=True)
            input_thread.start()

            # Main display loop
            while self.is_playing:
                current_time = time.time()
                current_lyric_index = self.get_current_lyric_index()

                # Update display more frequently for smooth animation and quit confirmation
                should_update = (
                    current_lyric_index != last_lyric_index or
                    self.is_paused != last_pause_state or
                    current_time - last_display_time > 0.05 or  # Update every 50ms for smooth animation
                    self.quit_confirmation_time > 0  # Update when quit confirmation is active
                )

                if should_update:
                    self.move_cursor_home()

                    # Display player info
                    info_lines = self.display_player_info(song_path)
                    for line in info_lines:
                        self.print_line_clean(line)

                    # Display lyrics
                    if self.current_lyrics:
                        lyrics_lines = self.display_lyrics()
                        for line in lyrics_lines:
                            self.print_line_clean(line)
                    else:
                        self.print_line_clean(f"{Fore.YELLOW}  No lyrics found for this song{Style.RESET_ALL}")

                    # Display controls
                    control_lines = self.display_controls()
                    for line in control_lines:
                        self.print_line_clean(line)

                    # Update tracking variables
                    last_lyric_index = current_lyric_index
                    last_pause_state = self.is_paused
                    last_display_time = current_time

                # Check if song finished
                if not pygame.mixer.music.get_busy() and not self.is_paused:
                    self.is_playing = False  # Mark as finished naturally
                    break

                time.sleep(0.05)  # Check every 50ms for smooth animation

        except Exception as e:
            print(f"Error playing {song_path.name}: {e}")
        finally:
            self.show_cursor()  # Always restore cursor when done

    def handle_input(self):
        """Handle keyboard input in a separate thread"""
        def _read_key_event() -> Optional[str]:
            """Translate msvcrt byte sequences to high-level keys; ignore combos/modifiers."""
            if not msvcrt.kbhit():
                return None

            b = msvcrt.getch()
            # Extended keys start with 0x00 or 0xE0; next byte determines key
            if b in (b'\x00', b'\xe0'):
                if not msvcrt.kbhit():
                    # Incomplete sequence; ignore
                    return None
                b2 = msvcrt.getch()
                # Map only left/right arrows; ignore everything else (prevents key combinations)
                if b2 == b'K':
                    return 'LEFT'
                if b2 == b'M':
                    return 'RIGHT'
                return None

            # Regular keys
            try:
                ch = b.decode('utf-8', errors='ignore')
            except Exception:
                return None

            if not ch:
                return None
            # Filter out control characters and combinations (non-printable)
            if ord(ch) < 32:
                return None
            return ch.lower()

        while self.is_playing:
            try:
                key = _read_key_event()
                if key is None:
                    time.sleep(0.03)
                    continue

                if key == 'LEFT':
                    self.seek_audio(-5.0)
                    continue
                if key == 'RIGHT':
                    self.seek_audio(5.0)
                    continue

                if key == ' ':  # Space bar - pause/resume
                    if self.is_paused:
                        pygame.mixer.music.unpause()
                        # Calculate total pause duration and add to total_pause_time
                        pause_duration = time.time() - self.pause_start_time
                        self.total_pause_time += pause_duration
                        self.is_paused = False
                    else:
                        pygame.mixer.music.pause()
                        self.pause_start_time = time.time()
                        self.is_paused = True
                    continue

                if key == 'n':  # Next song
                    if self.current_song_index >= len(self.playlist) - 1:
                        self.show_message("Reached bottom")
                    else:
                        self.navigation_action = 'next'
                        self.is_playing = False
                        pygame.mixer.music.stop()
                    continue

                if key == 'p':  # Previous song
                    if self.current_song_index <= 0:
                        self.show_message("Reached top")
                    else:
                        self.navigation_action = 'previous'
                        self.is_playing = False
                        pygame.mixer.music.stop()
                    continue

                if key == 'q':  # Quit with confirmation
                    if self.quit_confirmation_time > 0 and time.time() - self.quit_confirmation_time <= 3.0:
                        self.navigation_action = 'quit'
                        self.is_playing = False
                        pygame.mixer.music.stop()
                        return False
                    else:
                        self.quit_confirmation_time = time.time()
                        self.quit_message_displayed = True
                    continue

                # Ignore anything else
            except (UnicodeDecodeError, KeyboardInterrupt):
                pass
            time.sleep(0.03)

        return True

    def play_all(self):
        """Play all songs in the playlist"""
        if not self.load_playlist():
            return

        try:
            while self.current_song_index < len(self.playlist):
                song_path = self.playlist[self.current_song_index]

                # Reset navigation action before playing
                self.navigation_action = None

                # Play the song (input thread is now started inside play_song)
                self.play_song(song_path)

                # Handle navigation based on user action
                if self.navigation_action == 'quit':
                    break
                elif self.navigation_action == 'next':
                    self.current_song_index += 1
                elif self.navigation_action == 'previous':
                    self.current_song_index -= 1
                elif not self.is_playing:  # Song finished naturally
                    self.current_song_index += 1
                else:
                    # This shouldn't happen, but just in case
                    break

            if self.navigation_action != 'quit':
                print(f"\n{Fore.GREEN}Finished playing all songs!{Style.RESET_ALL}")

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Playback interrupted{Style.RESET_ALL}")
        finally:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            self.show_cursor()  # Restore cursor on exit


def main():
    """Main entry point"""
    print(f"{Fore.CYAN}🎵 LRC Music Player 3.2{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Loading playlist...{Style.RESET_ALL}")

    base_dir = Path(__file__).resolve().parent
    player = MusicPlayer(base_dir)

    try:
        player.play_all()
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
    finally:
        player.show_cursor()  # Ensure cursor is restored
        print(f"{Fore.WHITE}Goodbye!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
