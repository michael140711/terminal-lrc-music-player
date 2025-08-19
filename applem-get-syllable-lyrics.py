# -*- coding: utf-8 -*-
# Async Playwright: reuse login (storage_state or persistent context) -> final GET only -> save response.json
# 中英双语注释 / Bilingual comments

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

MUSIC_HOME = "https://music.apple.com/"
FINAL_URL  = "https://amp-api.music.apple.com/v1/catalog/us/songs/1446918510/syllable-lyrics"

STATE_FILE = Path("state.json")
use_persistent_context = False  # 若想用持久化上下文改 True；If you prefer persistent context, set True
USER_DATA_DIR = "user-data"     # 持久化上下文的用户数据目录 / user profile dir for persistent context

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

async def pause_for_login():
    print("\n== 手动登录 / Manual login ==")
    print("1) 在弹出的浏览器里登录 Apple Music。Sign in on the Apple Music page.")
    print("2) 登录成功后回到终端按回车。Press ENTER here after you’re signed in.")
    await asyncio.get_event_loop().run_in_executor(None, input, "Press ENTER / 回车继续：")

async def get_tokens_with_retry(page, attempts=6, delay_ms=1500):
    for i in range(1, attempts + 1):
        t = await page.evaluate(GET_TOKENS_JS)
        dev, usr = t.get("developerToken"), t.get("musicUserToken")
        if dev and usr:
            return dev, usr
        if i < attempts:
            print(f"Tokens not ready (try {i}/{attempts-1}). 令牌未就绪，等待中…")
            await page.wait_for_timeout(delay_ms)
    return None, None

async def main():
    async with async_playwright() as p:
        if use_persistent_context:
            # 方案 B：持久化上下文 / Persistent context
            context = await p.chromium.launch_persistent_context(
                USER_DATA_DIR, headless=False
            )
            page = await context.new_page()
        else:
            # 方案 A：storage_state
            browser = await p.chromium.launch(headless=False)
            if STATE_FILE.exists():
                context = await browser.new_context(storage_state=str(STATE_FILE))
            else:
                context = await browser.new_context()
            page = await context.new_page()

        # 打开站点 / Open site
        await page.goto(MUSIC_HOME, wait_until="domcontentloaded")

        # 如果没有 state，先登录并保存 / If no state yet, login and save
        if not use_persistent_context and not STATE_FILE.exists():
            await pause_for_login()
            # 保存 cookies & storage / Save authenticated state
            await context.storage_state(path=str(STATE_FILE))
            print(f"✅ Saved login state to {STATE_FILE} .")

        # 获取 MusicKit 令牌 / Get tokens
        dev_token, user_token = await get_tokens_with_retry(page)
        if not dev_token or not user_token:
            print("Try opening an album/track on the page to initialize MusicKit, then retry.")
            await page.wait_for_timeout(2000)
            dev_token, user_token = await get_tokens_with_retry(page, attempts=3, delay_ms=2000)
        if not dev_token or not user_token:
            raise RuntimeError("Failed to obtain MusicKit tokens. 无法获取 MusicKit 令牌。")

        print("✅ Tokens acquired / 已获取令牌：")
        print(f"- developerToken: {dev_token[:20]}... (truncated)")
        print(f"- musicUserToken: {user_token[:20]}... (truncated)")

        # 直接请求最终 URL（浏览器会在幕后自动做 CORS 预检）
        final = await page.evaluate(FETCH_JSON_JS, {
            "url": FINAL_URL,
            "devToken": dev_token,
            "userToken": user_token
        })
        print(f"Final GET status: {final['status']} ok={final['ok']} URL={final['url']}")

        # 保存响应 / Save response
        Path("response.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        print("✅ Saved to response.json / 已保存响应到 response.json")

        # 清理 / Cleanup
        if not use_persistent_context:
            await browser.close()
        else:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
