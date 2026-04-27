#!/usr/bin/env python3
"""Semi-assisted WeChat article downloader using a real browser session.

The script does not bypass WeChat verification. It opens every pending article
in a visible Chromium window, waits for a normal article page, saves the DOM and
visible text, and pauses for human help if WeChat shows a verification page.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from article_workflow import ROOT, build_manifest, ingest_all, load_manifest


PROFILE_DIR = ROOT / ".browser_profile" / "wechat"


CAPTURE_SCRIPT = r"""
() => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const content = document.querySelector('#js_content') || document.querySelector('.rich_media_content');
  const titleNode = document.querySelector('#activity-name') || document.querySelector('h1');
  const accountNode = document.querySelector('#js_name') || document.querySelector('.profile_nickname');
  const dateNode = document.querySelector('#publish_time') || document.querySelector('#js_publish_time');
  const articleText = content ? content.innerText : '';
  const pageText = document.body ? document.body.innerText : '';
  const isVerifyPage = pageText.includes('环境异常') || pageText.includes('完成验证后即可继续访问') || pageText.includes('去验证');
  return {
    url: location.href,
    title: clean(titleNode && titleNode.innerText),
    account: clean(accountNode && accountNode.innerText),
    published_at: clean(dateNode && dateNode.innerText),
    article_text: articleText.trim(),
    page_text: pageText.trim(),
    html: document.documentElement.outerHTML,
    is_article: Boolean(content && articleText.trim().length > 200),
    is_verify_page: isVerifyPage,
  };
}
"""


def require_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(
            "Playwright is not available. Install it with: python3 -m pip install playwright && python3 -m playwright install chromium"
        ) from exc
    return sync_playwright


def save_capture(record: dict[str, Any], capture: dict[str, Any]) -> None:
    html_path = ROOT / record["raw_html"]
    text_path = ROOT / record["raw_text"]
    html_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(capture["html"], encoding="utf-8")
    header = [
        f"标题：{capture.get('title') or ''}",
        f"公众号：{capture.get('account') or ''}",
        f"日期：{capture.get('published_at') or ''}",
        f"原文：{record['url']}",
        "",
    ]
    text_path.write_text("\n".join(header) + capture["article_text"].strip() + "\n", encoding="utf-8")


def wait_for_article(page: Any, record: dict[str, Any], timeout_seconds: int, interactive: bool) -> dict[str, Any] | None:
    deadline = time.time() + timeout_seconds
    last_capture: dict[str, Any] | None = None
    prompted = False
    while time.time() < deadline:
        capture = page.evaluate(CAPTURE_SCRIPT)
        last_capture = capture
        if capture["is_article"]:
            return capture
        if capture["is_verify_page"] and interactive and not prompted:
            print(f"\n{record['article_id']} needs human verification in the browser.")
            print("Finish WeChat verification/login in the opened browser window, then press Enter here.")
            input()
            prompted = True
            deadline = time.time() + timeout_seconds
        time.sleep(1.5)
    return last_capture if last_capture and last_capture.get("is_article") else None


def export_articles(limit: int | None, timeout_seconds: int, interactive: bool, update_manual: bool) -> int:
    sync_playwright = require_playwright()
    build_manifest()
    manifest = load_manifest()
    pending = [item for item in manifest if item["status"] != "ingested"]
    if limit:
        pending = pending[:limit]
    if not pending:
        print("No pending articles.")
        return 0

    exported = 0
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        for record in pending:
            print(f"\nOpening {record['article_id']}: {record['url']}")
            try:
                page.goto(record["url"], wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            except Exception as exc:
                print(f"Navigation warning for {record['article_id']}: {exc}")
            capture = wait_for_article(page, record, timeout_seconds, interactive)
            if capture:
                save_capture(record, capture)
                exported += 1
                print(f"Saved {record['article_id']}: {capture.get('title') or 'untitled'}")
            else:
                print(f"Skipped {record['article_id']}: article content was not available.")
        context.close()

    if exported:
        ingest_all()
        if update_manual:
            subprocess.run([sys.executable, str(ROOT / "tools" / "article_workflow.py"), "manual"], check=False)
    print(f"\nExported {exported}/{len(pending)} attempted articles.")
    return exported


def main() -> None:
    parser = argparse.ArgumentParser(description="Semi-assisted WeChat article export.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N pending articles.")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds to wait for each article.")
    parser.add_argument("--no-interactive", action="store_true", help="Do not pause for verification.")
    parser.add_argument("--no-manual", action="store_true", help="Do not regenerate the manual after export.")
    args = parser.parse_args()

    export_articles(
        limit=args.limit,
        timeout_seconds=args.timeout,
        interactive=not args.no_interactive,
        update_manual=not args.no_manual,
    )


if __name__ == "__main__":
    main()
