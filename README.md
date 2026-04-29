# 金渐成公众号文章知识库

这个项目用于把金渐成公众号文章归档成本地知识库，并在此基础上提炼他的美股长期配置框架、买卖节点、仓位管理和风险控制方法。

当前流程只保存你能在本机浏览器中正常访问的页面；微信要求登录、验证或权限确认时，需要你手动完成，不绕过验证码、登录、反爬、权限或付费限制。

## 当前状态

- 已归档正文：`raw/text/`，当前 378 篇。
- 已归档网页：`raw/html/`。
- 结构化文章：`articles/`，当前 378 篇。
- 框架总结：`manual/金渐成投资框架总结.md`。
- 项目内 skill：`.ai/skills/jinjiancheng-investing/`。

文件命名已经统一为：

```text
YYYY-MM-DD-HHMM-文章标题.txt
YYYY-MM-DD-HHMM-文章标题.html
YYYY-MM-DD-HHMM-文章标题.json
```

## 目录说明

- `gongzhonghao.json`：文章链接池。
- `data/links_manifest.json`：去重后的采集清单和处理状态。
- `data/filename_map.json`：旧抽象文件名到新文件名的映射。
- `raw/html/`：保存的微信文章 HTML。
- `raw/text/`：清洗后的正文 TXT。
- `articles/`：结构化文章 JSON。
- `manual/`：框架总结和操作手册。
- `tools/article_workflow.py`：本地归档、清洗、生成手册的基础流程。
- `tools/wechat_drission_export.py`：用 DrissionPage 批量下载文章。
- `tools/wechat_drission_collect_links.py`：自动滚动页面、收集更多文章链接，并可继续下载。
- `.ai/skills/jinjiancheng-investing/`：基于文章库回答投资研究问题的项目内 skill。

## 快速开始

首次使用先准备虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install DrissionPage
```

查看当前文章处理状态：

```bash
python3 tools/article_workflow.py status
```

只下载链接池里还没处理的文章：

```bash
.venv/bin/python tools/wechat_drission_export.py
```

如果提示 `No pending articles.`，说明 `data/links_manifest.json` 里的文章都已经处理过。想重新下载已有文章：

```bash
.venv/bin/python tools/wechat_drission_export.py --force
```

## 收集更多文章链接并下载

如果你有公众号主页、专辑页、历史页或搜索结果页 URL，用下面这条命令。把示例 URL 换成真实链接：

```bash
.venv/bin/python tools/wechat_drission_collect_links.py 'https://mp.weixin.qq.com/mp/appmsgalbum?...' --merge --download
```

这条命令会做三件事：

1. 打开页面并自动向下滚动，等待更多文章加载。
2. 把发现的新文章链接合并进 `gongzhonghao.json`。
3. 刷新 `data/links_manifest.json`，并下载新增待处理文章。

如果页面有“加载更多”按钮，可以加：

```bash
.venv/bin/python tools/wechat_drission_collect_links.py 'https://mp.weixin.qq.com/mp/appmsgalbum?...' --merge --download --click-more
```

如果你不传 URL，脚本会尝试从已保存的 HTML 里发现专辑入口：

```bash
.venv/bin/python tools/wechat_drission_collect_links.py --merge --download
```

批量下载时想放慢速度：

```bash
.venv/bin/python tools/wechat_drission_collect_links.py --merge --download --delay 5
```

DrissionPage 浏览器登录态保存在 `.browser_profile/drission_wechat/`，后续重复运行通常不需要每篇都重新验证。

## 只更新链接清单或手册

从 `gongzhonghao.json` 增量刷新处理清单；已有文章会保留原来的 `raw/html` 和 `raw/text` 文件名，新增链接会追加为新的待处理记录：

```bash
python3 tools/article_workflow.py init
```

把已经保存到 `raw/html/` 或 `raw/text/` 的文章清洗成结构化 JSON：

```bash
python3 tools/article_workflow.py ingest
```

重新生成长期配置操作手册：

```bash
python3 tools/article_workflow.py manual
```

如果你手动保存了非标准文件名，可以先尝试自动归档：

```bash
python3 tools/article_workflow.py adopt
```

## 本地文章检索

用 skill 自带检索脚本从 `articles/` 和 `raw/text/` 中取原文证据：

```bash
python3 .ai/skills/jinjiancheng-investing/scripts/search_articles.py "防守型账户" --limit 5
python3 .ai/skills/jinjiancheng-investing/scripts/search_articles.py "英伟达 NVDA 减仓" --limit 8
python3 .ai/skills/jinjiancheng-investing/scripts/search_articles.py "不满仓 金字塔加仓 现金" --limit 6 --json
```

常用主题可以参考：

```text
.ai/skills/jinjiancheng-investing/references/query-patterns.md
```

## 项目内 Skill

skill 路径：

```text
.ai/skills/jinjiancheng-investing/
```

它不复制 378 篇全文，而是负责规定分析流程：

1. 先读 `.ai/skills/jinjiancheng-investing/references/framework.md`。
2. 再按 `.ai/skills/jinjiancheng-investing/references/query-patterns.md` 扩展关键词。
3. 用 `scripts/search_articles.py` 检索 2-5 条本地文章证据。
4. 回答时区分“原文观点、框架推断、当前市场数据缺口”。

适合的问题：

- “按金渐成框架怎么看 NVDA？”
- “总结他关于防守型账户的观点。”
- “他为什么强调不满仓？”
- “如果标普大跌 15%，按他的体系怎么处理？”

校验 skill 结构：

```bash
python3 /Users/huanbin.wu/.codex/skills/.system/skill-creator/scripts/quick_validate.py .ai/skills/jinjiancheng-investing
```

## 输出原则

- 只做投资研究辅助，不生成自动买卖指令。
- 每条观点尽量保留来源文章，方便回溯。
- 不把历史价格节点机械当作今天可执行节点。
- 涉及当前价格、估值、财报、利率、流动性时，需要用最新市场数据重新校验。
