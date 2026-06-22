"""Synthesizer：把一周的高分条目转化成 Agent 视角的产出。

5 个能力：
  1. tldr               —— 一段话总结本周 LLM 圈的整体动向
  2. top_picks          —— 编辑精选 Top 3 必读，附"为什么必读"
  3. themes             —— 把条目聚成 5-8 个主题（如"长上下文"、"o1-style 推理"）
  4. weekly_diff        —— 与上周对比："延续主题" vs "新出现"
  5. learn_keywords     —— 从高分项目中提炼新的研究方向词，回写到独立 yaml

这一层调用 LLM 是"批量级"调用：每个能力 1 次（最多 2 次），相比逐条分析非常便宜。
"""

import json
import logging
import re
from datetime import date as Date
from pathlib import Path
from typing import Optional

import yaml

from src.models import AnalyzedItem
from src.processor.llm_analyzer import LLMAnalyzer

logger = logging.getLogger(__name__)


# ── Prompt 模板 ──────────────────────────────────────────────────────────────

TLDR_PROMPT = """你是一名 LLM 前沿研究的资深观察者。下面是本周（{week_label}）从 arXiv、HuggingFace Daily Papers 与多个研究博客聚合后的高分条目（共 {n} 条）。

请用 **3-5 句中文** 总结本周 LLM 研究圈的整体动向。要求：
- 提炼出 2-3 个**最显著的趋势/主题**（例如"长上下文持续突破"、"o1 风格推理扩散"）
- 不要逐条罗列论文
- 语气客观、专业、可读性强
- 不要用双引号"，需要时改用《》或顿号

## 本周条目
{items_block}

## 输出（直接输出 3-5 句话，不要任何标题或前缀）
"""


THEMES_PROMPT = """你是一名 LLM 前沿研究的内容编辑。请把下面 {n} 条本周高分内容**聚类成 5-8 个主题**（每个主题至少 2 条，不要把每条都单独成主题）。

## 输出严格 JSON 数组（不要 markdown 代码块、不要任何其他内容）：
[
  {{
    "name": "<10 字以内的主题中文名，如：长上下文与稀疏注意力>",
    "summary": "<1-2 句话说明该主题本周的核心进展>",
    "item_ids": ["<id1>", "<id2>", ...]   // 必须是下面给出的 id 之一，且必须 ≥2 个
  }},
  ...
]

要求：
- 主题数 5-8 个
- 把每条 id 分配到**最多一个**主题；非主流条目可以不被任何主题包含
- summary 不要双引号"
- name 不要超过 14 个字

## 本周条目
{items_block}
"""


TOP_PICKS_PROMPT = """你是一名严格的 LLM 研究内容编辑。从下面 {n} 条本周内容中，挑出 **最值得深读的 3 条**（不要更多）。

## 输出严格 JSON 数组（不要 markdown 代码块、不要任何其他内容）：
[
  {{
    "id": "<对应条目的 id>",
    "title": "<原标题>",
    "why": "<2-3 句话说明为什么值得读，需指出具体贡献而非套话；不要双引号>"
  }},
  ...
]

挑选标准（按重要性递减）：
1. 提出新方法/新洞察，而非渐进改进
2. 由有影响力的团队（OpenAI/DeepMind/Anthropic/Meta/各 top lab）发布
3. 有清晰的工程价值或可复现资源
4. 与三大方向（pretraining/post_training/agent）核心重合

## 本周条目
{items_block}
"""


DIFF_PROMPT = """你是一名 LLM 前沿研究的观察者。下面给出**上周**与**本周**的主题列表，请分析差异。

## 上周（{prev_week}）的主题
{prev_themes}

## 本周（{cur_week}）的主题
{cur_themes}

## 任务
判断本周哪些主题**延续**自上周（含演进），哪些是**新出现**的。请返回严格 JSON：

{{
  "continued": [
    {{"theme": "<本周主题名>", "note": "<1 句话说明本周相对上周有何进展，不要双引号>"}}
  ],
  "new": [
    {{"theme": "<本周主题名>", "note": "<1 句话说明这是新方向的原因，不要双引号>"}}
  ]
}}

不要 markdown 代码块、不要任何其他内容。
"""


