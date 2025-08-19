# -*- coding: utf-8 -*-
"""Parse Apple Music playlist JSON and output a CSV with song details."""

import csv
import json
from pathlib import Path

PLAYLIST_JSON = Path("playlist.json")
OUTPUT_CSV = Path("playlist.csv")

def _extract_songs(data: dict) -> list:
    """Return song entries from the playlist JSON."""
    if "library-songs" in data:
        return data["library-songs"]
    return [
        item
        for item in data.get("included", [])
        if item.get("type") == "library-songs"
    ]


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
