#!/usr/bin/env python3
"""Rename raw/article documents to date-title filenames."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_TEXT_DIR = ROOT / "raw" / "text"
RAW_HTML_DIR = ROOT / "raw" / "html"
ARTICLES_DIR = ROOT / "articles"
MANIFEST_FILE = ROOT / "data" / "links_manifest.json"
MAP_FILE = ROOT / "data" / "filename_map.json"


INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
SPACES = re.compile(r"\s+")


def safe_title(value: str, fallback: str) -> str:
    value = INVALID_CHARS.sub("-", value.strip())
    value = SPACES.sub(" ", value).strip(" .-_")
    return value[:80] or fallback


def parse_datetime(value: str) -> str:
    value = value.strip()
    match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(\d{1,2}):(\d{1,2}))?", value)
    if match:
        year, month, day, hour, minute = match.groups()
        prefix = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return f"{prefix}-{int(hour):02d}{int(minute):02d}" if hour and minute else prefix

    match = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?:[ T](\d{1,2}):(\d{1,2}))?", value)
    if match:
        year, month, day, hour, minute = match.groups()
        prefix = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return f"{prefix}-{int(hour):02d}{int(minute):02d}" if hour and minute else prefix

    return "unknown-date"


def header_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}：(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def metadata_from_text(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "title": header_value(text, "标题"),
        "date": header_value(text, "日期"),
        "url": header_value(text, "原文"),
    }


def metadata_from_article(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "title": str(data.get("title") or ""),
        "date": str(data.get("published_at") or ""),
        "url": str(data.get("url") or ""),
    }


def make_base(meta: dict[str, str], fallback: str) -> str:
    date = parse_datetime(meta.get("date", ""))
    title = safe_title(meta.get("title", ""), fallback)
    return f"{date}-{title}"


def unique_path(directory: Path, base: str, suffix: str, reserved: set[Path]) -> Path:
    candidate = directory / f"{base}{suffix}"
    index = 2
    while candidate in reserved or candidate.exists():
        candidate = directory / f"{base}-{index}{suffix}"
        index += 1
    reserved.add(candidate)
    return candidate


def load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_FILE.exists():
        return []
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def write_manifest(manifest: list[dict[str, Any]]) -> None:
    if manifest:
        MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def manifest_by_url(manifest: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("url")): item for item in manifest if item.get("url")}


def main() -> None:
    manifest = load_manifest()
    manifest_url_index = manifest_by_url(manifest)
    mapping: dict[str, str] = {}
    stem_to_base: dict[str, str] = {}
    url_to_base: dict[str, str] = {}
    reserved_by_dir: dict[Path, set[Path]] = {
        RAW_TEXT_DIR: set(),
        RAW_HTML_DIR: set(),
        ARTICLES_DIR: set(),
    }

    for path in sorted(RAW_TEXT_DIR.glob("*.txt")):
        meta = metadata_from_text(path)
        base = make_base(meta, path.stem)
        target = unique_path(path.parent, base, path.suffix, reserved_by_dir[path.parent])
        stem_to_base[path.stem] = target.stem
        if meta.get("url"):
            url_to_base[meta["url"]] = target.stem
        if path != target:
            path.rename(target)
            mapping[str(path.relative_to(ROOT))] = str(target.relative_to(ROOT))
        item = manifest_url_index.get(meta.get("url", ""))
        if item:
            item["raw_text"] = str(target.relative_to(ROOT))

    for path in sorted(RAW_HTML_DIR.glob("*.html")):
        base = stem_to_base.get(path.stem)
        if not base:
            base = safe_title(path.stem, path.stem)
        target = unique_path(path.parent, base, path.suffix, reserved_by_dir[path.parent])
        if path != target:
            path.rename(target)
            mapping[str(path.relative_to(ROOT))] = str(target.relative_to(ROOT))

        for item in manifest:
            if Path(str(item.get("raw_html", ""))).name == path.name:
                item["raw_html"] = str(target.relative_to(ROOT))
                break

    for path in sorted(ARTICLES_DIR.glob("*.json")):
        try:
            meta = metadata_from_article(path)
        except Exception:
            continue
        base = url_to_base.get(meta.get("url", "")) or make_base(meta, path.stem)
        target = unique_path(path.parent, base, path.suffix, reserved_by_dir[path.parent])
        if path != target:
            path.rename(target)
            mapping[str(path.relative_to(ROOT))] = str(target.relative_to(ROOT))

    write_manifest(manifest)
    MAP_FILE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Renamed {len(mapping)} files.")
    print(f"Wrote {MAP_FILE.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
