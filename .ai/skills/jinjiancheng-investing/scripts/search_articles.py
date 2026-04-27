#!/usr/bin/env python3
"""检索本地金渐成文章记录，并返回可引用的证据片段。"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[4]
ARTICLES_DIR = PROJECT_ROOT / "articles"
RAW_TEXT_DIR = PROJECT_ROOT / "raw" / "text"


ALIASES = {
    "nvda": ["英伟达", "nvidia", "黄仁勋", "gpu", "算力"],
    "英伟达": ["nvda", "nvidia", "黄仁勋", "gpu", "算力"],
    "tsla": ["特斯拉", "tesla", "马斯克", "电动车", "自动驾驶"],
    "特斯拉": ["tsla", "tesla", "马斯克", "电动车", "自动驾驶"],
    "aapl": ["苹果", "apple", "iphone"],
    "苹果": ["aapl", "apple", "iphone"],
    "msft": ["微软", "microsoft", "openai", "云计算"],
    "微软": ["msft", "microsoft", "openai", "云计算"],
    "googl": ["goog", "谷歌", "google", "alphabet", "搜索"],
    "goog": ["googl", "谷歌", "google", "alphabet", "搜索"],
    "谷歌": ["googl", "goog", "google", "alphabet", "搜索"],
    "amzn": ["亚马逊", "amazon", "aws"],
    "亚马逊": ["amzn", "amazon", "aws"],
    "meta": ["脸书", "facebook", "instagram", "元宇宙"],
    "brk": ["伯克希尔", "巴菲特", "buffett"],
    "伯克希尔": ["brk", "巴菲特", "buffett"],
    "tsm": ["台积电", "tsmc", "半导体", "晶圆"],
    "台积电": ["tsm", "tsmc", "半导体", "晶圆"],
    "spy": ["voo", "标普", "标普500", "s&p", "宽基"],
    "voo": ["spy", "标普", "标普500", "s&p", "宽基"],
    "标普": ["spy", "voo", "标普500", "s&p", "宽基"],
    "qqq": ["纳指", "纳斯达克", "纳指100", "科技股"],
    "纳指": ["qqq", "纳斯达克", "纳指100", "科技股"],
    "tlt": ["美债", "长债", "国债", "债券", "降息"],
    "美债": ["tlt", "长债", "国债", "债券", "降息"],
    "bil": ["短债", "美元现金", "现金管理", "货币基金"],
}


@dataclass
class Article:
    title: str
    date: str
    source_file: Path
    url: str
    text: str


class ChineseArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "用法:")
            .replace("positional arguments:", "位置参数:")
            .replace("options:", "选项:")
        )

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法:")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def tokenize_query(query: str, expand_aliases: bool = True) -> list[str]:
    raw_terms = [
        part.strip()
        for part in re.split(r"[\s,，;；|/]+", query)
        if part.strip()
    ]
    terms: list[str] = []
    for term in raw_terms:
        if term not in terms:
            terms.append(term)
        if expand_aliases:
            for alias in ALIASES.get(term.lower(), []) + ALIASES.get(term, []):
                if alias not in terms:
                    terms.append(alias)
    if query.strip() and not raw_terms:
        terms.append(query.strip())
    return terms


def read_json_article(path: Path) -> Article | None:
    if path.name.startswith(".") or path.suffix != ".json":
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    title = str(data.get("title") or path.stem)
    date = str(data.get("published_at") or "")
    if len(date) > 10:
        date = date[:10]
    url = str(data.get("url") or "")
    text_parts = [
        str(data.get("clean_text") or ""),
        " ".join(map(str, data.get("mentioned_assets") or [])),
        str(data.get("core_thesis") or ""),
        " ".join(map(str, data.get("buy_or_accumulate_conditions") or [])),
        " ".join(map(str, data.get("hold_conditions") or [])),
        " ".join(map(str, data.get("reduce_or_exit_conditions") or [])),
        " ".join(map(str, data.get("risk_notes") or [])),
    ]
    return Article(title=title, date=date, source_file=path, url=url, text="\n".join(text_parts))


def parse_header_value(lines: list[str], names: Iterable[str]) -> str:
    for line in lines[:12]:
        for name in names:
            prefix = f"{name}:"
            full_prefix = f"{name}："
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
            if line.startswith(full_prefix):
                return line[len(full_prefix) :].strip()
    return ""


def read_raw_text_article(path: Path) -> Article | None:
    if path.name.startswith(".") or path.suffix != ".txt":
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    lines = text.splitlines()
    title = parse_header_value(lines, ["标题", "Title"]) or path.stem
    date = parse_header_value(lines, ["日期", "发布时间", "Date"])
    if not date:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
        date = match.group(1) if match else ""
    url = parse_header_value(lines, ["原文", "链接", "URL", "url"])
    return Article(title=title, date=date[:10], source_file=path, url=url, text=text)


def article_key(article: Article) -> str:
    if article.url:
        return article.url
    return f"{article.date}|{article.title}"


def iter_articles(source: str) -> Iterable[Article]:
    seen: set[str] = set()
    if source in {"both", "articles"}:
        for path in sorted(ARTICLES_DIR.glob("*.json")):
            article = read_json_article(path)
            if not article:
                continue
            key = article_key(article)
            seen.add(key)
            yield article
    if source in {"both", "raw"}:
        for path in sorted(RAW_TEXT_DIR.glob("*.txt")):
            article = read_raw_text_article(path)
            if not article:
                continue
            key = article_key(article)
            if key in seen:
                continue
            seen.add(key)
            yield article


def contains_term(text: str, term: str) -> int:
    if not term:
        return 0
    if re.search(r"[A-Za-z]", term):
        return len(re.findall(re.escape(term), text, flags=re.IGNORECASE))
    return text.count(term)


def matched_terms(article: Article, terms: list[str]) -> list[str]:
    haystack = f"{article.title}\n{article.text}"
    return [term for term in terms if contains_term(haystack, term) > 0]


def score_article(article: Article, terms: list[str]) -> int:
    score = 0
    for term in terms:
        title_hits = contains_term(article.title, term)
        text_hits = contains_term(article.text, term)
        score += title_hits * 20
        score += min(text_hits, 12)
    return score


def snippet(article: Article, terms: list[str], context: int) -> str:
    compact = normalize_space(article.text)
    if not compact:
        return ""

    lower = compact.lower()
    positions: list[int] = []
    for term in terms:
        if re.search(r"[A-Za-z]", term):
            index = lower.find(term.lower())
        else:
            index = compact.find(term)
        if index >= 0:
            positions.append(index)

    start_at = min(positions) if positions else 0
    start = max(0, start_at - context)
    end = min(len(compact), start_at + context)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def search(query: str, limit: int, source: str, context: int) -> list[dict[str, object]]:
    terms = tokenize_query(query)
    scored: list[tuple[int, Article, list[str]]] = []
    for article in iter_articles(source):
        matches = matched_terms(article, terms)
        if not matches:
            continue
        score = score_article(article, terms)
        if score <= 0:
            continue
        scored.append((score, article, matches))

    scored.sort(key=lambda item: (-item[0], item[1].date, item[1].title))
    results: list[dict[str, object]] = []
    for score, article, matches in scored[:limit]:
        source_file = article.source_file.relative_to(PROJECT_ROOT)
        results.append(
            {
                "title": article.title,
                "date": article.date,
                "source_file": str(source_file),
                "url": article.url,
                "matched_terms": matches,
                "evidence_snippet": snippet(article, matches, context),
                "score": score,
            }
        )
    return results


def print_markdown(results: list[dict[str, object]]) -> None:
    if not results:
        print("未找到匹配结果。")
        return
    for index, item in enumerate(results, start=1):
        print(f"{index}. {item['title']} ({item['date']})")
        print(f"   来源文件: {item['source_file']}")
        if item["url"]:
            print(f"   原文链接: {item['url']}")
        print(f"   命中词: {', '.join(item['matched_terms'])}")
        print(f"   证据片段: {item['evidence_snippet']}")
        print()


def main() -> int:
    parser = ChineseArgumentParser(
        description=__doc__,
        usage="%(prog)s [选项] 检索词",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助信息并退出")
    parser.add_argument("query", help="检索词，例如：'英伟达 NVDA 减仓'")
    parser.add_argument("--limit", type=int, default=8, help="最多返回多少条结果。")
    parser.add_argument("--context", type=int, default=120, help="首个命中词前后的片段字符数。")
    parser.add_argument(
        "--source",
        choices=["both", "articles", "raw"],
        default="both",
        help="检索来源：both 为结构化文章和正文，articles 只查结构化文章，raw 只查正文。",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON，而不是易读文本。")
    args = parser.parse_args()

    results = search(args.query, max(1, args.limit), args.source, max(40, args.context))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_markdown(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
