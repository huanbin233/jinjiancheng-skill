#!/usr/bin/env python3
"""Local workflow for WeChat article archiving and investment-manual drafting."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
LINKS_FILE = ROOT / "gongzhonghao.json"
DATA_DIR = ROOT / "data"
RAW_HTML_DIR = ROOT / "raw" / "html"
RAW_TEXT_DIR = ROOT / "raw" / "text"
ARTICLES_DIR = ROOT / "articles"
MANUAL_DIR = ROOT / "manual"
MANIFEST_FILE = DATA_DIR / "links_manifest.json"
INDEX_FILE = DATA_DIR / "articles_index.json"
MANUAL_FILE = MANUAL_DIR / "长期配置操作手册.md"
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')

BUY_KEYWORDS = ("买入", "建仓", "加仓", "定投", "配置", "低估", "低位", "回调", "便宜", "机会")
HOLD_KEYWORDS = ("持有", "长期", "复利", "护城河", "竞争力", "现金流", "壁垒", "龙头", "垄断")
SELL_KEYWORDS = ("卖出", "减仓", "止盈", "高估", "泡沫", "风险", "不及预期", "逻辑", "恶化")
RISK_KEYWORDS = ("风险", "回撤", "衰退", "加息", "降息", "通胀", "财报", "监管", "竞争", "周期")
ASSET_ALIASES = {
    "纳斯达克": "NASDAQ",
    "标普": "S&P 500",
    "道琼斯": "DOW",
    "英伟达": "NVDA",
    "苹果": "AAPL",
    "微软": "MSFT",
    "谷歌": "GOOGL",
    "亚马逊": "AMZN",
    "特斯拉": "TSLA",
    "Meta": "META",
    "META": "META",
    "美股": "US equities",
}
PROGRESS_EVERY = 25


def progress_log(enabled: bool, message: str) -> None:
    if enabled:
        print(message, flush=True)


class TextExtractor(HTMLParser):
    """Small HTML text extractor good enough for saved article pages."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag in {"p", "br", "div", "section", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return normalize_text("\n".join(self.parts))


@dataclass
class LinkRecord:
    article_id: str
    url: str
    slug: str
    original_positions: list[int]
    raw_html: str
    raw_text: str
    status: str


def ensure_dirs() -> None:
    for path in (DATA_DIR, RAW_HTML_DIR, RAW_TEXT_DIR, ARTICLES_DIR, MANUAL_DIR):
        path.mkdir(parents=True, exist_ok=True)


def read_links() -> list[str]:
    with LINKS_FILE.open("r", encoding="utf-8") as fh:
        links = json.load(fh)
    if not isinstance(links, list) or not all(isinstance(item, str) for item in links):
        raise ValueError(f"{LINKS_FILE} must be a JSON array of URL strings")
    return links


def slug_for_url(url: str) -> str:
    parsed = urlparse(url)
    slug = parsed.path.rstrip("/").split("/")[-1] or parsed.netloc
    return re.sub(r"[^A-Za-z0-9_-]+", "-", slug).strip("-")[:48]


def raw_file_exists(record: dict[str, Any]) -> bool:
    return any((ROOT / str(record.get(key, ""))).exists() for key in ("raw_html", "raw_text"))


def refresh_status(record: dict[str, Any]) -> str:
    if record.get("status") == "ingested":
        return "ingested"
    return "raw_available" if raw_file_exists(record) else "needs_browser_export"


def load_existing_manifest_records() -> list[dict[str, Any]]:
    if not MANIFEST_FILE.exists():
        return []
    try:
        data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and isinstance(item.get("url"), str)]


def next_article_id(existing_records: list[dict[str, Any]]) -> str:
    used_ids = {str(item.get("article_id")) for item in existing_records if item.get("article_id")}
    max_number = 0
    for article_id in used_ids:
        match = re.fullmatch(r"A(\d+)", article_id)
        if match:
            max_number = max(max_number, int(match.group(1)))

    while True:
        max_number += 1
        candidate = f"A{max_number:03d}"
        if candidate not in used_ids:
            return candidate


def normalized_manifest_record(
    record: dict[str, Any],
    positions: list[int],
    existing_records: list[dict[str, Any]],
) -> dict[str, Any]:
    record = dict(record)
    url = str(record["url"])
    article_id = str(record.get("article_id") or next_article_id(existing_records))
    slug = str(record.get("slug") or slug_for_url(url))
    record["article_id"] = article_id
    record["url"] = url
    record["slug"] = slug
    record["original_positions"] = positions
    if not record.get("raw_html"):
        record["raw_html"] = f"raw/html/{article_id}_{slug}.html"
    if not record.get("raw_text"):
        record["raw_text"] = f"raw/text/{article_id}_{slug}.txt"
    record["status"] = refresh_status(record)
    return record


