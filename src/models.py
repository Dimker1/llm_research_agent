from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawItem:
    """采集层输出的标准化条目"""
    id: str
    title: str
    abstract: str
    url: str
    source: str          # 'arxiv' | '量子位' | '机器之心' | ...
    lang: str            # 'zh' | 'en'
    published: str       # ISO 8601
    authors: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    pdf_url: str = ""


@dataclass
class AnalyzedItem:
    """LLM 处理层输出，包含原始字段 + 分析结果"""
    # 原始字段
    id: str
    title: str
    abstract: str
    url: str
    source: str
    lang: str
    published: str
    authors: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    pdf_url: str = ""
    # 分析结果
    relevance_score: int = 0
    direction: str = "other"   # pretraining | post_training | agent | other
    summary_zh: str = ""
    keywords: list = field(default_factory=list)
    reason: str = ""

    @classmethod
    def from_raw(cls, raw: RawItem, **analysis_kwargs) -> "AnalyzedItem":
        return cls(
            id=raw.id,
            title=raw.title,
            abstract=raw.abstract,
            url=raw.url,
            source=raw.source,
            lang=raw.lang,
            published=raw.published,
            authors=raw.authors,
            categories=raw.categories,
            pdf_url=raw.pdf_url,
            **analysis_kwargs,
        )
