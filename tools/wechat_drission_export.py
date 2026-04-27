#!/usr/bin/env python3
"""Semi-assisted WeChat article downloader powered by DrissionPage.

This uses a visible Chromium browser and a persistent user profile. It does not
attempt to bypass WeChat verification; when a verification/login page appears,
finish it in the browser and press Enter in the terminal.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from article_workflow import MANIFEST_FILE, ROOT, build_manifest, ingest_all, load_manifest


PROFILE_DIR = ROOT / ".browser_profile" / "drission_wechat"


CAPTURE_SCRIPT = r"""
return (() => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const content = document.querySelector('#js_content') || document.querySelector('.rich_media_content');
  const titleNode = document.querySelector('#activity-name') || document.querySelector('h1');
  const accountNode = document.querySelector('#js_name') || document.querySelector('.profile_nickname');
  const dateNode = document.querySelector('#publish_time') || document.querySelector('#js_publish_time');
  const articleText = content ? content.innerText : '';
  const pageText = document.body ? document.body.innerText : '';
  const isVerifyPage = pageText.includes('环境异常')
    || pageText.includes('完成验证后即可继续访问')
    || pageText.includes('去验证')
    || pageText.includes('验证');
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
})();
"""

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def require_drission() -> tuple[Any, Any]:
    try:
        from DrissionPage import ChromiumOptions, ChromiumPage
    except Exception as exc:
        raise SystemExit(
            "DrissionPage is not installed. Run:\n"
            "python3 -m venv .venv\n"
            ".venv/bin/python -m pip install DrissionPage\n"
            ".venv/bin/python tools/wechat_drission_export.py"
        ) from exc
    return ChromiumOptions, ChromiumPage


def find_browser_path(explicit_path: str | None) -> str | None:
    if explicit_path:
        return explicit_path
    candidates = [
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    return next((path for path in candidates if path and Path(path).exists()), None)


def safe_filename_part(value: str, fallback: str) -> str:
    value = INVALID_FILENAME_CHARS.sub("-", value.strip())
    value = re.sub(r"\s+", " ", value).strip(" .-_")
    return value[:80] or fallback


def date_for_filename(value: str) -> str:
    match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(\d{1,2}):(\d{1,2}))?", value or "")
    if match:
        year, month, day, hour, minute = match.groups()
        prefix = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return f"{prefix}-{int(hour):02d}{int(minute):02d}" if hour and minute else prefix
    match = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?:[ T](\d{1,2}):(\d{1,2}))?", value or "")
    if match:
        year, month, day, hour, minute = match.groups()
        prefix = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return f"{prefix}-{int(hour):02d}{int(minute):02d}" if hour and minute else prefix
    return "unknown-date"


def title_paths(record: dict[str, Any], capture: dict[str, Any]) -> tuple[Path, Path]:
    current_html = ROOT / record["raw_html"]
    current_text = ROOT / record["raw_text"]
    if not re.match(r"A\d{3}", current_html.name) and not re.match(r"A\d{3}", current_text.name):
        return current_html, current_text

    date = date_for_filename(str(capture.get("published_at") or ""))
    title = safe_filename_part(str(capture.get("title") or ""), str(record.get("article_id") or "article"))
    base = f"{date}-{title}"
    html_path = ROOT / "raw" / "html" / f"{base}.html"
    text_path = ROOT / "raw" / "text" / f"{base}.txt"
    index = 2
    while (html_path.exists() and html_path != current_html) or (text_path.exists() and text_path != current_text):
        html_path = ROOT / "raw" / "html" / f"{base}-{index}.html"
        text_path = ROOT / "raw" / "text" / f"{base}-{index}.txt"
        index += 1
    return html_path, text_path


def save_capture(record: dict[str, Any], capture: dict[str, Any]) -> None:
    html_path, text_path = title_paths(record, capture)
    record["raw_html"] = str(html_path.relative_to(ROOT))
    record["raw_text"] = str(text_path.relative_to(ROOT))
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


def page_capture(page: Any) -> dict[str, Any] | None:
    try:
        capture = page.run_js(CAPTURE_SCRIPT, timeout=10)
    except Exception:
        return None
    return capture if isinstance(capture, dict) else None


def wait_for_article(page: Any, record: dict[str, Any], timeout_seconds: int, interactive: bool) -> dict[str, Any] | None:
    deadline = time.time() + timeout_seconds
    prompted = False
    last_capture: dict[str, Any] | None = None

    while time.time() < deadline:
        capture = page_capture(page)
        if capture:
            last_capture = capture
            if capture.get("is_article"):
                return capture
            if capture.get("is_verify_page") and interactive and not prompted:
                print(f"\n{record['article_id']} needs human verification/login in Chromium.")
                print("Finish it in the browser window, then press Enter here.")
                input()
                prompted = True
                deadline = time.time() + timeout_seconds
        time.sleep(1.5)

    return last_capture if last_capture and last_capture.get("is_article") else None


def open_page(browser_path: str | None, user_data_path: Path, port: int) -> Any:
    ChromiumOptions, ChromiumPage = require_drission()
    options = ChromiumOptions()
    options.headless(False)
    options.set_local_port(port)
    options.set_user_data_path(str(user_data_path))
    resolved_browser = find_browser_path(browser_path)
    if resolved_browser:
        options.set_browser_path(resolved_browser)
    options.set_argument("--window-size", "1280,900")
    options.set_argument("--disable-notifications")
    return ChromiumPage(options)


def export_articles(
    limit: int | None,
    timeout_seconds: int,
    interactive: bool,
    update_manual: bool,
    refresh_manifest: bool,
    browser_path: str | None,
    port: int,
    delay_seconds: float,
    force: bool,
) -> int:
    if refresh_manifest:
        build_manifest()
    manifest = load_manifest()
    pending = manifest if force else [item for item in manifest if item["status"] != "ingested"]
    if limit:
        pending = pending[:limit]
    if not pending:
        ingested = sum(1 for item in manifest if item["status"] == "ingested")
        print("No pending articles.")
        print(f"Manifest articles: {len(manifest)} total, {ingested} ingested, {len(manifest) - ingested} pending.")
        print("To re-download existing articles, run with --force.")
        print("To add new articles, update gongzhonghao.json, then run with --refresh-manifest.")
        return 0

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    page = open_page(browser_path, PROFILE_DIR, port)
    exported = 0

    try:
        for record in pending:
            print(f"\nOpening {record['article_id']}: {record['url']}")
            try:
                page.get(record["url"], timeout=timeout_seconds)
            except Exception as exc:
                print(f"Navigation warning for {record['article_id']}: {exc}")

            capture = wait_for_article(page, record, timeout_seconds, interactive)
            if capture:
                save_capture(record, capture)
                exported += 1
                print(f"Saved {record['article_id']}: {capture.get('title') or 'untitled'}")
            else:
                print(f"Skipped {record['article_id']}: article content was not available.")
            if delay_seconds > 0:
                time.sleep(delay_seconds)
    finally:
        try:
            page.quit(timeout=5, force=False)
        except Exception:
            pass

    if exported:
        MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ingest_all()
        if update_manual:
            subprocess.run([sys.executable, str(ROOT / "tools" / "article_workflow.py"), "manual"], check=False)

    print(f"\nExported {exported}/{len(pending)} attempted articles.")
    return exported


def main() -> None:
    parser = argparse.ArgumentParser(description="Semi-assisted WeChat article export via DrissionPage.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N pending articles.")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds to wait for each article.")
    parser.add_argument("--no-interactive", action="store_true", help="Do not pause for verification.")
    parser.add_argument("--no-manual", action="store_true", help="Do not regenerate the manual after export.")
    parser.add_argument("--refresh-manifest", action="store_true", help="Rebuild manifest from gongzhonghao.json first.")
    parser.add_argument("--browser-path", default=None, help="Optional explicit Chromium/Chrome executable path.")
    parser.add_argument("--port", type=int, default=9223, help="Local Chrome debugging port for DrissionPage.")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between articles.")
    parser.add_argument("--force", action="store_true", help="Re-download all manifest articles, including already ingested ones.")
    args = parser.parse_args()

    export_articles(
        limit=args.limit,
        timeout_seconds=args.timeout,
        interactive=not args.no_interactive,
        update_manual=not args.no_manual,
        refresh_manifest=args.refresh_manifest,
        browser_path=args.browser_path,
        port=args.port,
        delay_seconds=args.delay,
        force=args.force,
    )


if __name__ == "__main__":
    main()