def build_manifest(verbose: bool = False) -> list[dict[str, Any]]:
    ensure_dirs()
    positions_by_url: dict[str, list[int]] = {}
    for index, url in enumerate(read_links(), start=1):
        positions_by_url.setdefault(url, []).append(index)

    progress_log(verbose, f"Refreshing manifest from {LINKS_FILE.relative_to(ROOT)}...")
    existing_records = load_existing_manifest_records()
    records: list[dict[str, Any]] = []
    included_urls: set[str] = set()
    kept_count = 0
    new_count = 0

    for existing in existing_records:
        url = str(existing["url"])
        if url not in positions_by_url or url in included_urls:
            continue
        records.append(normalized_manifest_record(existing, positions_by_url[url], existing_records))
        included_urls.add(url)
        kept_count += 1

    for url, positions in positions_by_url.items():
        if url in included_urls:
            continue
        article_id = next_article_id(existing_records + records)
        slug = slug_for_url(url)
        raw_html = f"raw/html/{article_id}_{slug}.html"
        raw_text = f"raw/text/{article_id}_{slug}.txt"
        status = "raw_available" if (ROOT / raw_html).exists() or (ROOT / raw_text).exists() else "needs_browser_export"
        records.append(
            {
                "article_id": article_id,
                "url": url,
                "slug": slug,
                "original_positions": positions,
                "raw_html": raw_html,
                "raw_text": raw_text,
                "status": status,
            }
        )
        new_count += 1

    MANIFEST_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    progress_log(
        verbose,
        f"Manifest refreshed: {kept_count} existing kept, {new_count} new, {len(records)} total.",
    )
    return records


