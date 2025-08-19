# -*- coding: utf-8 -*-
"""Parse Apple Music playlist JSON and output a CSV with song details."""

import csv
import json
from pathlib import Path

PLAYLIST_JSON = Path("playlist.json")
OUTPUT_CSV = Path("playlist.csv")

def _extract_songs(data: dict) -> list:
    """
    Return song entries from the playlist JSON.

    Supports multiple Apple Music response shapes:
    - resources.library-songs: { id: { ... }, ... }
    - included: [ { type: "library-songs", ... }, ... ]
    - top-level library-songs (list or dict) as a fallback
    """
    # Preferred: resources.library-songs can be a dict keyed by id
    resources = data.get("resources", {})
    lib_songs = resources.get("library-songs")
    if isinstance(lib_songs, dict):
        return list(lib_songs.values())
    if isinstance(lib_songs, list):
        return lib_songs

    # Fallback: included array with mixed types
    included = data.get("included", [])
    if included:
        return [item for item in included if item.get("type") == "library-songs"]

    # Last resort: top-level key
    top = data.get("library-songs")
    if isinstance(top, dict):
        return list(top.values())
    if isinstance(top, list):
        return top
    return []


def main() -> None:
    data = json.loads(PLAYLIST_JSON.read_text(encoding="utf-8"))
    songs = _extract_songs(data)
    rows = []
    for item in songs:
        attrs = item.get("attributes", {})
        params = attrs.get("playParams", {})
        rows.append(
            [
                params.get("catalogId", ""),
                params.get("id", ""),
                attrs.get("name", ""),
                attrs.get("artistName", ""),
                attrs.get("albumName", ""),
                attrs.get("contentRating", ""),
                str(bool(attrs.get("hasLyrics", False))).lower(),
            ]
        )

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

if __name__ == "__main__":
    main()