LEARN_KW_PROMPT = """你是一名 LLM 研究关键词维护者。下面是本周高分条目的标题与关键词列表。

请提炼 **5-10 个新出现/正在升温的英文技术关键词**，用于扩充关键词词库。要求：
- 必须是**多词短语**或**专有缩写**（避免 "model"、"learning" 这类太泛的词）
- 优先考虑当前还不是常见词、但近期反复出现的（如 "test-time compute", "speculative decoding"）
- 全部用小写英文输出
- 输出严格 JSON 数组：["kw1", "kw2", ...]

## 本周内容
{items_block}

不要 markdown 代码块、不要任何其他内容。
"""


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _format_items_for_synth(items: list[AnalyzedItem], max_chars_per_item: int = 220) -> str:
    """精简版条目块，用于 synthesize 阶段的 prompt（每条只给标题+方向+精简摘要）"""
    chunks = []
    for it in items:
        summary = (it.summary_zh or it.abstract or "")[:max_chars_per_item]
        chunks.append(
            f"id={it.id} | dir={it.direction} | score={it.relevance_score} | src={it.source}\n"
            f"  标题：{it.title}\n"
            f"  摘要：{summary}"
        )
    return "\n\n".join(chunks)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _safe_parse_json(text: str, expected: str = "array") -> Optional[object]:
    """从模型输出里尽力提取 JSON。expected = 'array' | 'object'"""
    cleaned = _strip_code_fence(text)
    pattern = r"\[.*\]" if expected == "array" else r"\{.*\}"
    m = re.search(pattern, cleaned, re.DOTALL)
    if m:
        cleaned = m.group(0)
    try:
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"[synthesizer] JSON parse failed ({expected}): {e}; raw={text[:200]}")
        return None


# ── 主类 ─────────────────────────────────────────────────────────────────────

