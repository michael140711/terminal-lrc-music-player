# -*- coding: utf-8 -*-
"""Fetch Apple Music playlist JSON using Playwright.

This script opens Apple Music in a real browser so the user can sign in.
The authenticated cookies and localStorage are stored for future runs.
After obtaining `developerToken` and `musicUserToken` from MusicKit it
makes an authenticated request to the playlist endpoint and saves the
JSON response to ``playlist.json``. Tokens are also persisted to
``tokens.json`` for reuse.
"""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright

MUSIC_HOME = "https://music.apple.com/"
PLAYLIST_API = "https://amp-api.music.apple.com/v1/me/library/playlists/"

# query parameters required by Apple Music to fetch playlist resources
PLAYLIST_QUERY = {
    "art[library-music-videos:url]": "c,f",
    "art[url]": "f",
    "extend": "hasCollaboration,isCollaborativeHost",
    "extend[library-playlists]": "tags",
    "fields[music-videos]": "artistUrl,artwork,durationInMillis,url",
    "fields[songs]": "artistUrl,artwork,durationInMillis,url",
    "format[resources]": "map",
    "include": "catalog,artists,tracks",
    "include[library-playlists]": "catalog,tracks,playlists",
    "include[playlists]": "curator",
    "include[songs]": "artists",
    "l": "en-US",
    "omit[resource]": "autos",
    "platform": "web",
    "relate": "catalog",
}

STATE_FILE = Path("applem-tools/state.json")
TOKENS_FILE = Path("applem-tools/tokens.json")
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
    """Instruct the user to log in using the opened browser."""
    print("\n== Manual login required ==")
    print("1) Sign in to Apple Music in the opened browser window.")
    print("2) After successful login return here and press ENTER.")
    await asyncio.get_event_loop().run_in_executor(None, input, "Press ENTER to continue: ")

async def get_tokens_with_retry(page, attempts: int = 6, delay_ms: int = 15000):
    for i in range(1, attempts + 1):
        tokens = await page.evaluate(GET_TOKENS_JS)
        dev, usr = tokens.get("developerToken"), tokens.get("musicUserToken")
        if dev and usr:
            return dev, usr
        if i < attempts:
            print(f"Tokens not ready (attempt {i}/{attempts-1}). Waiting...")
            await page.wait_for_timeout(delay_ms)
    return None, None

async def main(playlist_id: str) -> None:
    # ensure prefix p. exists for library playlists
    if not playlist_id.startswith("p."):
        playlist_id = f"p.{playlist_id}"
    params = urlencode(PLAYLIST_QUERY)
    playlist_url = f"{PLAYLIST_API}{playlist_id}?{params}"

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

        TOKENS_FILE.write_text(
            json.dumps({"developerToken": dev_token, "musicUserToken": user_token}, indent=2),
            encoding="utf-8",
        )
        print(f"Saved tokens to {TOKENS_FILE}")

        final = await page.evaluate(
            FETCH_JSON_JS,
            {"url": playlist_url, "devToken": dev_token, "userToken": user_token},
        )
        Path("playlist.json").write_text(
            json.dumps(final.get("data"), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("Playlist response saved to playlist.json")

        if not use_persistent_context:
            await browser.close()
        else:
            await context.close()

if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else input("Enter playlist ID: ").strip()
    asyncio.run(main(pid))
