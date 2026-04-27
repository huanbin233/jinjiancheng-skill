#!/usr/bin/env python3
"""Collect WeChat article links with DrissionPage, then optionally download them.

Known article URLs do not need scrolling: the downloader opens them one by one.
Scrolling is only needed on source pages such as albums, profile/history pages,
or search result pages because WeChat often lazy-loads those article links.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from article_workflow import ROOT, build_manifest, load_manifest
from link_harvester import DEFAULT_SOURCES, extract_links_from_text, iter_source_files, read_existing_links, write_links
from wechat_drission_export import PROFILE_DIR, export_articles, open_page


DISCOVERED_FILE = ROOT / "data" / "discovered_links.json"


COLLECT_SCRIPT = r"""
return (() => {
  const values = [];
  const push = (value) => { if (value) values.push(String(value)); };
  document.querySelectorAll('a[href]').forEach((node) => push(node.href));
  document.querySelectorAll('[data-link]').forEach((node) => push(node.getAttribute('data-link')));
  document.querySelectorAll('[data-url]').forEach((node) => push(node.getAttribute('data-url')));
  const bodyText = document.body ? document.body.innerText : '';
  const html = document.documentElement ? document.documentElement.outerHTML : '';
  push(bodyText);
  const isVerifyPage = bodyText.includes('环境异常')
    || bodyText.includes('完成验证后即可继续访问')
    || bodyText.includes('去验证')
    || bodyText.includes('验证');
  return {
    text: values.join('\n'),
    html,
    body_text_length: bodyText.length,
    scroll_height: document.documentElement.scrollHeight || document.body.scrollHeight || 0,
    scroll_y: window.scrollY || window.pageYOffset || 0,
    link_count: document.querySelectorAll('a[href], [data-link], [data-url]').length,
    is_verify_page: isVerifyPage,
  };
})();
"""


CLICK_MORE_SCRIPT = r"""
return (() => {
  const words = ['加载更多', '查看更多', '更多文章', '更多'];
  const nodes = Array.from(document.querySelectorAll('button, a, div, span'))
    .filter((node) => {
      const text = (node.innerText || '').replace(/\s+/g, '');
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && words.some((word) => text.includes(word));
    });
  const node = nodes[nodes.length - 1];
  if (!node) return '';
  const text = (node.innerText || node.getAttribute('aria-label') || '').trim();
  node.click();
  return text || 'clicked';
})();
"""


def article_key(url: str) -> str:
    if "/s/" in url:
        return url.rstrip("/").split("/s/", 1)[1].split("?", 1)[0]
    if "__biz=" in url and "mid=" in url:
        return url
    return url


def merge_links(existing: list[str], new_links: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for link in existing + new_links:
        key = article_key(link)
        if key in seen:
            continue
        seen.add(key)
        merged.append(link)
    return merged


def default_entrypoints() -> list[str]:
    entrypoints: set[str] = set()
    for path in iter_source_files(DEFAULT_SOURCES):
        if path.suffix.lower() not in {".html", ".htm", ".txt", ".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        _, albums = extract_links_from_text(text)
        entrypoints.update(albums)
    return sorted(entrypoints)


def manifest_links() -> list[str]:
    try:
        return [item["url"] for item in load_manifest()]
    except Exception:
        return []


def run_js_dict(page: Any, script: str) -> dict[str, Any]:
    result = page.run_js(script, timeout=10)
    return result if isinstance(result, dict) else {}


def maybe_handle_verification(page: Any, interactive: bool, timeout_seconds: int) -> None:
    capture = run_js_dict(page, COLLECT_SCRIPT)
    if capture.get("is_verify_page") and interactive:
        print("This source page needs human verification/login in Chromium.")
        print("Finish it in the browser window, then press Enter here.")
        input()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            capture = run_js_dict(page, COLLECT_SCRIPT)
            if not capture.get("is_verify_page"):
                return
            time.sleep(1.5)


def auto_scroll_collect(
    page: Any,
    max_rounds: int,
    stable_rounds: int,
    wait_seconds: float,
    click_more: bool,
    interactive: bool,
    timeout_seconds: int,
) -> set[str]:
    discovered: set[str] = set()
    stable_count = 0
    last_signature: tuple[int, int, int] | None = None

    maybe_handle_verification(page, interactive=interactive, timeout_seconds=timeout_seconds)

    for round_no in range(1, max_rounds + 1):
        capture = run_js_dict(page, COLLECT_SCRIPT)
        text = f"{capture.get('text', '')}\n{capture.get('html', '')}"
        articles, _ = extract_links_from_text(text)
        before_count = len(discovered)
        discovered.update(articles)

        signature = (
            int(capture.get("scroll_height") or 0),
            int(capture.get("body_text_length") or 0),
            len(discovered),
        )
        new_count = len(discovered) - before_count
        print(
            f"Scroll round {round_no}: links={len(discovered)}"
            f" (+{new_count}), height={signature[0]}, text={signature[1]}"
        )

        if signature == last_signature:
            stable_count += 1
        else:
            stable_count = 0
        if stable_count >= stable_rounds:
            print("Page looks stable; stopping auto-scroll.")
            break
        last_signature = signature

        if click_more:
            clicked = page.run_js(CLICK_MORE_SCRIPT, timeout=5)
            if clicked:
                print(f"Clicked possible load-more control: {clicked}")
                time.sleep(wait_seconds)

        page.run_js("window.scrollTo(0, document.documentElement.scrollHeight || document.body.scrollHeight);")
        time.sleep(wait_seconds)

    return discovered


def collect_links(
    urls: list[str],
    merge: bool,
    download: bool,
    browser_path: str | None,
    port: int,
    max_rounds: int,
    stable_rounds: int,
    wait_seconds: float,
    click_more: bool,
    interactive: bool,
    timeout_seconds: int,
    delay_seconds: float,
) -> list[str]:
    existing = read_existing_links()
    existing_set = set(existing)
    existing_with_manifest = merge_links(existing, manifest_links())
    existing_with_manifest_set = set(existing_with_manifest)
    discovered: set[str] = set()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    page = open_page(browser_path, PROFILE_DIR, port)
    try:
        for url in urls:
            print(f"\nOpening link source: {url}")
            try:
                page.get(url, timeout=timeout_seconds)
            except Exception as exc:
                print(f"Navigation warning: {exc}")
            discovered.update(
                auto_scroll_collect(
                    page,
                    max_rounds=max_rounds,
                    stable_rounds=stable_rounds,
                    wait_seconds=wait_seconds,
                    click_more=click_more,
                    interactive=interactive,
                    timeout_seconds=timeout_seconds,
                )
            )
    finally:
        try:
            page.quit(timeout=5, force=False)
        except Exception:
            pass

    new_links = sorted(link for link in discovered if link not in existing_with_manifest_set)
    DISCOVERED_FILE.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERED_FILE.write_text(
        json.dumps(
            {
                "entrypoints": urls,
                "all_discovered": sorted(discovered),
                "new_links": new_links,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\nDiscovered article links: {len(discovered)}")
    print(f"New article links: {len(new_links)}")
    for link in new_links:
        print(f"+ {link}")

    if merge:
        merged_links = merge_links(existing_with_manifest, new_links)
        write_links(merged_links)
        build_manifest()
        print(f"\nUpdated gongzhonghao.json: {len(existing_set)} current -> {len(merged_links)} merged links")

    if download:
        if not merge:
            print("\nSkipping download because --download needs --merge to refresh the manifest safely.")
        else:
            export_articles(
                limit=None,
                timeout_seconds=timeout_seconds,
                interactive=interactive,
                update_manual=True,
                refresh_manifest=True,
                browser_path=browser_path,
                port=port,
                delay_seconds=delay_seconds,
                force=False,
            )

    return new_links


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-scroll source pages, collect WeChat article links, optionally download.")
    parser.add_argument("urls", nargs="*", help="Album/profile/search URLs. Defaults to entrypoints found in saved HTML.")
    parser.add_argument("--merge", action="store_true", help="Append discovered links to gongzhonghao.json.")
    parser.add_argument("--download", action="store_true", help="After merging, refresh manifest and download pending articles.")
    parser.add_argument("--max-rounds", type=int, default=40, help="Maximum auto-scroll rounds per source page.")
    parser.add_argument("--stable-rounds", type=int, default=3, help="Stop after this many unchanged scroll rounds.")
    parser.add_argument("--wait", type=float, default=1.5, help="Seconds to wait after each scroll.")
    parser.add_argument("--click-more", action="store_true", help="Also click visible load-more controls while scrolling.")
    parser.add_argument("--no-interactive", action="store_true", help="Do not pause for verification/login.")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds to wait for source/download pages.")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between downloaded articles.")
    parser.add_argument("--browser-path", default=None, help="Optional explicit Chromium/Chrome executable path.")
    parser.add_argument("--port", type=int, default=9223, help="Local Chrome debugging port for DrissionPage.")
    args = parser.parse_args()

    urls = args.urls or default_entrypoints()
    if not urls:
        raise SystemExit("No entrypoint URLs found. Save a profile/album/search page or pass URLs explicitly.")

    collect_links(
        urls=urls,
        merge=args.merge,
        download=args.download,
        browser_path=args.browser_path,
        port=args.port,
        max_rounds=args.max_rounds,
        stable_rounds=args.stable_rounds,
        wait_seconds=args.wait,
        click_more=args.click_more,
        interactive=not args.no_interactive,
        timeout_seconds=args.timeout,
        delay_seconds=args.delay,
    )


if __name__ == "__main__":
    main()
