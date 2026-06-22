"""HuggingFace Daily Papers fetcher.

通过 https://huggingface.co/api/daily_papers?date=YYYY-MM-DD 获取每日精选论文。
返回的 RawItem 中：
  - source = "HFDailyPapers"
  - categories 中第一项为 "upvotes:N"，第二项为 "githubStars:N"（若有）
  - abstract 优先使用 ai_summary（更精炼），回退到原始 summary
"""

import logging
from datetime import date as Date, timedelta, datetime, timezone

import httpx

from src.fetcher.base import BaseFetcher
from src.models import RawItem
from src.storage.db import make_item_id

logger = logging.getLogger(__name__)

API_URL = "https://huggingface.co/api/daily_papers"
USER_AGENT = "Mozilla/5.0 (compatible; llm-research-agent/1.0)"


class HFDailyPapersFetcher(BaseFetcher):
    def __init__(self, lookback_days: int = 8, min_upvotes: int = 0, timeout: float = 15.0):
        self.lookback_days = lookback_days
        self.min_upvotes = min_upvotes
        self.timeout = timeout

    @property
    def source_name(self) -> str:
        return "HFDailyPapers"

    def fetch(self) -> list[RawItem]:
        results: list[RawItem] = []
        seen_ids: set[str] = set()

        today = Date.today()
        with httpx.Client(timeout=self.timeout, headers={"User-Agent": USER_AGENT}) as client:
            for offset in range(self.lookback_days):
                day = today - timedelta(days=offset)
                params = {"date": day.isoformat()}
                try:
                    resp = client.get(API_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning(f"[HFDailyPapers] fetch {day.isoformat()} failed: {e}")
                    continue

                if not isinstance(data, list):
                    continue

                for entry in data:
                    paper = entry.get("paper") if isinstance(entry, dict) else None
                    if not paper:
                        continue
                    arxiv_id = paper.get("id", "").strip()
                    if not arxiv_id or arxiv_id in seen_ids:
                        continue

                    upvotes = int(paper.get("upvotes") or 0)
                    if upvotes < self.min_upvotes:
                        continue

                    title = (paper.get("title") or "").strip().replace("\n", " ")
                    if not title:
                        continue

                    abstract = (paper.get("ai_summary") or paper.get("summary") or "").strip()
                    abstract = abstract.replace("\n", " ")

                    pub = paper.get("publishedAt") or paper.get("submittedOnDailyAt") or ""
                    if pub:
                        # 形如 "2025-01-14T18:50:05.000Z"，归一化成 ISO
                        try:
                            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                            published = dt.isoformat()
                        except Exception:
                            published = datetime.now(tz=timezone.utc).isoformat()
                    else:
                        published = datetime.now(tz=timezone.utc).isoformat()

                    authors_list = paper.get("authors") or []
                    authors = [a.get("name", "") for a in authors_list if isinstance(a, dict)]
                    authors = [a for a in authors if a][:5]

                    # 把 upvotes / githubStars 塞到 categories（不改 model schema）
                    categories: list[str] = [f"upvotes:{upvotes}"]
                    gh_stars = paper.get("githubStars")
                    if gh_stars:
                        categories.append(f"githubStars:{gh_stars}")
                    gh_repo = paper.get("githubRepo")
                    if gh_repo:
                        categories.append(f"githubRepo:{gh_repo}")
                    ai_kws = paper.get("ai_keywords") or []
                    if isinstance(ai_kws, list):
                        for kw in ai_kws[:5]:
                            if isinstance(kw, str):
                                categories.append(f"hfkw:{kw}")

                    url = f"https://huggingface.co/papers/{arxiv_id}"
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                    raw = RawItem(
                        id=make_item_id({"source": "arxiv", "id": f"http://arxiv.org/abs/{arxiv_id}v1"}),
                        title=title,
                        abstract=abstract,
                        url=url,
                        source=self.source_name,
                        lang="en",
                        published=published,
                        authors=authors,
                        categories=categories,
                        pdf_url=pdf_url,
                    )
                    results.append(raw)
                    seen_ids.add(arxiv_id)

        logger.info(
            f"[HFDailyPapers] fetched {len(results)} papers across {self.lookback_days} days "
            f"(min_upvotes={self.min_upvotes})"
        )
        return results


def get_upvotes(item: RawItem) -> int:
    """从 categories 中读出 upvotes，便于排序。无则返回 0。"""
    for c in item.categories or []:
        if c.startswith("upvotes:"):
            try:
                return int(c.split(":", 1)[1])
            except ValueError:
                return 0
    return 0


def get_github_stars(item: RawItem) -> int:
    for c in item.categories or []:
        if c.startswith("githubStars:"):
            try:
                return int(c.split(":", 1)[1])
            except ValueError:
                return 0
    return 0
