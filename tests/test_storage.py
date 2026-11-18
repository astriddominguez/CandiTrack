import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest

from canditrack.models import Email
from canditrack.storage import SCHEMA_VERSION, EmailCache


def make_email(msg_id: str = "m1", subject: str = "Hola", **kwargs) -> Email:
    fields = {
        "id": msg_id,
        "thread_id": "t1",
        "sender": "RRHH <rrhh@empresa.com>",
        "subject": subject,
        "date": datetime(2026, 11, 17, 9, 30, tzinfo=UTC),
        "snippet": "snippet",
        "body": "cuerpo\ncon saltos",
        "html_text": "texto del HTML",
    }
    return Email(**(fields | kwargs))


def test_saved_emails_are_returned_unchanged(tmp_path):
    madrid = timezone(timedelta(hours=1))
    emails = [make_email("a"), make_email("b", date=datetime(2026, 1, 2, 3, 4, tzinfo=madrid))]

    with EmailCache(tmp_path / "c.db") as cache:
        cache.save_many(emails)
        found = cache.get_many(["a", "b", "missing"])

    assert found == {"a": emails[0], "b": emails[1]}


def test_data_persists_after_reopening(tmp_path):
    path = tmp_path / "c.db"
    with EmailCache(path) as cache:
        cache.save_many([make_email("a")])

    with EmailCache(path) as cache:
        assert list(cache.get_many(["a"])) == ["a"]


def test_saving_same_id_replaces_it(tmp_path):
    with EmailCache(tmp_path / "c.db") as cache:
        cache.save_many([make_email("a", subject="v1")])
        cache.save_many([make_email("a", subject="v2")])

        assert cache.get_many(["a"])["a"].subject == "v2"


def test_get_many_handles_more_ids_than_sqlite_parameter_limit(tmp_path):
    ids = [f"m{i}" for i in range(1500)]
    with EmailCache(tmp_path / "c.db") as cache:
        cache.save_many(make_email(i) for i in ids)

        assert len(cache.get_many(ids)) == 1500


def test_schema_version_is_recorded(tmp_path):
    path = tmp_path / "c.db"
    EmailCache(path).close()

    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "c.db"
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="Actualiza CandiTrack"):
        EmailCache(path)
