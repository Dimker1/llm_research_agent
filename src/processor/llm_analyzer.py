import json
import logging
import os
import re
import time
from typing import Optional

import anthropic

from src.models import RawItem, AnalyzedItem

logger = logging.getLogger(__name__)


def _make_client() -> anthropic.Anthropic:
    """支持 ANTHROPIC_AUTH_TOKEN（京东云）和标准 ANTHROPIC_API_KEY 两种认证方式"""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)

ANALYZE_PROMPT = """你是一名专注于大语言模型研究的 AI 助手。请分析以下内容并返回 JSON。

## 内容信息
标题：{title}
来源：{source}
摘要：{abstract}

## 分析任务
1. **相关性打分** (0-10)：与「LLM预训练 / 后训练(RLHF/DPO等) / LLM Agent」三个方向的相关程度
   - 0-3: 基本无关
   - 4-5: 轻微相关
   - 6-7: 明显相关
   - 8-10: 核心方向论文
2. **方向分类**：从 [pretraining, post_training, agent, other] 中选一个最匹配的
3. **中文摘要**：用 3-5 句话概括核心贡献（如果是中文内容则直接精炼）
   注意：摘要中不能包含双引号（"），改用书名号《》或顿号
4. **关键词**：提取 3-5 个技术关键词（英文缩写保留，如 RLHF/DPO/MoE）

## 输出格式（严格 JSON，不要任何其他内容）
{{
  "relevance_score": <0-10的整数>,
  "direction": "<pretraining|post_training|agent|other>",
  "summary_zh": "<3-5句中文摘要，不含双引号>",
  "keywords": ["kw1", "kw2", "kw3"],
  "reason": "<一句话说明打分理由，不含双引号>"
}}"""


class LLMAnalyzer:
    def __init__(
        self,
        model: str = "Claude-Sonnet-4.6",
        max_tokens: int = 512,
        min_score: int = 5,
        max_retries: int = 2,
        abstract_max_chars: int = 2000,
    ):
        self.client = _make_client()
        self.model = model
        self.max_tokens = max_tokens
        self.min_score = min_score
        self.max_retries = max_retries
        self.abstract_max_chars = abstract_max_chars

    def _call_llm(self, prompt: str) -> Optional[dict]:
        for attempt in range(self.max_retries + 1):
            try:
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = message.content[0].text.strip()
                # 去掉 ```json ... ``` 包裹
                if text.startswith("```"):
                    text = re.sub(r"^```[a-z]*\n?", "", text)
                    text = re.sub(r"\n?```$", "", text)
                # 提取第一个完整 JSON 对象（防止模型在 JSON 后附加说明文字）
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    text = match.group(0)
                return json.loads(text)
            except json.JSONDecodeError as e:
                logger.warning(f"[LLMAnalyzer] JSON parse error (attempt {attempt+1}): {e}")
                if attempt < self.max_retries:
                    time.sleep(1)
            except anthropic.RateLimitError:
                logger.warning(f"[LLMAnalyzer] rate limit, waiting 30s...")
                time.sleep(30)
            except Exception as e:
                logger.error(f"[LLMAnalyzer] API error (attempt {attempt+1}): {e}")
                if attempt < self.max_retries:
                    time.sleep(2)
        return None

    def analyze_item(self, item: RawItem) -> Optional[AnalyzedItem]:
        prompt = ANALYZE_PROMPT.format(
            title=item.title,
            source=item.source,
            abstract=item.abstract[: self.abstract_max_chars],
        )
        result = self._call_llm(prompt)
        if result is None:
            return None

        return AnalyzedItem.from_raw(
            item,
            relevance_score=int(result.get("relevance_score", 0)),
            direction=result.get("direction", "other"),
            summary_zh=result.get("summary_zh", ""),
            keywords=result.get("keywords", []),
            reason=result.get("reason", ""),
        )

    def batch_analyze(self, items: list[RawItem]) -> list[AnalyzedItem]:
        """批量分析，过滤低相关条目，返回高质量结果"""
        results = []
        total = len(items)

        for i, item in enumerate(items, 1):
            logger.info(f"[LLMAnalyzer] analyzing {i}/{total}: {item.title[:60]}...")
            analyzed = self.analyze_item(item)

            if analyzed is None:
                logger.warning(f"[LLMAnalyzer] skipped (analyze failed): {item.id}")
                continue

            if analyzed.relevance_score < self.min_score:
                logger.debug(
                    f"[LLMAnalyzer] skipped (score={analyzed.relevance_score}): {item.title[:60]}"
                )
                continue

            results.append(analyzed)
            # 控制 API 调用频率
            time.sleep(0.3)

        logger.info(
            f"[LLMAnalyzer] {total} in → {len(results)} relevant (score >= {self.min_score})"
        )
        return results