class Synthesizer:
    """复用 LLMAnalyzer 的 client/backend，做更高层次的归纳。"""

    def __init__(
        self,
        analyzer: LLMAnalyzer,
        max_items_for_synth: int = 60,
        max_tokens_long: int = 2048,
    ):
        self.analyzer = analyzer
        self.max_items_for_synth = max_items_for_synth
        self.max_tokens_long = max_tokens_long

    def _call(self, prompt: str, max_tokens: Optional[int] = None) -> Optional[str]:
        return self.analyzer._call_llm_raw(prompt, max_tokens=max_tokens or self.max_tokens_long)

    # --- TL;DR ---
    def gen_tldr(self, items: list[AnalyzedItem], week_label: str) -> str:
        if not items:
            return ""
        sub = items[: self.max_items_for_synth]
        prompt = TLDR_PROMPT.format(
            week_label=week_label,
            n=len(sub),
            items_block=_format_items_for_synth(sub, max_chars_per_item=180),
        )
        text = self._call(prompt, max_tokens=600)
        if not text:
            return ""
        return _strip_code_fence(text).strip()

    # --- 主题聚类 ---
    def gen_themes(self, items: list[AnalyzedItem]) -> list[dict]:
        if len(items) < 4:
            return []
        sub = items[: self.max_items_for_synth]
        valid_ids = {it.id for it in sub}
        prompt = THEMES_PROMPT.format(
            n=len(sub),
            items_block=_format_items_for_synth(sub),
        )
        text = self._call(prompt, max_tokens=self.max_tokens_long)
        if not text:
            return []
        parsed = _safe_parse_json(text, expected="array")
        if not isinstance(parsed, list):
            return []

        themes: list[dict] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            summary = (entry.get("summary") or "").strip()
            item_ids = entry.get("item_ids") or []
            if not isinstance(item_ids, list):
                continue
            item_ids = [str(i) for i in item_ids if str(i) in valid_ids]
            if name and len(item_ids) >= 2:
                themes.append({
                    "name": name,
                    "summary": summary,
                    "item_ids": item_ids,
                })
        return themes

    # --- Top 3 必读 ---
    def gen_top_picks(self, items: list[AnalyzedItem]) -> list[dict]:
        if not items:
            return []
        # 只把全局相关性最高的 30 条交给 LLM 选 top 3
        sub = sorted(items, key=lambda x: x.relevance_score, reverse=True)[:30]
        valid = {it.id: it for it in sub}
        prompt = TOP_PICKS_PROMPT.format(
            n=len(sub),
            items_block=_format_items_for_synth(sub),
        )
        text = self._call(prompt, max_tokens=900)
        if not text:
            return []
        parsed = _safe_parse_json(text, expected="array")
        if not isinstance(parsed, list):
            return []

        picks = []
        for entry in parsed[:3]:
            if not isinstance(entry, dict):
                continue
            iid = str(entry.get("id") or "")
            if iid not in valid:
                continue
            picks.append({
                "id": iid,
                "title": valid[iid].title,
                "url": valid[iid].url,
                "why": (entry.get("why") or "").strip(),
            })
        return picks

    # --- 周间对比 ---
    def gen_weekly_diff(
        self,
        cur_themes: list[dict],
        prev_memory: Optional[dict],
        cur_week: str,
    ) -> dict:
        if not prev_memory or not prev_memory.get("themes") or not cur_themes:
            return {"continued": [], "new": []}

        prev_themes_text = "\n".join(
            f"- {t.get('name','')}: {t.get('summary','')}"
            for t in prev_memory["themes"]
        )
        cur_themes_text = "\n".join(
            f"- {t.get('name','')}: {t.get('summary','')}"
            for t in cur_themes
        )
        prompt = DIFF_PROMPT.format(
            prev_week=prev_memory.get("week_label", "?"),
            cur_week=cur_week,
            prev_themes=prev_themes_text,
            cur_themes=cur_themes_text,
        )
        text = self._call(prompt, max_tokens=800)
        if not text:
            return {"continued": [], "new": []}
        parsed = _safe_parse_json(text, expected="object")
        if not isinstance(parsed, dict):
            return {"continued": [], "new": []}
        return {
            "continued": parsed.get("continued") or [],
            "new": parsed.get("new") or [],
        }

    # --- 关键词学习 ---
    def learn_keywords(
        self,
        items: list[AnalyzedItem],
        existing_keywords: set[str],
        learned_path: str = "config/keywords_learned.yaml",
    ) -> list[str]:
        if len(items) < 5:
            return []
        sub = sorted(items, key=lambda x: x.relevance_score, reverse=True)[:40]
        prompt = LEARN_KW_PROMPT.format(
            items_block=_format_items_for_synth(sub, max_chars_per_item=160),
        )
        text = self._call(prompt, max_tokens=400)
        if not text:
            return []
        parsed = _safe_parse_json(text, expected="array")
        if not isinstance(parsed, list):
            return []

        new_kws = []
        existing_lower = {k.lower() for k in existing_keywords}
        for kw in parsed:
            if not isinstance(kw, str):
                continue
            kw = kw.strip().lower()
            # 必须是多词或缩写（含数字/连字符也算）
            if not kw or len(kw) < 3:
                continue
            if kw in existing_lower:
                continue
            new_kws.append(kw)
            existing_lower.add(kw)

        if new_kws:
            self._append_learned_keywords(new_kws, learned_path)

        return new_kws

    @staticmethod
    def _append_learned_keywords(new_kws: list[str], path: str) -> None:
        """把学到的关键词追加到独立的 yaml（不污染主关键词文件）"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if p.exists():
            try:
                existing = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                existing = {}
        history: list[dict] = existing.get("history", [])
        history.append({
            "date": Date.today().isoformat(),
            "keywords": new_kws,
        })
        # 累计 keywords 集合
        all_kws = set(existing.get("keywords", []))
        all_kws.update(new_kws)
        new_doc = {
            "keywords": sorted(all_kws),
            "history": history[-26:],  # 最多保留近半年（26 周）
        }
        p.write_text(
            "# 自动学习的前沿关键词（由 synthesizer 维护）\n# 不要手动编辑\n\n"
            + yaml.safe_dump(new_doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    # --- 一站式 synthesize ---
    def synthesize(
        self,
        items: list[AnalyzedItem],
        week_label: str,
        prev_memory: Optional[dict] = None,
        existing_keywords: Optional[set[str]] = None,
        learned_path: str = "config/keywords_learned.yaml",
    ) -> dict:
        """返回 dict：{tldr, top_picks, themes, weekly_diff, learned_kws}"""
        logger.info(f"[synthesizer] start synthesize for {week_label} ({len(items)} items)")

        tldr = self.gen_tldr(items, week_label)
        logger.info(f"[synthesizer] tldr: {len(tldr)} chars")

        themes = self.gen_themes(items)
        logger.info(f"[synthesizer] themes: {len(themes)}")

        top_picks = self.gen_top_picks(items)
        logger.info(f"[synthesizer] top_picks: {len(top_picks)}")

        weekly_diff = self.gen_weekly_diff(themes, prev_memory, week_label)
        logger.info(
            f"[synthesizer] weekly_diff: continued={len(weekly_diff['continued'])}, "
            f"new={len(weekly_diff['new'])}"
        )

        learned = self.learn_keywords(
            items,
            existing_keywords or set(),
            learned_path=learned_path,
        )
        logger.info(f"[synthesizer] learned_kws: {len(learned)}")

        return {
            "tldr": tldr,
            "top_picks": top_picks,
            "themes": themes,
            "weekly_diff": weekly_diff,
            "learned_kws": learned,
        }
