# LLM Research Agent

自动追踪 LLM 前沿技术的周报 Agent，聚焦**预训练 / 后训练 / LLM Agent** 三大方向，支持 arXiv 论文 + 中英文社区多源聚合，每周生成结构化 HTML 周报，可选推送到 Telegram。

## 📖 在线阅读

**归档首页**（所有历史周报）：https://dimker1.github.io/llm_research_agent/

每次运行后自动更新，点击对应周次即可阅读。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

程序会自动检测使用哪个后端：优先使用 `OPENAI_API_KEY`，未设置则使用 Anthropic。

**方案 A：DeepSeek（推荐，性价比高）**
```bash
export OPENAI_API_KEY="sk-xxx"
export OPENAI_BASE_URL="https://api.deepseek.com"
# settings.yaml 中 model 填: deepseek-chat
```

**方案 B：MiniMax**
```bash
export OPENAI_API_KEY="xxx"
export OPENAI_BASE_URL="https://api.minimax.chat/v1"
# settings.yaml 中 model 填: MiniMax-Text-01
```

**方案 C：OpenAI 官方**
```bash
export OPENAI_API_KEY="sk-xxx"
# 不需要设置 OPENAI_BASE_URL
# settings.yaml 中 model 填: gpt-4o-mini
```

**方案 D：Claude（Anthropic 官方）**
```bash
export ANTHROPIC_API_KEY="sk-ant-xxx"
# settings.yaml 中 model 填: claude-haiku-4-5-20251001
```

**方案 E：Claude（京东云等第三方代理）**
```bash
export ANTHROPIC_API_KEY="pk-xxx"
export ANTHROPIC_BASE_URL="http://your-proxy.example.com/anthropic"
# settings.yaml 中 model 填代理支持的模型名，如 Claude-Sonnet-4.6
```

同时在 `config/settings.yaml` 中设置对应的模型名：
```yaml
llm:
  model: deepseek-chat   # 改成对应平台的模型名
```

Telegram 推送（可选）：
```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
```

### 3. 运行一次

```bash
# 生成当前周的周报（覆盖本周一到今天）
python -m src.main

# 指定 ISO 周次（补跑历史周）
python -m src.main --week 2026-W23

# 调试模式：只抓取+过滤，不调用 LLM
python -m src.main --dry-run

# 跳过 Telegram 推送
python -m src.main --no-telegram
```

输出文件为 `weekly/2026-W24.html`，用浏览器直接打开即可。

### 4. 启动定时调度（本地生产部署）

```bash
python -m src.scheduler
```

默认每周一北京时间 09:00 运行，进程需常驻。调度时间可在 `config/settings.yaml` 的 `scheduler` 节修改。

### 5. Docker 部署

```bash
docker build -t llm-research-agent .
docker run -d \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -e TELEGRAM_BOT_TOKEN="..." \
  -e TELEGRAM_CHAT_ID="..." \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/weekly:/app/weekly \
  llm-research-agent
```

## 项目结构

```
llm-research-agent/
├── .github/workflows/daily-digest.yml  # GitHub Actions 定时任务（每周一）
├── config/
│   ├── keywords.yaml   # 关键词配置（三大方向 + 排除词）
│   ├── sources.yaml    # 数据源配置（arXiv / RSS / 开关控制）
│   └── settings.yaml   # 全局参数（模型、阈值、调度时间等）
├── src/
│   ├── main.py         # 主入口（周报流程）
│   ├── scheduler.py    # APScheduler 定时调度
│   ├── models.py       # 数据模型（RawItem / AnalyzedItem）
│   ├── fetcher/
│   │   ├── arxiv_fetcher.py   # arXiv 论文抓取
│   │   └── rss_fetcher.py     # RSS 源抓取
│   ├── processor/
│   │   ├── dedup.py           # 去重（SQLite）
│   │   ├── keyword_filter.py  # 关键词粗筛
│   │   └── llm_analyzer.py    # Claude API 分析与评分
│   ├── storage/
│   │   └── db.py              # SQLite 存储
│   └── publisher/
│       ├── html_writer.py      # HTML 周报生成
│       ├── markdown_writer.py  # Markdown 格式生成
│       └── telegram_sender.py  # Telegram 推送
├── weekly/             # 周报 HTML 输出目录（weekly/2026-W24.html）
├── data/               # SQLite 数据库（data/digest.db）
├── requirements.txt
└── Dockerfile
```

