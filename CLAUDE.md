# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A reusable AI Skill based on 384 Chinese-language investing articles by 金渐成 (a Fujian-born investor now in California). Any compatible AI agent loads this Skill to answer questions about US stocks, ETFs, asset allocation, and risk management through the author's investing framework.

AGENTS.md is the primary entry point loaded by Claude Code, Cursor, and Codex CLI. SKILL.md is the WorkBuddy entry point.

## Core operation

```bash
python scripts/search_articles.py "防守型账户" --limit 5
python scripts/search_articles.py "英伟达 NVDA 减仓 负成本" --limit 8 --json
```

Search queries must be in Chinese. The script searches both `articles/*.json` (structured) and `raw/text/*.txt` (cleaned full text), expands ticker aliases automatically (e.g., NVDA → 英伟达, Nvidia, 黄仁勋, GPU), and returns scored results with evidence snippets.

## Project structure

```
scripts/search_articles.py   ← Core: full-text search across all articles
scripts/ingest.py            ← Data pipeline: link manifest → ingest → structured JSON → manual
scripts/export_drission.py   ← Browser-based article download (DrissionPage, recommended)
references/                  ← Domain knowledge loaded by the agent at query time
  framework.md               ← Complete investing framework (3-tier accounts, position rules, macro cycles)
  金渐成-人格画像.md          ← Author's persona, philosophy, values, writing style
  query-patterns.md           ← Search keyword expansion and ticker aliases
  pipeline.md                 ← Data pipeline guide
articles/*.json               ← 384 structured articles with extracted conditions and risks
raw/text/*.txt                ← Cleaned full-text articles
raw/html/*.html               ← Saved original article pages
manual/                       ← Human-curated framework and long-form reference docs
data/                         ← Link manifests and article indexes
```

## When answering investing questions

The workflow (defined in AGENTS.md and SKILL.md) is:

1. Classify the question type (asset allocation / single asset / trade review / macro cycle / risk control / persona)
2. Read the relevant reference files first — `framework.md` for investing questions, `人格画像.md` for persona questions
3. Use `query-patterns.md` to expand search keywords and ticker aliases
4. Run `search_articles.py` to collect primary evidence
5. Structure responses with: conclusion summary → relevant framework → primary evidence (with source dates) → operational checklist → risks and data gaps
6. Always distinguish: what the articles directly say vs framework inference vs stale data that needs current market verification
7. Never output deterministic buy/sell instructions

## Data pipeline (when updating articles)

```bash
python scripts/ingest.py init       # Initialize link manifest from data/gongzhonghao.json
python scripts/export_drission.py   # Download articles via browser automation
python scripts/ingest.py ingest     # Extract structured JSON from raw files
python scripts/ingest.py manual     # Generate long-form manual
python scripts/ingest.py status     # Check pipeline status
```

Flow: `data/gongzhonghao.json → links_manifest.json → raw/html/ + raw/text/ → articles/*.json → manual/`

Dependencies: `drissionpage`, `pypdf`. Install with `pip install drissionpage pypdf`.

## Key constraints

- All search queries and article content are in Chinese — do not translate search terms
- Article evidence snippets must be short; paraphrase rather than quoting long passages
- Historical price levels from articles are not actionable today — flag them as stale
- Never imply the author's positions are suitable for any reader's capital, tax situation, or risk tolerance
- The strategy has a ~3-year shelf life (the author explicitly says this); the framework principles outlast specific trade examples
