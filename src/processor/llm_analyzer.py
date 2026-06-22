import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.models import RawItem, AnalyzedItem

logger = logging.getLogger(__name__)

# ── 后端选择规则 ──────────────────────────────────────────────────────────────
# 优先级：OPENAI_API_KEY > ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN
#
# OpenAI 兼容（DeepSeek / MiniMax / 任意 OpenAI 格式代理）：
#   export OPENAI_API_KEY="sk-xxx"
#   export OPENAI_BASE_URL="https://api.deepseek.com"   # DeepSeek
#   export OPENAI_BASE_URL="https://api.minimax.chat/v1" # MiniMax
#   model 填对应平台的模型名，如 deepseek-chat / MiniMax-Text-01
#
# Anthropic（Claude 官方或代理）：
#   export ANTHROPIC_API_KEY="sk-ant-xxx"
#   export ANTHROPIC_BASE_URL="..."   # 可选，使用代理时设置
#   model 填 Claude 模型名，如 claude-sonnet-4-5-20251001 / Claude-Sonnet-4.6
# ─────────────────────────────────────────────────────────────────────────────


def _detect_backend() -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"


def _make_client(backend: str):
    if backend == "openai":
        from openai import OpenAI
        return OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
    else:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        kwargs = {"api_key": api_key}
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        return anthropic.Anthropic(**kwargs)


def _call_api(backend: str, client, model: str, max_tokens: int, prompt: str) -> str:
    """统一调用，返回模型输出文本。"""
    if backend == "openai":
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user","content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    else:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()


# ── 单条 prompt（保留作为 fallback） ─────────────────────────────────────────
ANALYZE_PROMPT = """你是一名专注于大语言模型研究的 AI 助手。请分析以下内容并返回 JSON。

## 内容信息
标题：{title}
来源：{source}
摘要：{abstract}

## 研究方向定义
本项目聚焦以下三个方向（不含多模态/视觉/纯计算机视觉）：
- **pretraining**：LLM 预训练、模型架构（Transformer/MoE等）、扩展律、数据配比、上下文长度、推理效率、量化、知识蒸馏
- **post_training**：指令微调（SFT）、偏好优化（DPO/KTO/GRPO等）、RLHF、对齐、安全性、幻觉、评测基准、LoRA/PEFT、模型合并
- **agent**：LLM Agent、工具调用、CoT推理、RAG、代码生成、多智能体、规划、测试时计算（o1风格）

## 分析任务
1. **相关性打分** (0-10)：与上述三个方向的相关程度
   - 0-3: 基本无关（多模态、视觉、机器人等无关方向均为此类）
   - 4-5: 轻微相关
   - 6-7: 明显相关
   - 8-10: 核心方向内容
2. **方向分类**：从 [pretraining, post_training, agent, other] 中选一个最匹配的
3. **中文摘要**：用 3-5 句话概括核心贡献（如果是中文内容则直接精炼）
   注意：摘要中不能包含双引号（"），改用书名号《》或顿号
4. **关键词**：提取 3-5 个技术关键词（英文缩写保留，如 DPO/MoE/RAG）

## 输出格式（严格 JSON，不要任何其他内容）
{{
  "relevance_score": <0-10的整数>,
  "direction": "<pretraining|post_training|agent|other>",
  "summary_zh": "<3-5句中文摘要，不含双引号>",
  "keywords": ["kw1", "kw2", "kw3"],
  "reason": "<一句话说明打分理由，不含双引号>"
}}"""


