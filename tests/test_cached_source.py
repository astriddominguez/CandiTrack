from datetime import UTC, datetime

import pytest

from canditrack.mail import cached
from canditrack.mail.cached import CachedMailSource
from canditrack.models import Email
from canditrack.storage import EmailCache


def make_email(msg_id: str) -> Email:
    return Email(
        id=msg_id,
        thread_id="t",
        sender="x@example.com",
        subject=f"Asunto {msg_id}",
        date=datetime(2026, 11, 17, tzinfo=UTC),
        snippet="",
        body="",
    )


class FakeRemote:
    def __init__(self, ids: list[str], fail_after: int | None = None) -> None:
        self.ids = ids
        self.fail_after = fail_after
        self.list_calls: list[tuple[str, int]] = []
        self.downloaded: list[str] = []

    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        return self.get_messages(self.list_ids(query, max_results))

    def list_ids(self, query: str = "", max_results: int = 50) -> list[str]:
        self.list_calls.append((query, max_results))
        return self.ids[:max_results]

    def get_messages(self, ids: list[str]) -> list[Email]:
        if self.fail_after is not None and len(self.downloaded) >= self.fail_after:
            raise ConnectionError("Gmail no responde")
        self.downloaded.extend(ids)
        return [make_email(i) for i in ids]


@pytest.fixture
def cache(tmp_path):
    with EmailCache(tmp_path / "c.db") as cache:
        yield cache


def test_first_fetch_downloads_everything_and_second_nothing(cache):
    remote = FakeRemote(["c", "b", "a"])
    source = CachedMailSource(remote, cache)

    first = source.fetch("from:x", 10)
    assert [e.id for e in first] == ["c", "b", "a"]
    assert source.downloaded == 3

    second = source.fetch("from:x", 10)
    assert second == first
    assert source.downloaded == 0
    assert remote.downloaded == ["c", "b", "a"]
    assert remote.list_calls == [("from:x", 10), ("from:x", 10)]


def test_only_new_emails_are_downloaded_and_order_is_kept(cache):
    cache.save_many([make_email("b")])
    remote = FakeRemote(["c", "b", "a"])
    source = CachedMailSource(remote, cache)

    emails = source.fetch()

    assert [e.id for e in emails] == ["c", "b", "a"]
    assert remote.downloaded == ["c", "a"]
    assert source.downloaded == 2


def test_progress_is_saved_if_download_breaks_midway(cache, monkeypatch):
    monkeypatch.setattr(cached, "SAVE_EVERY", 2)
    remote = FakeRemote(["a", "b", "c", "d", "e"], fail_after=4)

    with pytest.raises(ConnectionError):
        CachedMailSource(remote, cache).fetch()

    assert sorted(cache.get_many(remote.ids)) == ["a", "b", "c", "d"]
