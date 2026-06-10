from abc import ABC, abstractmethod
from src.models import RawItem


class BaseFetcher(ABC):
    @abstractmethod
    def fetch(self) -> list[RawItem]:
        """抓取并返回标准化条目列表，单个来源失败应捕获异常后返回空列表"""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源名称，用于日志和存储标记"""
        ...
