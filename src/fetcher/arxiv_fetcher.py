import logging
from datetime import datetime, timedelta, timezone

import arxiv

from src.fetcher.base import BaseFetcher
from src.models import RawItem
from src.storage.db import make_item_id

logger = logging.getLogger(__name__)


class ArxivFetcher(BaseFetcher):
    def __init__(self, categories: list[str], max_results: int = 200, lookback_hours: int = 36):
        self.categories = categories
        self.max_results = max_results
        self.lookback_hours = lookback_hours

    @property
    def source_name(self) -> str:
        return "arxiv"

    def fetch(self) -> list[RawItem]:
        query = " OR ".join(f"cat:{c}" for c in self.categories)
        client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)

        search = arxiv.Search(
            query=query,
            max_results=self.max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=self.lookback_hours)
        results = []

        try:
            for paper in client.results(search):
                pub = paper.published
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                if pub < cutoff:
                    break

                raw_item = RawItem(
                    id="",  # 先占位，下面设置
                    title=paper.title.strip().replace("\n", " "),
                    abstract=paper.summary.strip().replace("\n", " "),
                    url=paper.entry_id,
                    source="arxiv",
                    lang="en",
                    published=paper.published.isoformat(),
                    authors=[a.name for a in paper.authors[:5]],
                    categories=paper.categories,
                    pdf_url=paper.pdf_url,
                )
                # 用 entry_id 生成稳定 ID
                raw_item.id = make_item_id({"source": "arxiv", "id": paper.entry_id})
                results.append(raw_item)

        except Exception as e:
            logger.error(f"[ArxivFetcher] fetch failed: {e}")

        logger.info(f"[ArxivFetcher] fetched {len(results)} papers")
        return results
