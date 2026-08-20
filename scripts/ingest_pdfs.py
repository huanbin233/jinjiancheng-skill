#!/usr/bin/env python3
"""将 pdf/ 中尚未入库的盲区文章，按 ingest.py 同款规则入库到 articles/ + raw/text/，并更新 data 索引。

盲区判定：以 '日期-标题'(去~) 为唯一 key。pdf 文件 key 不在 articles/*.json 与
raw/text/*.txt 的文件名 key 集合中，即视为未入库。
注意：必须用 日期+标题 区分同名不同期的文章（如机哥两次所写
'有些话只能点到为止' 2025 与 2026 两篇），不能用归一化标题判重。

字段提取完全复用 ingest.py 的规则函数（mentioned_assets / matching_sentences 等），
不依赖任何 LLM。数据源从 HTML/TXT 换成 PDF 文本。

用法：
    python scripts/ingest_pdfs.py --dry-run      # 只打印将入库清单 + 首篇预览，不落盘
    python scripts/ingest_pdfs.py                # 正式入库
"""
from __future__ import annotations

import argparse
import json
import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import ROOT, RAW_TEXT_DIR, ARTICLES_DIR, INDEX_FILE, MAP_FILE
from ingest import (
    mentioned_assets,
    matching_sentences,
    normalize_text,
    BUY_KEYWORDS,
    HOLD_KEYWORDS,
    SELL_KEYWORDS,
    RISK_KEYWORDS,
    first_nonempty,
)
from pypdf import PdfReader


def norm(s: str) -> str:
    s = s.replace("~", "")
    return re.sub(r"[^0-9a-zA-Z一-鿿]", "", s).lower()


def build_existing() -> set[str]:
    """已入库标识集合：以 '日期-标题'(去~) 为唯一 key。

    关键：必须用 日期+标题 区分同名不同期的文章（如机哥两次所写的
    '有些话只能点到为止' 2025 与 2026 两篇），否则归一化标题判重会把
    后一篇误判为已入库而漏掉。
    """
    existing: set[str] = set()

    def add_stem(stem: str) -> None:
        # stem 形如 YYYY-MM-DD-HHMM-title（可能含~），统一去~作为 key
        existing.add(stem.replace("~", ""))

    for f in glob.glob(str(ARTICLES_DIR / "*.json")):
        add_stem(Path(f).stem)
    for f in glob.glob(str(RAW_TEXT_DIR / "*.txt")):
        add_stem(Path(f).stem)
    return existing


def max_article_number() -> int:
    maxn = 0
    for f in glob.glob(str(ARTICLES_DIR / "*.json")):
        try:
            a = json.load(open(f, encoding="utf-8")).get("article_id")
        except Exception:
            continue
        if a and re.fullmatch(r"A\d+", a):
            maxn = max(maxn, int(a[1:]))
    return maxn


PDF_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{4})-(.+)\.pdf$")


def collect_plan(existing: set[str]) -> list[dict]:
    plan: list[dict] = []
    for f in sorted(glob.glob(str(ROOT / "pdf" / "*.pdf"))):
        name = Path(f).name
        m = PDF_RE.match(name)
        if not m:
            continue
        y, mo, d, hm, title = m.groups()
        # 用完整 '日期-标题'(去~) 作为判重 key，区分同名不同期文章
        key = f"{y}-{mo}-{d}-{hm}-{title.replace('~', '')}"
        if key in existing:
            continue
        plan.append(
            {
                "src": f,
                "name": name,
                "title": title,
                "published_at": f"{y}-{mo}-{d}",
                "published_at_for_filename": f"{y}-{mo}-{d}-{hm}",
            }
        )
    return plan


def build_article(record: dict, article_id: str) -> dict:
    reader = PdfReader(record["src"])
    raw = "\n".join((p.extract_text() or "") for p in reader.pages)
    clean = normalize_text(raw)

    buy = matching_sentences(clean, BUY_KEYWORDS)
    hold = matching_sentences(clean, HOLD_KEYWORDS)
    sell = matching_sentences(clean, SELL_KEYWORDS)
    risks = matching_sentences(clean, RISK_KEYWORDS)

    evidence: list[str] = []
    for group in (buy, hold, sell, risks):
        for sentence in group:
            if sentence not in evidence:
                evidence.append(sentence)
            if len(evidence) >= 8:
                break

    return {
        "url": "",
        "article_id": article_id,
        "title": record["title"],
        "published_at": record["published_at"],
        "published_at_for_filename": record["published_at_for_filename"],
        "account_name": "天玑",
        "clean_text": clean,
        "mentioned_assets": mentioned_assets(clean),
        "core_thesis": first_nonempty(hold, buy, risks),
        "buy_or_accumulate_conditions": buy,
        "hold_conditions": hold,
        "reduce_or_exit_conditions": sell,
        "risk_notes": risks,
        "source_evidence": evidence,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="将 pdf 盲区文章按规则入库")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不落盘")
    args = ap.parse_args()

    existing = build_existing()
    plan = collect_plan(existing)
    maxn = max_article_number()
    records = []
    for i, rec in enumerate(plan, start=maxn + 1):
        records.append((f"A{i:03d}", rec))

    print(f"现有最大 article_id: A{maxn:03d}")
    print(f"将入库盲区数量: {len(records)}")
    for aid, rec in records:
        print(f"  {aid}  {rec['published_at_for_filename']}  {rec['title']}")

    if not records:
        print("无盲区，无需入库。")
        return

    if args.dry_run:
        # 首篇预览，确认 PDF 文本质量
        aid, rec = records[0]
        article = build_article(rec, aid)
        print("\n=== 首篇预览（clean_text 前 600 字）===")
        print(article["clean_text"][:600])
        print("\n=== 首篇结构化字段抽样 ===")
        print("  mentioned_assets:", article["mentioned_assets"][:10])
        print("  core_thesis:", article["core_thesis"][:120])
        print("  buy:", article["buy_or_accumulate_conditions"][:2])
        print("  hold:", article["hold_conditions"][:2])
        return

    # 正式入库
    index = json.load(open(INDEX_FILE, encoding="utf-8"))
    fmap = json.load(open(MAP_FILE, encoding="utf-8"))
    written = 0
    for aid, rec in records:
        article = build_article(rec, aid)
        out_json = ARTICLES_DIR / f"{rec['published_at_for_filename']}-{rec['title']}.json"
        out_txt = RAW_TEXT_DIR / f"{rec['published_at_for_filename']}-{rec['title']}.txt"
        out_json.write_text(json.dumps(article, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out_txt.write_text(article["clean_text"], encoding="utf-8")
        index.append(article)
        fmap[f"raw/text/{aid}_s.txt"] = f"raw/text/{rec['published_at_for_filename']}-{rec['title']}.txt"
        written += 1
        print(f"  [OK] {aid} -> {out_json.name}")

    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MAP_FILE.write_text(json.dumps(fmap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n入库完成：写入 {written} 篇。articles_index 现 {len(index)} 条，filename_map 现 {len(fmap)} 条。")


if __name__ == "__main__":
    main()
