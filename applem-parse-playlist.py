# -*- coding: utf-8 -*-
"""Parse Apple Music playlist JSON and output a CSV with song details."""

import csv
import json
from pathlib import Path

PLAYLIST_JSON = Path("playlist.json")
OUTPUT_CSV = Path("playlist.csv")

FIELDNAMES = [
    "catalogId",
    "songId",
    "song name",
    "artistName",
    "albumName",
    "contentRating",
    "hasLyrics",
]

def main() -> None:
    data = json.loads(PLAYLIST_JSON.read_text(encoding="utf-8"))
    songs = data.get("library-songs", [])
    rows = []
    for item in songs:
        attrs = item.get("attributes", {})
        params = attrs.get("playParams", {})
        rows.append({
            "catalogId": params.get("catalogId", ""),
            "songId": params.get("id", ""),
            "song name": attrs.get("name", ""),
            "artistName": attrs.get("artistName", ""),
            "albumName": attrs.get("albumName", ""),
            "contentRating": attrs.get("contentRating", ""),
            "hasLyrics": str(bool(attrs.get("hasLyrics", False))).lower(),
        })

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    main()
