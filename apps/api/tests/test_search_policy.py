from datetime import datetime, timedelta, timezone

from app.search_policy import HourlySearchBudget, SearchCache, compact_search_queries


def test_compact_search_queries_returns_at_most_two_distinct_queries():
    queries = compact_search_queries('深圳', '心内科', '胸痛')

    assert len(queries) == 2
    assert len(set(queries)) == 2


def test_search_cache_expires_entries():
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    cache = SearchCache(ttl=timedelta(minutes=30), clock=lambda: now)
    cache.set('key', 'value')
    assert cache.get('key') == 'value'

    now = now + timedelta(minutes=31)
    assert cache.get('key') is None


def test_search_cache_evicts_oldest_entry_when_capacity_is_reached():
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    cache = SearchCache(ttl=timedelta(minutes=30), max_entries=2, clock=lambda: now)
    cache.set('one', 1)
    cache.set('two', 2)
    cache.set('three', 3)

    assert cache.get('one') is None
    assert cache.get('two') == 2
    assert cache.get('three') == 3


def test_hourly_budget_blocks_after_limit_and_reopens_after_window():
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    budget = HourlySearchBudget(limit=2, clock=lambda: now)
    assert budget.allow()
    budget.record()
    assert budget.allow()
    budget.record()
    assert not budget.allow()

    now = now + timedelta(hours=1, seconds=1)
    assert budget.allow()