## 配置说明

### 启用更多数据源（`config/sources.yaml`）

将对应数据源的 `enabled: false` 改为 `enabled: true`：

```yaml
rss:
  - name: 机器之心
    url: https://www.jiqizhixin.com/rss
    enabled: true   # 改为 true 启用（注意：官方 RSS 可能失效，需自建 RSSHub）
```

已内置数据源：

| 来源 | 类型 | 语言 | 默认状态 |
|------|------|------|----------|
| arXiv (cs.CL / cs.AI / cs.LG) | 论文 | EN | 启用 |
| 量子位 | 资讯 | ZH | 启用 |
| 雷峰网 | 资讯 | ZH | 启用 |
| 宝玉博客 | 翻译/分析 | ZH | 启用 |
| AheadOfAI (Sebastian Raschka) | 博客 | EN | 启用 |
| Import AI (Jack Clark) | 博客 | EN | 启用 |
| Interconnects (Nathan Lambert) | 博客 | EN | 启用 |
| The Gradient | 博客 | EN | 启用 |
| Last Week in AI | 周报 | EN | 启用 |
| Chip Huyen Blog | 博客 | EN | 启用 |
| Eugene Yan | 博客 | EN | 启用 |
| Simon Willison | 博客 | EN | 启用 |
| AI Snake Oil | 分析 | EN | 启用 |
| The ML Engineer | 周报 | EN | 启用 |
| Hugging Face Blog | 官方博客 | EN | 启用 |
| OpenAI Blog | 官方博客 | EN | 启用 |
| DeepMind Blog | 官方博客 | EN | 启用 |
| Alignment Forum | 社区 | EN | 启用 |
| r/MachineLearning | 社区 | EN | 启用 |
| r/LocalLLaMA | 社区 | EN | 启用 |
| 机器之心 | 资讯 | ZH | 禁用（RSS 不稳定）|
| GitHub Trending (Python/AI) | 项目 | EN | 禁用（需自建 RSSHub）|
| Towards AI / TDS | 博客 | EN | 禁用（噪音较多）|

### 调整关键词（`config/keywords.yaml`）

在对应方向下添加关键词，支持中英文：

```yaml
directions:
  post_training:
    en:
      - your_new_keyword
    zh:
      - 你的新关键词
```

三大方向说明：
- `pretraining`：预训练、架构、扩展律、数据配比、MoE 等
- `post_training`：RLHF、DPO、SFT、对齐、评测、幻觉等
- `agent`：Agent、RAG、CoT、工具调用、代码生成、数学推理等

### 调整质量阈值（`config/settings.yaml`）

```yaml
llm:
  min_relevance_score: 4   # 0-10，提高则减少噪音但可能漏掉内容

pipeline:
  max_llm_candidates: 120  # 关键词筛选后最多送 LLM 分析的条数
  target_total_items: 20   # 最终周报保留的总条目数
  max_items_per_direction: 10  # 单方向最多展示条数
```

## GitHub Actions 部署

1. Fork 本仓库
2. 在仓库 **Settings → Secrets and variables → Actions** 中添加：
   - `ANTHROPIC_API_KEY`（必填）
   - `TELEGRAM_BOT_TOKEN`（可选）
   - `TELEGRAM_CHAT_ID`（可选）
3. GitHub Actions 将在每周一 UTC 01:00（北京时间 09:00）自动运行

每次运行结果会以 `weekly/YYYY-WNN.html` 的形式 commit 回仓库，可直接在 GitHub Pages 浏览。

> **注意**：`.github/workflows/daily-digest.yml` 中 `run` 命令需使用 `python -m src.main`，不支持 `--mode` 参数。

## 处理流程

```
arXiv + RSS 抓取
    ↓
SQLite 去重（已分析过的跳过）
    ↓
关键词粗筛（命中三大方向之一）
    ↓
优先级裁剪（最多 120 条送 LLM）
    ↓
Claude API 评分 + 分类 + 中文摘要
    ↓
存入 SQLite，查询整周高分条目
    ↓
生成 HTML 周报 → weekly/YYYY-WNN.html
    ↓
（可选）Telegram 推送
```
