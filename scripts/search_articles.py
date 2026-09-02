#!/usr/bin/env python3
"""检索本地金渐成文章记录，并返回可引用的证据片段。"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


from _paths import ARTICLES_DIR, RAW_TEXT_DIR, PROJECT_ROOT


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


# 概念 -> 同义词组。查询词命中组内任意词（含概念名）时，整组加入概念展开词。
# 概念展开词在打分时权重减半，避免"顺嘴提一句"的文章冲上榜首。
# 与 references/query-patterns.md 保持一致，修改时两处同步。
CONCEPTS = {
    "降成本": ["做t", "摊薄", "降低成本", "回本", "高抛低吸", "做差价"],
    "做t": ["降成本", "摊薄", "高抛低吸", "做差价", "回本"],
    "负成本": ["降成本", "做t", "回本", "摊薄"],
    "建仓": ["买入", "底仓", "左侧", "分批", "试错"],
    "加仓": ["金字塔加仓", "越跌越买", "补仓", "抄底"],
    "减仓": ["止盈", "卖出", "清仓", "落袋", "高抛", "获利了结"],
    "不满仓": ["留现金", "子弹", "备用金", "7成", "7.5成", "半仓", "现金为王"],
    "满仓": ["仓位", "重仓", "加杠杆"],
    "防守型资产": ["压舱石", "安全垫", "财富锚", "短债", "红利", "股息", "债券"],
    "第一或唯一": ["龙头", "垄断", "护城河", "不可替代"],
    "美元资产": ["美元现金", "美债", "美元定存", "海外配置", "全球配置"],
    "策略迭代": ["策略过期", "体系迭代", "重构", "复盘"],
}


@dataclass
class Article:
    title: str
    date: str
    source_file: Path
    url: str
    text: str
    core_thesis: str = ""
    buy_conditions: list[str] = field(default_factory=list)
    hold_conditions: list[str] = field(default_factory=list)
    sell_conditions: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)


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


def tokenize_query(query: str, expand_aliases: bool = True) -> tuple[list[str], list[str], list[str]]:
    """返回 (用户原词, 标的别名, 概念展开词) 三组。

    权重语义：原词与标的别名同权（都是用户明确要查的），
    概念展开词减半（只是语义相关，避免噪音文章冲榜）。
    """
    raw_terms = [
        part.strip()
        for part in re.split(r"[\s,，;；|/]+", query)
        if part.strip()
    ]
    primary: list[str] = []
    alias_terms: list[str] = []
    concept_terms: list[str] = []
    for term in raw_terms:
        if term not in primary:
            primary.append(term)
        if expand_aliases:
            for alias in ALIASES.get(term.lower(), []) + ALIASES.get(term, []):
                if alias not in primary and alias not in alias_terms and alias not in concept_terms:
                    alias_terms.append(alias)
            term_lower = term.lower()
            for concept, synonyms in CONCEPTS.items():
                group = [concept] + list(synonyms)
                if term_lower in {g.lower() for g in group}:
                    for word in group:
                        w = word.lower()
                        if w == term_lower:
                            continue
                        if w not in primary and w not in alias_terms and w not in concept_terms:
                            concept_terms.append(w)
    if query.strip() and not raw_terms:
        primary.append(query.strip())
    return primary, alias_terms, concept_terms


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
    return Article(
        title=title,
        date=date,
        source_file=path,
        url=url,
        text="\n".join(text_parts),
        core_thesis=str(data.get("core_thesis") or ""),
        buy_conditions=list(data.get("buy_or_accumulate_conditions") or []),
        hold_conditions=list(data.get("hold_conditions") or []),
        sell_conditions=list(data.get("reduce_or_exit_conditions") or []),
        risk_notes=list(data.get("risk_notes") or []),
    )


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


def score_article(
    article: Article,
    primary_terms: list[str],
    alias_terms: list[str],
    concept_terms: list[str],
) -> int:
    score = 0
    # 用户原词与标的别名同权
    for term in primary_terms:
        score += contains_term(article.title, term) * 20
        score += min(contains_term(article.text, term), 12)
    for term in alias_terms:
        score += contains_term(article.title, term) * 20
        score += min(contains_term(article.text, term), 12)
    # 概念展开词权重减半
    for term in concept_terms:
        score += contains_term(article.title, term) * 10
        score += min(contains_term(article.text, term), 6)
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
    primary, alias_terms, concept_terms = tokenize_query(query)
    all_terms = primary + alias_terms + concept_terms
    scored: list[tuple[int, Article, list[str]]] = []
    for article in iter_articles(source):
        matches = matched_terms(article, all_terms)
        if not matches:
            continue
        score = score_article(article, primary, alias_terms, concept_terms)
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
                "core_thesis": article.core_thesis,
                "buy_or_accumulate_conditions": article.buy_conditions,
                "hold_conditions": article.hold_conditions,
                "reduce_or_exit_conditions": article.sell_conditions,
                "risk_notes": article.risk_notes,
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


def print_timeline(results: list[dict[str, object]]) -> None:
    """按日期升序输出观点时间线，按年份分组，展示每篇的核心观点与买卖条件。"""
    if not results:
        print("未找到匹配结果。")
        return
    print(f"观点时间线（按日期升序，共 {len(results)} 篇）：\n")
    current_year = ""
    for item in results:
        year = str(item["date"])[:4] or "?"
        if year != current_year:
            current_year = year
            print(f"———— {current_year} ————")
        print(f"[{item['date']}] {item['title']}")
        thesis = str(item.get("core_thesis") or "").strip()
        if thesis:
            print(f"  核心观点: {thesis[:90]}")
        for label, key in (
            ("建仓/加仓", "buy_or_accumulate_conditions"),
            ("持有条件", "hold_conditions"),
            ("减仓/退出", "reduce_or_exit_conditions"),
            ("风险备注", "risk_notes"),
        ):
            conds = item.get(key) or []
            if conds:
                shown = "；".join(str(c)[:40] for c in conds[:2])
                print(f"  {label}: {shown}")
        print(f"  来源: {item['source_file']}")
        print()


def main() -> int:
    parser = ChineseArgumentParser(
        description=__doc__,
        usage="%(prog)s [选项] 检索词",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助信息并退出")
    parser.add_argument("query", help="检索词，例如：'英伟达 NVDA 减仓'")
    parser.add_argument("--limit", type=int, default=None, help="最多返回多少条结果。")
    parser.add_argument("--context", type=int, default=120, help="首个命中词前后的片段字符数。")
    parser.add_argument(
        "--source",
        choices=["both", "articles", "raw"],
        default="both",
        help="检索来源：both 为结构化文章和正文，articles 只查结构化文章，raw 只查正文。",
    )
    parser.add_argument("--timeline", action="store_true", help="按日期升序输出观点时间线（默认 limit 30，可用 --limit 调整）。")
    parser.add_argument("--json", action="store_true", help="输出 JSON，而不是易读文本。")
    args = parser.parse_args()

    limit = args.limit if args.limit is not None else (30 if args.timeline else 8)
    results = search(args.query, max(1, limit), args.source, max(40, args.context))
    if args.timeline:
        results.sort(key=lambda r: (str(r["date"]), str(r["title"])))
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print_timeline(results)
        return 0
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_markdown(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