# ── 批量 prompt（一次评 N 条，节省 token） ───────────────────────────────────
BATCH_ANALYZE_PROMPT = """你是一名专注于大语言模型研究的 AI 助手。请分析以下 {n} 条内容，并对**每一条**返回一个 JSON 对象，按编号顺序合并到一个 JSON 数组中。

## 研究方向定义
- **pretraining**：LLM 预训练、模型架构（Transformer/MoE等）、扩展律、数据配比、上下文长度、推理效率、量化、知识蒸馏
- **post_training**：指令微调（SFT）、偏好优化（DPO/KTO/GRPO等）、RLHF、对齐、安全性、幻觉、评测基准、LoRA/PEFT、模型合并
- **agent**：LLM Agent、工具调用、CoT推理、RAG、代码生成、多智能体、规划、测试时计算（o1风格）

## 评分标准（0-10）
- 0-3: 基本无关（多模态、视觉、机器人等）
- 4-5: 轻微相关
- 6-7: 明显相关
- 8-10: 核心方向内容

## 待分析内容

{items_block}

## 输出格式（严格 JSON 数组，不要任何其他内容、不要 markdown 代码块）
[
  {{
    "idx": 1,
    "relevance_score": <0-10>,
    "direction": "<pretraining|post_training|agent|other>",
    "summary_zh": "<3-5句中文摘要，不含双引号>",
    "keywords": ["kw1","kw2","kw3"],
    "reason": "<一句话理由，不含双引号>"
  }},
  ...
]
请严格保证数组长度等于 {n}，且 idx 从 1 到 {n}。"""


def _format_items_block(items: list[RawItem], abstract_max_chars: int) -> str:
    chunks = []
    for i, item in enumerate(items, 1):
        abstract = (item.abstract or "")[:abstract_max_chars]
        chunks.append(
            f"[{i}] 标题：{item.title}\n"
            f"    来源：{item.source}\n"
            f"    摘要：{abstract}"
        )
    return "\n\n".join(chunks)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


