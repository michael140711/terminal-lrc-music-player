# -*- coding: utf-8 -*-
"""Fetch syllable lyrics for songs listed in ``playlist.csv``."""

import asyncio
import csv
import json
import random
from pathlib import Path

from playwright.async_api import async_playwright

MUSIC_HOME = "https://music.apple.com/"
LYRIC_API = "https://amp-api.music.apple.com/v1/catalog/us/songs/{}/syllable-lyrics"

CSV_FILE = Path("applem-tools/playlist.csv")
LYRICS_DIR = Path("lyrics-ttml-json")
DELAY_SECONDS_MIN = 3
DELAY_SECONDS_MAX = 20

STATE_FILE = Path("applem-tools/state.json")
use_persistent_context = False
USER_DATA_DIR = "user-data"

GET_TOKENS_JS = """
() => {
  try {
    if (window.MusicKit && MusicKit.getInstance) {
      const mk = MusicKit.getInstance();
      return {
        developerToken: mk?.developerToken || null,
        musicUserToken: mk?.musicUserToken || null
      };
    }
    return { developerToken: null, musicUserToken: null };
  } catch (_) {
    return { developerToken: null, musicUserToken: null };
  }
}
"""

FETCH_JSON_JS = """
async ({ url, devToken, userToken }) => {
  const res = await fetch(url, {
    method: "GET",
    headers: {
      "Accept": "*/*",
      "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
      "Authorization": `Bearer ${devToken}`,
      "media-user-token": userToken,
      "Origin": "https://music.apple.com",
      "Referer": "https://music.apple.com/"
    },
    mode: "cors",
    credentials: "include"
  });
  const text = await res.text();
  let parsed;
  try { parsed = JSON.parse(text); } catch { parsed = { raw: text }; }
  return { status: res.status, ok: res.ok, url: res.url, data: parsed };
}
"""

async def pause_for_login() -> None:
    print("\n== Manual login required ==")
    print("1) Sign in to Apple Music in the opened browser window.")
    print("2) After successful login return here and press ENTER.")
    await asyncio.get_event_loop().run_in_executor(None, input, "Press ENTER to continue: ")

async def get_tokens_with_retry(page, attempts: int = 6, delay_ms: int = 1500):
    for i in range(1, attempts + 1):
        print("Waiting for Chrome, or user login... (10s)")
        await page.wait_for_timeout(10000)
        tokens = await page.evaluate(GET_TOKENS_JS)
        dev, usr = tokens.get("developerToken"), tokens.get("musicUserToken")
        if dev and usr:
            return dev, usr
        if i < attempts:
            print(f"Tokens not ready (attempt {i}/{attempts-1}). Waiting...")
            await page.wait_for_timeout(delay_ms)
    return None, None

def sanitize_filename(name: str) -> str:
    return "".join(c for c in name if c not in '\\/:*?"<>|').strip()

async def main() -> None:
    # Read CSV: we expect columns like
    # 0: catalogId (numeric), 1: unknown, 2: song name, 3: artist, 4: album, 5: content rating ('explicit' or blank)
    rows = []
    if CSV_FILE.exists():
        with CSV_FILE.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                # If there's an accidental header, skip non-numeric first column
                first = (row[0] or "").strip()
                if not first.isdigit():
                    continue
                rows.append(row)
    else:
        print(f"{CSV_FILE} not found")
        return

    async with async_playwright() as p:
        if use_persistent_context:
            context = await p.chromium.launch_persistent_context(USER_DATA_DIR, headless=False)
            page = await context.new_page()
        else:
            browser = await p.chromium.launch(headless=False)
            if STATE_FILE.exists():
                context = await browser.new_context(storage_state=str(STATE_FILE))
            else:
                context = await browser.new_context()
            page = await context.new_page()

        await page.goto(MUSIC_HOME, wait_until="domcontentloaded")

        if not use_persistent_context and not STATE_FILE.exists():
            await pause_for_login()
            await context.storage_state(path=str(STATE_FILE))
            print(f"Saved login state to {STATE_FILE}")

        dev_token, user_token = await get_tokens_with_retry(page)
        if not dev_token or not user_token:
            print("Tokens missing; try interacting with the site then retry.")
            await page.wait_for_timeout(2000)
            dev_token, user_token = await get_tokens_with_retry(page, attempts=3, delay_ms=2000)
        if not dev_token or not user_token:
            raise RuntimeError("Failed to acquire MusicKit tokens.")

        LYRICS_DIR.mkdir(parents=True, exist_ok=True)
        for row in rows:
            try:
                catalog_id = (row[0] or "").strip()
                song_name = (row[2] if len(row) > 2 else "").strip()
                artist_name = (row[3] if len(row) > 3 else "").strip()
                content_col = (row[5] if len(row) > 5 else "").strip()
                is_explicit = content_col.lower() == "explicit"

                if not catalog_id:
                    print("Skipping row with missing catalog id:", row)
                    continue

                url = LYRIC_API.format(catalog_id)

                await asyncio.sleep(random.randint(DELAY_SECONDS_MIN, DELAY_SECONDS_MAX))

                print(f"Fetching: {song_name} - {artist_name} | {url}")
                final = await page.evaluate(
                    FETCH_JSON_JS,
                    {"url": url, "devToken": dev_token, "userToken": user_token},
                )

                # Build filename as "{3rd column} - {4th column}" with optional "(Explicit)"
                base_name = f"{song_name} - {artist_name}"
                if is_explicit:
                    base_name += " (Explicit)"
                fname = f"{base_name}.json"

                file_path = LYRICS_DIR / sanitize_filename(fname)
                file_path.write_text(
                    json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                status = final.get("status")
                print(f"Saved {file_path} (status={status})")
            except Exception as e:
                print("Error processing row:", row)
                print(e)

        if not use_persistent_context:
            await browser.close()
        else:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
