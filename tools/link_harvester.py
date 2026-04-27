#!/usr/bin/env python3
"""Harvest WeChat article links from saved pages or text files."""

from __future__ import annotations

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
LINKS_FILE = ROOT / "gongzhonghao.json"
DEFAULT_SOURCES = [ROOT / "raw" / "html", ROOT / "raw" / "text", ROOT / "link_sources"]
ARTICLE_PATTERNS = [
    re.compile(r"https?://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+"),
    re.compile(r"https?://mp\.weixin\.qq\.com/s\?[^\"'<>\s\\]+"),
]
ALBUM_PATTERN = re.compile(r"https?://mp\.weixin\.qq\.com/mp/appmsgalbum\?[^\"'<>\s\\]+")


class SavedPageLinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.visible_text: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        for key, value in attrs:
            if value and key.lower() in {"href", "data-link", "data-url"}:
                self.hrefs.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and "mp.weixin.qq.com" in data:
            self.visible_text.append(data)

    def searchable_text(self) -> str:
        return "\n".join(self.hrefs + self.visible_text)


def read_existing_links() -> list[str]:
    if not LINKS_FILE.exists():
        return []
    with LINKS_FILE.open("r", encoding="utf-8") as fh:
        links = json.load(fh)
    if not isinstance(links, list):
        raise ValueError(f"{LINKS_FILE} must contain a JSON array")
    return [item for item in links if isinstance(item, str)]


def write_links(links: list[str]) -> None:
    LINKS_FILE.write_text(json.dumps(links, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_source_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in {".html", ".htm", ".txt", ".md", ".json"}
            )
        elif path.is_file():
            files.append(path)
    return sorted(set(files))


def clean_url(raw_url: str) -> str | None:
    url = html.unescape(unquote(raw_url)).strip().rstrip(".,;，。；)")
    if "${" in url:
        return None
    parsed = urlparse(url)
    scheme = "https"
    netloc = "mp.weixin.qq.com"
    path = parsed.path

    if path.startswith("/s/"):
        slug = path.rstrip("/").split("/")[-1]
        return urlunparse((scheme, netloc, f"/s/{quote(slug)}", "", "", ""))

    if path == "/s":
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        required = ("__biz", "mid", "idx", "sn")
        if all(query.get(key) for key in required):
            query_text = "&".join(f"{key}={quote(query[key], safe='')}" for key in required)
            return urlunparse((scheme, netloc, "/s", "", query_text, ""))
        return None

    return url


def extract_links_from_text(text: str) -> tuple[set[str], set[str]]:
    decoded = html.unescape(unquote(text))
    articles: set[str] = set()
    albums: set[str] = set()
    for pattern in ARTICLE_PATTERNS:
        for match in pattern.findall(decoded):
            url = clean_url(match)
            if url and "__biz=&" not in url:
                articles.add(url)
    for match in ALBUM_PATTERN.findall(decoded):
        url = html.unescape(unquote(match)).strip().rstrip(".,;，。；)")
        if "__biz=" in url:
            albums.add(url)
    return articles, albums


def harvest(paths: list[Path], merge: bool) -> None:
    source_files = iter_source_files(paths)
    article_links: set[str] = set()
    album_links: set[str] = set()
    for path in source_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() in {".html", ".htm"}:
            _, raw_albums = extract_links_from_text(text)
            album_links.update(raw_albums)
            parser = SavedPageLinkExtractor()
            parser.feed(text)
            text = parser.searchable_text()
        articles, albums = extract_links_from_text(text)
        article_links.update(articles)
        album_links.update(albums)

    existing = read_existing_links()
    existing_set = set(existing)
    new_links = [link for link in sorted(article_links) if link not in existing_set]

    print(f"Scanned files: {len(source_files)}")
    print(f"Article links found: {len(article_links)}")
    print(f"New article links: {len(new_links)}")
    if new_links:
        for link in new_links:
            print(f"+ {link}")

    if album_links:
        print("\nAlbum/profile-like entry points found:")
        for link in sorted(album_links):
            print(f"* {link}")

    if merge and new_links:
        write_links(existing + new_links)
        print(f"\nUpdated {LINKS_FILE.relative_to(ROOT)}: {len(existing)} -> {len(existing) + len(new_links)} links")
    elif merge:
        print(f"\nNo new links to merge into {LINKS_FILE.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest WeChat article links from saved HTML/text.")
    parser.add_argument("paths", nargs="*", type=Path, help="Files or folders to scan. Defaults to raw/html raw/text link_sources.")
    parser.add_argument("--merge", action="store_true", help="Append new article links to gongzhonghao.json.")
    args = parser.parse_args()

    paths = [path if path.is_absolute() else ROOT / path for path in args.paths] if args.paths else DEFAULT_SOURCES
    harvest(paths, merge=args.merge)


if __name__ == "__main__":
    main()