def load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_FILE.exists():
        return build_manifest()
    with MANIFEST_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_title(raw: str, text: str) -> str:
    patterns = [
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+name=["\']twitter:title["\']\s+content=["\']([^"\']+)["\']',
        r"var\s+msg_title\s*=\s*['\"]([^'\"]+)['\"]",
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.I | re.S)
        if match:
            title = normalize_text(re.sub(r"<[^>]+>", "", match.group(1)))
            if title and title != "微信公众平台":
                return title
    return text.splitlines()[0][:80] if text else ""


def extract_account(raw: str, text: str) -> str:
    patterns = [
        r"var\s+nickname\s*=\s*['\"]([^'\"]+)['\"]",
        r'<meta\s+property=["\']og:article:author["\']\s+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.I | re.S)
        if match:
            return normalize_text(match.group(1))
    for line in text.splitlines()[:12]:
        if "微信号" in line or "公众号" in line:
            return line[:80]
    return ""


def extract_date(raw: str, text: str) -> str:
    ct_match = re.search(r"var\s+ct\s*=\s*['\"]?(\d{10})['\"]?", raw)
    if ct_match:
        return datetime.fromtimestamp(int(ct_match.group(1))).strftime("%Y-%m-%d")
    patterns = [r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?", r"(\d{4})\.(\d{1,2})\.(\d{1,2})"]
    for pattern in patterns:
        match = re.search(pattern, text[:800])
        if match:
            year, month, day = (int(part) for part in match.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def extract_datetime_for_filename(raw: str, text: str) -> str:
    ct_match = re.search(r"var\s+ct\s*=\s*['\"]?(\d{10})['\"]?", raw)
    if ct_match:
        return datetime.fromtimestamp(int(ct_match.group(1))).strftime("%Y-%m-%d-%H%M")
    match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?\s+(\d{1,2}):(\d{1,2})", text[:1000])
    if match:
        year, month, day, hour, minute = (int(part) for part in match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}-{hour:02d}{minute:02d}"
    return extract_date(raw, text) or "unknown-date"


def safe_filename_part(value: str, fallback: str) -> str:
    value = INVALID_FILENAME_CHARS.sub("-", value.strip())
    value = re.sub(r"\s+", " ", value).strip(" .-_")
    return value[:80] or fallback


def article_output_path(article: dict[str, Any]) -> Path:
    date = article.get("published_at_for_filename") or article.get("published_at") or "unknown-date"
    title = safe_filename_part(str(article.get("title") or ""), str(article.get("article_id") or "article"))
    base = f"{date}-{title}"
    path = ARTICLES_DIR / f"{base}.json"
    if not path.exists():
        return path
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("url") == article.get("url"):
            return path
    except Exception:
        pass
    index = 2
    while True:
        candidate = ARTICLES_DIR / f"{base}-{index}.json"
        if not candidate.exists():
            return candidate
        try:
            existing = json.loads(candidate.read_text(encoding="utf-8"))
            if existing.get("url") == article.get("url"):
                return candidate
        except Exception:
            pass
        index += 1


def html_to_text(raw: str) -> str:
    extractor = TextExtractor()
    extractor.feed(raw)
    return extractor.text()


def sentence_split(text: str) -> list[str]:
    pieces = re.split(r"(?<=[。！？!?])\s*|\n+", text)
    return [piece.strip() for piece in pieces if len(piece.strip()) >= 8]


def matching_sentences(text: str, keywords: tuple[str, ...], limit: int = 5) -> list[str]:
    matches: list[str] = []
    for sentence in sentence_split(text):
        if any(keyword in sentence for keyword in keywords):
            matches.append(sentence[:240])
        if len(matches) >= limit:
            break
    return matches


def mentioned_assets(text: str) -> list[str]:
    assets = {canonical for alias, canonical in ASSET_ALIASES.items() if alias in text}
    for ticker in re.findall(r"(?<![A-Za-z])\$?([A-Z]{2,5})(?![A-Za-z])", text):
        if ticker not in {"HTTP", "HTML", "CSS", "JSON", "ETF"}:
            assets.add(ticker)
    return sorted(assets)


def first_nonempty(*items: list[str]) -> str:
    for values in items:
        if values:
            return values[0]
    return ""


def ingest_article(record: dict[str, Any]) -> dict[str, Any] | None:
    html_path = ROOT / record["raw_html"]
    text_path = ROOT / record["raw_text"]
    raw = ""
    if html_path.exists():
        raw = html_path.read_text(encoding="utf-8", errors="replace")
        clean_text = html_to_text(raw)
    elif text_path.exists():
        raw = text_path.read_text(encoding="utf-8", errors="replace")
        clean_text = normalize_text(raw)
    else:
        return None

    buy = matching_sentences(clean_text, BUY_KEYWORDS)
    hold = matching_sentences(clean_text, HOLD_KEYWORDS)
    sell = matching_sentences(clean_text, SELL_KEYWORDS)
    risks = matching_sentences(clean_text, RISK_KEYWORDS)
    evidence = []
    for group in (buy, hold, sell, risks):
        for sentence in group:
            if sentence not in evidence:
                evidence.append(sentence)
            if len(evidence) >= 8:
                break

    article = {
        "url": record["url"],
        "article_id": record["article_id"],
        "title": extract_title(raw, clean_text),
        "published_at": extract_date(raw, clean_text),
        "published_at_for_filename": extract_datetime_for_filename(raw, clean_text),
        "account_name": extract_account(raw, clean_text),
        "clean_text": clean_text,
        "mentioned_assets": mentioned_assets(clean_text),
        "core_thesis": first_nonempty(hold, buy, risks),
        "buy_or_accumulate_conditions": buy,
        "hold_conditions": hold,
        "reduce_or_exit_conditions": sell,
        "risk_notes": risks,
        "source_evidence": evidence,
    }
    output = article_output_path(article)
    output.write_text(json.dumps(article, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return article


def ingest_all(verbose: bool = False, progress_every: int = PROGRESS_EVERY) -> list[dict[str, Any]]:
    manifest = load_manifest()
    articles: list[dict[str, Any]] = []
    updated_manifest: list[dict[str, Any]] = []
    total = len(manifest)
    progress_log(verbose, f"Ingesting {total} manifest records...")
    for index, record in enumerate(manifest, start=1):
        article = ingest_article(record)
        record = dict(record)
        record["status"] = "ingested" if article else "needs_browser_export"
        updated_manifest.append(record)
        if article:
            articles.append(article)
        if verbose and (index == 1 or index % progress_every == 0 or index == total):
            status = "ingested" if article else "pending"
            title = str(article.get("title") or "untitled") if article else "raw file missing"
            print(f"Ingest progress {index}/{total}: {record['article_id']} {status} - {title[:60]}", flush=True)
    MANIFEST_FILE.write_text(json.dumps(updated_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INDEX_FILE.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    progress_log(verbose, f"Ingest complete: {len(articles)} articles written to {INDEX_FILE.relative_to(ROOT)}.")
    return articles


def adopt_saved_htmls() -> list[str]:
    """Copy manually saved HTML files to their manifest paths when the URL matches."""

    ensure_dirs()
    manifest = load_manifest()
    adopted: list[str] = []
    expected_paths = {(ROOT / item["raw_html"]).resolve() for item in manifest}
    candidates = [
        path
        for path in RAW_HTML_DIR.glob("*.html")
        if path.resolve() not in expected_paths and path.is_file()
    ]
    for path in candidates:
        raw = path.read_text(encoding="utf-8", errors="replace")
        for item in manifest:
            if item["url"] in raw:
                destination = ROOT / item["raw_html"]
                if not destination.exists():
                    shutil.copy2(path, destination)
                    adopted.append(f"{path.name} -> {destination.relative_to(ROOT)}")
                break

    build_manifest()
    return adopted


def generate_rules(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules = [
        {
            "rule_name": "先确认长期逻辑，再谈价格",
            "scenario": "观察",
            "condition": "文章反复强调公司质量、竞争优势、现金流、行业空间或宏观周期时",
            "suggested_action": "把该标的放入观察池，先记录长期逻辑和需要验证的数据，不因单篇情绪直接买入。",
            "source_articles": [item["article_id"] for item in articles if item.get("hold_conditions")][:6],
            "confidence": "medium" if articles else "pending",
            "notes": "首版规则会随正文增多继续校准。",
        },
        {
            "rule_name": "分批建仓优先于一次性押注",
            "scenario": "建仓",
            "condition": "长期逻辑成立，同时出现估值回落、市场恐慌、财报验证或行业拐点迹象",
            "suggested_action": "采用分批配置；每一笔都记录触发条件、仓位比例和失效条件。",
            "source_articles": [item["article_id"] for item in articles if item.get("buy_or_accumulate_conditions")][:6],
            "confidence": "medium" if articles else "pending",
            "notes": "不把低价本身视为充分买入理由。",
        },
        {
            "rule_name": "逻辑受损优先于价格亏损",
            "scenario": "减仓",
            "condition": "基本面、竞争格局、财报趋势、监管环境或原始买入逻辑发生不利变化",
            "suggested_action": "先复盘原始假设，再决定暂停加仓、降低仓位或退出。",
            "source_articles": [item["article_id"] for item in articles if item.get("reduce_or_exit_conditions") or item.get("risk_notes")][:6],
            "confidence": "medium" if articles else "pending",
            "notes": "价格波动本身只触发复盘，不自动触发卖出。",
        },
    ]
    return rules


def article_summary(article: dict[str, Any]) -> str:
    lines = [
        f"### {article.get('article_id', '')} {article.get('title') or '未识别标题'}",
        f"- 原文：{article.get('url', '')}",
        f"- 日期：{article.get('published_at') or '待补'}",
        f"- 公众号：{article.get('account_name') or '待补'}",
        f"- 涉及资产：{', '.join(article.get('mentioned_assets') or []) or '待识别'}",
        f"- 核心观点：{article.get('core_thesis') or '待人工复核'}",
        f"- 建仓/加仓条件：{'; '.join(article.get('buy_or_accumulate_conditions') or ['待提炼'])}",
        f"- 持有条件：{'; '.join(article.get('hold_conditions') or ['待提炼'])}",
        f"- 减仓/退出条件：{'; '.join(article.get('reduce_or_exit_conditions') or ['待提炼'])}",
        f"- 风险提示：{'; '.join(article.get('risk_notes') or ['待提炼'])}",
    ]
    return "\n".join(lines)


def generate_manual(articles: list[dict[str, Any]] | None = None, verbose: bool = False) -> None:
    if articles is None:
        progress_log(verbose, "Manual generation: refreshing article index first...")
        articles = ingest_all(verbose=verbose)
    else:
        progress_log(verbose, f"Manual generation: using {len(articles)} already ingested articles.")

    progress_log(verbose, "Manual generation: deriving rules and summary sections...")
    rules = generate_rules(articles)
    manifest = load_manifest()
    pending = [item for item in manifest if item["status"] != "ingested"]
    duplicate_count = sum(len(item["original_positions"]) - 1 for item in manifest)
    source_link_count = len(read_links())
    manifest_input_count = sum(len(item["original_positions"]) for item in manifest)

    content = [
        "# 长期配置操作手册",
        "",
        "> 研究辅助文件，不构成投资建议或自动买卖指令。涉及实时估值、财报和行情时，需要另行校验最新数据。",
        "",
        "## 当前进度",
        "",
        f"- `gongzhonghao.json` 当前链接：{source_link_count} 条",
        f"- 当前处理队列来源链接：{manifest_input_count} 条",
        f"- 当前处理队列去重文章：{len(manifest)} 篇",
        f"- 当前处理队列重复链接：{duplicate_count} 条",
        f"- 已归档并提炼：{len(articles)} 篇",
        f"- 待浏览器导出：{len(pending)} 篇",
        "",
        "## 长期配置流程",
        "",
        "1. 观察：先确认公司质量、行业空间、宏观位置和估值区间。",
        "2. 建仓：只有当长期逻辑成立且价格/估值/事件提供安全边际时，才分批配置。",
        "3. 加仓：加仓必须来自逻辑增强、估值更有吸引力或关键数据继续验证。",
        "4. 持有：持有期间跟踪原始假设，不被单日价格波动替代判断。",
        "5. 减仓：当逻辑受损、估值显著透支或风险暴露超过预期时复盘并降低仓位。",
        "6. 复盘：每次操作记录来源文章、触发条件、仓位变化和后续验证点。",
        "",
        "## 操作规则库",
        "",
    ]
    for rule in rules:
        content.extend(
            [
                f"### {rule['rule_name']}",
                f"- 场景：{rule['scenario']}",
                f"- 条件：{rule['condition']}",
                f"- 动作：{rule['suggested_action']}",
                f"- 来源文章：{', '.join(rule['source_articles']) or '待正文归档'}",
                f"- 置信度：{rule['confidence']}",
                f"- 备注：{rule['notes']}",
                "",
            ]
        )

    content.extend(["## 文章案例库", ""])
    if articles:
        content.extend(article_summary(article) + "\n" for article in articles)
    else:
        content.extend(
            [
                "尚未归档正文。请按 `README.md` 中的浏览器半自动流程保存文章 HTML 或正文 TXT 后重新运行：",
                "",
                "```bash",
                "python3 tools/article_workflow.py manual",
                "```",
                "",
            ]
        )

    content.extend(
        [
            "## 单标的评估模板",
            "",
            "- 标的/行业：",
            "- 参考文章：",
            "- 长期逻辑：",
            "- 当前估值与安全边际：",
            "- 建仓条件是否满足：",
            "- 加仓条件：",
            "- 暂停/减仓条件：",
            "- 需要跟踪的数据：",
            "- 本次决策：观察 / 建仓 / 加仓 / 持有 / 减仓",
            "",
            "## 待处理文章",
            "",
        ]
    )
    if pending:
        for item in pending:
            content.append(f"- {item['article_id']} {item['url']} -> 保存到 `{item['raw_html']}` 或 `{item['raw_text']}`")
    else:
        content.append("- 无")
    content.append("")

    progress_log(verbose, f"Manual generation: writing {MANUAL_FILE.relative_to(ROOT)}...")
    MANUAL_FILE.write_text("\n".join(content), encoding="utf-8")
    progress_log(verbose, "Manual generation complete.")


def print_status() -> None:
    manifest = load_manifest()
    rows = []
    for item in manifest:
        html_exists = (ROOT / item["raw_html"]).exists()
        text_exists = (ROOT / item["raw_text"]).exists()
        rows.append(f"{item['article_id']} {item['status']:<22} html={html_exists!s:<5} text={text_exists!s:<5} {item['url']}")
    print("\n".join(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the WeChat article research workflow.")
    parser.add_argument("command", choices=["init", "adopt", "ingest", "manual", "status", "open"], help="Workflow command")
    args = parser.parse_args()

    if args.command == "init":
        records = build_manifest(verbose=True)
        print(f"Wrote {MANIFEST_FILE.relative_to(ROOT)} with {len(records)} unique links.")
    elif args.command == "adopt":
        adopted = adopt_saved_htmls()
        if adopted:
            print("Adopted saved HTML files:")
            for item in adopted:
                print(f"- {item}")
        else:
            print("No matching saved HTML files found.")
    elif args.command == "ingest":
        articles = ingest_all(verbose=True)
        print(f"Ingested {len(articles)} articles into {ARTICLES_DIR.relative_to(ROOT)}.")
    elif args.command == "manual":
        generate_manual(verbose=True)
        print(f"Wrote {MANUAL_FILE.relative_to(ROOT)}.")
    elif args.command == "status":
        print_status()
    elif args.command == "open":
        manifest = load_manifest()
        pending = [item for item in manifest if item["status"] != "ingested"]
        for item in pending:
            subprocess.run(["open", item["url"]], check=False)
        print(f"Opened {len(pending)} pending article links in the default browser.")


if __name__ == "__main__":
    main()
