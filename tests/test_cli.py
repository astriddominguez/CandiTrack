from datetime import UTC, datetime

from canditrack import cli
from canditrack.models import Email

SENT_AT = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)


class FakeSource:
    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        return [
            Email(
                id="1",
                thread_id="t",
                sender="rrhh@empresa.com",
                subject="Entrevista",
                date=datetime(2026, 11, 17, 9, 30, tzinfo=UTC),
                snippet="",
                body="",
            )
        ]


def test_fetch_command_prints_emails(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_credentials", lambda *a: object())
    monkeypatch.setattr(cli.GmailSource, "from_credentials", lambda creds: FakeSource())

    cli.main(["fetch", "-q", "newer_than:1d"])

    out = capsys.readouterr().out
    assert f"{SENT_AT.astimezone():%Y-%m-%d %H:%M}" in out
    assert "rrhh@empresa.com" in out
    assert "Entrevista" in out
