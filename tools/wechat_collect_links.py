#!/usr/bin/env python3
"""Collect WeChat article links from album/profile/search pages in a browser."""

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

from article_workflow import ROOT
from link_harvester import DEFAULT_SOURCES, extract_links_from_text, iter_source_files, read_existing_links, write_links
from wechat_auto_export import PROFILE_DIR, require_playwright


DISCOVERED_FILE = ROOT / "data" / "discovered_links.json"


COLLECT_SCRIPT = r"""
() => {
  const values = [];
  const push = (value) => { if (value) values.push(value); };
  document.querySelectorAll('a[href]').forEach((node) => push(node.href));
  document.querySelectorAll('[data-link]').forEach((node) => push(node.getAttribute('data-link')));
  document.querySelectorAll('[data-url]').forEach((node) => push(node.getAttribute('data-url')));
  push(document.body ? document.body.innerText : '');
  return values.join('\n');
}
"""


def default_entrypoints() -> list[str]:
    entrypoints: set[str] = set()
    for path in iter_source_files(DEFAULT_SOURCES):
        if path.suffix.lower() not in {".html", ".htm", ".txt", ".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        _, albums = extract_links_from_text(text)
        entrypoints.update(albums)
    return sorted(entrypoints)


def collect_links(urls: list[str], auto_scroll_rounds: int, manual_pause: bool, merge: bool) -> list[str]:
    sync_playwright = require_playwright()
    existing = read_existing_links()
    existing_set = set(existing)
    discovered: set[str] = set()
    network_texts: list[str] = []

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.on("response", lambda response: network_texts.append(response.url))

        for url in urls:
            print(f"\nOpening link source: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                print(f"Navigation warning: {exc}")

            for _ in range(auto_scroll_rounds):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.2)

            if manual_pause:
                print("Scroll/click in the browser until the article list is loaded, then press Enter here.")
                input()

            page_text = page.evaluate(COLLECT_SCRIPT)
            articles, _ = extract_links_from_text(page_text + "\n" + "\n".join(network_texts))
            discovered.update(articles)

        context.close()

    new_links = sorted(link for link in discovered if link not in existing_set)
    DISCOVERED_FILE.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERED_FILE.write_text(
        json.dumps({"all_discovered": sorted(discovered), "new_links": new_links}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\nDiscovered article links: {len(discovered)}")
    print(f"New article links: {len(new_links)}")
    for link in new_links:
        print(f"+ {link}")

    if merge and new_links:
        write_links(existing + new_links)
        subprocess.run([sys.executable, str(ROOT / "tools" / "article_workflow.py"), "init"], check=False)
        print(f"\nMerged into gongzhonghao.json and refreshed manifest.")
    elif merge:
        print("\nNo new links to merge.")

    return new_links


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect article links from WeChat album/profile/search pages.")
    parser.add_argument("urls", nargs="*", help="Album/profile/search URLs. Defaults to entrypoints found in saved HTML.")
    parser.add_argument("--auto-scroll", type=int, default=8, help="Automatic scroll rounds before manual capture.")
    parser.add_argument("--no-pause", action="store_true", help="Do not wait for manual scrolling/clicking before capture.")
    parser.add_argument("--merge", action="store_true", help="Append discovered links to gongzhonghao.json.")
    args = parser.parse_args()

    urls = args.urls or default_entrypoints()
    if not urls:
        raise SystemExit("No entrypoint URLs found. Save a profile/album/search page or pass URLs explicitly.")
    collect_links(urls, auto_scroll_rounds=args.auto_scroll, manual_pause=not args.no_pause, merge=args.merge)


if __name__ == "__main__":
    main()
