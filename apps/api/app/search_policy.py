"""Cost controls for external web search calls."""

from collections import OrderedDict, deque
from datetime import UTC, datetime, timedelta
from typing import Callable, Generic, TypeVar

T = TypeVar('T')


def compact_search_queries(city: str, specialty: str, query: str) -> tuple[str, str]:
    city = city.strip() or '全国'
    specialty = specialty.strip() or '综合医疗'
    query = query.strip()
    return (
        f'{city} {specialty} 医院 官方网站',
        f'{city} {query or specialty} 医院 科室 挂号',
    )


class SearchCache(Generic[T]):
    def __init__(self, *, ttl: timedelta, max_entries: int = 256, clock: Callable[[], datetime] | None = None) -> None:
        self.ttl = ttl
        self.max_entries = max(1, max_entries)
        self.clock = clock or (lambda: datetime.now(UTC))
        self._values: OrderedDict[str, tuple[datetime, T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        item = self._values.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self.clock() >= expires_at:
            self._values.pop(key, None)
            return None
        self._values.move_to_end(key)
        return value

    def set(self, key: str, value: T) -> None:
        self._values[key] = (self.clock() + self.ttl, value)
        self._values.move_to_end(key)
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)


class HourlySearchBudget:
    def __init__(self, *, limit: int, clock: Callable[[], datetime] | None = None) -> None:
        self.limit = max(0, limit)
        self.clock = clock or (lambda: datetime.now(UTC))
        self._calls: deque[datetime] = deque()

    def _prune(self) -> None:
        cutoff = self.clock() - timedelta(hours=1)
        while self._calls and self._calls[0] <= cutoff:
            self._calls.popleft()

    def allow(self) -> bool:
        self._prune()
        return len(self._calls) < self.limit

    def record(self) -> None:
        self._prune()
        self._calls.append(self.clock())
