# 检索模式

回答金渐成框架相关问题前，先用这些模式检索本地文章知识库。先使用精确中文短语，再扩展到相近概念和标的别名。

## 账户与配置

- `防守型账户`: 防守型账户, 防守账户, 稳健账户, 进取型账户, 账户分层, 压舱石, 安全垫, 家庭财富锚
- `家庭资产配置`: 四个钱包, 家庭开支, 备用金, 投资资金, 财富锚, 养老, 教育, 保险, 港险
- `不满仓`: 不满仓, 仓位, 现金, 子弹, 分批, 金字塔加仓, 风险控制, 低成本, 负成本

## 建仓、加仓、持有、减仓

- `建仓`: 建仓, 买入, 低位, 逢低, 左侧, 右侧, 分批, 底仓, 试错
- `加仓`: 加仓, 金字塔加仓, 下跌, 回撤, 暴跌, 越跌越买, 做T, 降成本
- `持有`: 长期持有, 低成本, 负成本, 现金流, 分红, 护城河, 第一, 唯一
- `减仓/卖出`: 减仓, 清仓, 止盈, 卖出, 高位, 高估, 低成本变现, 回收本金, 负成本
- `复盘`: 复盘, 策略过期, 体系迭代, 节点, 错误, 教训, 机会成本

## 宏观周期

- `美元资产`: 美元资产, 美元潮汐, 美联储, 加息, 降息, 美债, 美元现金, 全球配置, 人民币资产
- `利率和流动性`: 利率, 十年期, CPI, 通胀, 衰退, 流动性, 风险偏好, 降息预期
- `美股大跌`: 标普, 纳指, 下跌, 回撤, 暴跌, 熊市, VIX, 恐慌, 金字塔加仓, 不满仓

## 标的与别名

- `NVDA`: NVDA, 英伟达, Nvidia, 黄仁勋, GPU, AI, 算力, 半导体
- `TSLA`: TSLA, 特斯拉, 马斯克, 电动车, 机器人, 自动驾驶
- `AAPL`: AAPL, 苹果, Apple, iPhone, 消费电子
- `MSFT`: MSFT, 微软, Microsoft, OpenAI, 云计算, AI
- `GOOGL`: GOOGL, GOOG, 谷歌, Google, Alphabet, 搜索, 广告
- `AMZN`: AMZN, 亚马逊, Amazon, AWS, 电商, 云计算
- `META`: META, Meta, 脸书, Facebook, Instagram, 元宇宙, 广告
- `BRK`: BRK, 伯克希尔, 巴菲特, Buffett, 保险, 现金
- `TSM`: TSM, 台积电, TSMC, 半导体, 晶圆
- `AMD`: AMD, 超威, 半导体, AI 芯片
- `AVGO`: AVGO, 博通, Broadcom, 半导体, 网络芯片
- `SPY/VOO`: SPY, VOO, 标普, 标普500, S&P 500, 宽基
- `QQQ`: QQQ, 纳指, 纳斯达克, 纳指100, 科技股
- `TLT/美债`: TLT, 美债, 长债, 国债, 债券, 降息
- `BIL/短债`: BIL, 短债, 货币基金, 美元现金, 现金管理

## 示例检索

```bash
python3 .ai/skills/jinjiancheng-investing/scripts/search_articles.py "英伟达 NVDA AI 减仓" --limit 8
python3 .ai/skills/jinjiancheng-investing/scripts/search_articles.py "防守型账户 压舱石 安全垫" --limit 6
python3 .ai/skills/jinjiancheng-investing/scripts/search_articles.py "不满仓 金字塔加仓 现金" --limit 6
python3 .ai/skills/jinjiancheng-investing/scripts/search_articles.py "标普 下跌 15% 加仓" --limit 8
```
