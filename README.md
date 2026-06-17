# 金渐成投资框架 Skill

一个**工具无关的通用 AI Skill**，基于金渐成公众号 384 篇文章构建。任何兼容 AGENTS.md 或 SKILL.md 的 AI agent（Claude Code、Cursor、WorkBuddy、Codex CLI 等）都能直接加载使用，按金渐成的投资体系回答美股配置、仓位管理和风险控制问题。

## 能做什么

- **分析美股/ETF**：按三层账户（进取、稳健、防守）定位单只资产，检查是否满足"第一或唯一"标准
- **交易节点复盘**：回溯历史建仓、加仓、减仓、做 T 的记录和逻辑
- **宏观判断**：结合美元周期、利率、流动性判断当前周期位置
- **风险控制**：不满仓、低成本/负成本、金字塔加仓等纪律检查
- **人格问答**：回答博主的投资哲学、人生价值观、教育理念、社会观察

## 项目结构

```
├── AGENTS.md            ← Claude Code / Cursor / Codex CLI 入口
├── SKILL.md             ← WorkBuddy 入口
├── README.md
├── scripts/             ← 可执行工具
│   ├── search_articles.py   ← 本地全文检索（核心）
│   ├── ingest.py            ← 数据管道：清洗、结构化、生成手册
│   ├── export_drission.py   ← 浏览器下载文章
│   ├── collect_drission.py  ← 浏览器收集链接
│   ├── link_harvester.py    ← 从 HTML/TXT 提取链接
│   └── rename.py            ← 文件重命名
├── references/          ← AI agent 加载的领域知识
│   ├── 金渐成-人格画像.md   ← 博主全貌
│   ├── framework.md         ← 投资框架总结
│   ├── query-patterns.md    ← 检索模式指南
│   └── pipeline.md          ← 数据管道指南
├── data/                ← 元数据和链接清单
├── articles/            ← 384 篇结构化 JSON
├── raw/                 ← HTML + 清洗 TXT
├── pdf/                 ← 232 篇 PDF
└── manual/              ← 人工整理的框架和手册
```

## AI Agent 如何使用

不同工具的入口文件：

| 工具 | 入口 | 自动加载 |
|------|------|---------|
| Claude Code | `AGENTS.md` | ✅ |
| Cursor | `AGENTS.md` | ✅ |
| Codex CLI / OpenAI | `AGENTS.md` | ✅ |
| WorkBuddy | `SKILL.md` | ✅ |

Agent 加载后的标准流程：先读 `references/金渐成-人格画像.md` 了解博主 → 读 `references/framework.md` 理解框架 → 按 `references/query-patterns.md` 扩展关键词 → 运行检索命令 → 按回答结构输出。

## 本地检索

```bash
python scripts/search_articles.py "防守型账户" --limit 5
python scripts/search_articles.py "英伟达 NVDA 减仓 负成本" --limit 8 --json
python scripts/search_articles.py "不满仓 金字塔加仓 做T" --limit 6
```

## 数据管道

更新文章数据：

```bash
# 查看状态
python scripts/ingest.py status

# 初始化链接清单
python scripts/ingest.py init

# 浏览器下载文章（DrissionPage，推荐）
python scripts/export_drission.py

# 结构化提取
python scripts/ingest.py ingest

# 生成操作手册
python scripts/ingest.py manual
```

更多细节见 `references/pipeline.md`。

## 输出原则

- 研究辅助，不生成买卖指令
- 每条观点保留来源，方便回溯
- 历史价格节点不等于今天可执行节点
- 当前市场数据需实时校验
