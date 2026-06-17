# 数据管道使用指南

维护和更新金渐成公众号文章知识库的完整流程。

## 数据流

```
gongzhonghao.json (链接池)
    ↓  python scripts/ingest.py init
links_manifest.json (去重清单+状态)
    ↓  python scripts/export_drission.py (浏览器下载)
raw/html/ + raw/text/ (原始文件)
    ↓  python scripts/ingest.py ingest
articles/*.json + articles_index.json (结构化文章)
    ↓  python scripts/ingest.py manual
manual/长期配置操作手册.md
```

## 常用命令

### 初始化链接清单

```bash
python scripts/ingest.py init
```

从 `data/gongzhonghao.json` 读取链接，去重后生成 `data/links_manifest.json`。

### 收集新链接

```bash
# 从已有 HTML/TXT 中提取链接
python scripts/link_harvester.py

# 用浏览器自动滚动收集（DrissionPage）
python scripts/collect_drission.py --url "https://mp.weixin.qq.com/..." --export

# 用浏览器自动滚动收集（Playwright 备用）
python scripts/collect_playwright.py --url "https://mp.weixin.qq.com/..." --export
```

### 下载文章

```bash
# DrissionPage（推荐）
python scripts/export_drission.py

# Playwright（备用）
python scripts/export_playwright.py
```

### 结构化提取

```bash
python scripts/ingest.py ingest
```

从 `raw/html/` 和 `raw/text/` 中提取标题、日期、正文，生成 `articles/` 下的 JSON 文件和 `data/articles_index.json`。

### 生成操作手册

```bash
python scripts/ingest.py manual
```

### 重命名文件

```bash
python scripts/rename.py
```

### 查看状态

```bash
python scripts/ingest.py status
```

## 状态流转

```
needs_browser_export → raw_available → ingested
```

## 前置依赖

```bash
pip install drissionpage pypdf
# Playwright 备用方案需要额外安装：
# pip install playwright && python -m playwright install chromium
```