class LLMAnalyzer:
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20251001",
        max_tokens: int = 512,
        min_score: int = 5,
        max_retries: int = 2,
        abstract_max_chars: int = 2000,
        batch_size: int = 5,
        concurrency: int = 3,
        item_sleep: float = 0.0,
    ):
        self.backend = _detect_backend()
        self.client = _make_client(self.backend)
        self.model = model
        self.max_tokens = max_tokens
        self.min_score = min_score
        self.max_retries = max_retries
        self.abstract_max_chars = abstract_max_chars
        self.batch_size = max(1, batch_size)
        self.concurrency = max(1, concurrency)
        self.item_sleep = item_sleep
        logger.info(
            f"[LLMAnalyzer] backend={self.backend}, model={self.model}, "
            f"batch_size={self.batch_size}, concurrency={self.concurrency}"
        )

    # ── 通用 LLM 调用：含重试与 rate-limit 处理 ──
    def _call_llm_raw(self, prompt: str, max_tokens: Optional[int] = None) -> Optional[str]:
        for attempt in range(self.max_retries + 1):
            try:
                return _call_api(
                    self.backend, self.client, self.model,
                    max_tokens or self.max_tokens, prompt,
                )
            except Exception as e:
                msg = str(e).lower()
                if "rate" in msg or "429" in msg:
                    wait = 30 * (attempt + 1)
                    logger.warning(f"[LLMAnalyzer] rate limit, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"[LLMAnalyzer] API error attempt={attempt+1}: {e}")
                    if attempt < self.max_retries:
                        time.sleep(2)
        return None

    # ── 单条分析（fallback） ──
    def analyze_item(self, item: RawItem) -> Optional[AnalyzedItem]:
        prompt = ANALYZE_PROMPT.format(
            title=item.title,
            source=item.source,
            abstract=(item.abstract or "")[: self.abstract_max_chars],
        )
        text = self._call_llm_raw(prompt)
        if text is None:
            return None
        try:
            cleaned = _strip_code_fence(text)
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
            result = json.loads(cleaned)
        except Exception as e:
            logger.warning(f"[LLMAnalyzer] single-parse failed: {e}; raw={text[:200]}")
            return None

        return AnalyzedItem.from_raw(
            item,
            relevance_score=int(result.get("relevance_score", 0)),
            direction=result.get("direction", "other"),
            summary_zh=result.get("summary_zh", ""),
            keywords=result.get("keywords", []),
            reason=result.get("reason", ""),
        )

    # ── 批量分析一组（最多 batch_size 条） ──
    def _analyze_batch(self, batch: list[RawItem]) -> list[Optional[AnalyzedItem]]:
        n = len(batch)
        items_block = _format_items_block(batch, self.abstract_max_chars)
        prompt = BATCH_ANALYZE_PROMPT.format(n=n, items_block=items_block)

        # 每条输出约 150-300 tokens（中文摘要 3-5 句 + JSON 结构），留 1.5x 余量
        budget = max(self.max_tokens * n * 2, 1024)
        text = self._call_llm_raw(prompt, max_tokens=budget)
        if text is None:
            logger.warning(f"[LLMAnalyzer] batch returned None, falling back to single")
            return [self.analyze_item(it) for it in batch]

        cleaned = _strip_code_fence(text)
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            logger.warning(f"[LLMAnalyzer] batch no JSON array, falling back; raw={text[:200]}")
            return [self.analyze_item(it) for it in batch]

        try:
            arr = json.loads(match.group(0))
        except Exception as e:
            logger.warning(f"[LLMAnalyzer] batch JSON parse failed: {e}; falling back")
            return [self.analyze_item(it) for it in batch]

        if not isinstance(arr, list):
            return [self.analyze_item(it) for it in batch]

        # 用 idx 对齐；缺漏的 fallback 单条
        by_idx: dict[int, dict] = {}
        for entry in arr:
            if isinstance(entry, dict) and "idx" in entry:
                try:
                    by_idx[int(entry["idx"])] = entry
                except (ValueError, TypeError):
                    pass

        results: list[Optional[AnalyzedItem]] = []
        for i, item in enumerate(batch, 1):
            entry = by_idx.get(i)
            if entry is None:
                logger.debug(f"[LLMAnalyzer] batch missing idx={i}, single fallback")
                results.append(self.analyze_item(item))
                continue
            try:
                results.append(AnalyzedItem.from_raw(
                    item,
                    relevance_score=int(entry.get("relevance_score", 0)),
                    direction=entry.get("direction", "other"),
                    summary_zh=entry.get("summary_zh", ""),
                    keywords=entry.get("keywords", []) or [],
                    reason=entry.get("reason", ""),
                ))
            except Exception as e:
                logger.warning(f"[LLMAnalyzer] batch entry {i} build failed: {e}")
                results.append(self.analyze_item(item))
        return results

    # ── 总入口：批量 + 并发 ──
    def batch_analyze(self, items: list[RawItem]) -> list[AnalyzedItem]:
        total = len(items)
        if total == 0:
            return []

        # 切 batch
        batches = [
            items[i : i + self.batch_size]
            for i in range(0, total, self.batch_size)
        ]
        logger.info(
            f"[LLMAnalyzer] analyzing {total} items in {len(batches)} batches "
            f"(batch_size={self.batch_size}, concurrency={self.concurrency})"
        )

        results: list[AnalyzedItem] = []
        completed = 0
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            future_to_idx = {
                pool.submit(self._analyze_batch, batch): bi
                for bi, batch in enumerate(batches)
            }
            for fut in as_completed(future_to_idx):
                bi = future_to_idx[fut]
                try:
                    batch_results = fut.result()
                except Exception as e:
                    logger.error(f"[LLMAnalyzer] batch {bi} crashed: {e}")
                    batch_results = []

                for analyzed in batch_results:
                    if analyzed is None:
                        continue
                    if analyzed.relevance_score < self.min_score:
                        continue
                    results.append(analyzed)
                completed += 1
                logger.info(
                    f"[LLMAnalyzer] batch {completed}/{len(batches)} done "
                    f"(kept so far: {len(results)})"
                )

        logger.info(
            f"[LLMAnalyzer] {total} in → {len(results)} relevant (score >= {self.min_score})"
        )
        return results
