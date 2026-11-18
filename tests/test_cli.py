import argparse
from datetime import UTC, datetime

import pytest

from canditrack import cli
from canditrack.models import Email

SENT_AT = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)


def make_email(sender: str, subject: str, day: int = 17, msg_id: str = "1") -> Email:
    return Email(
        id=msg_id,
        thread_id="t",
        sender=sender,
        subject=subject,
        date=datetime(2026, 11, day, 9, 30, tzinfo=UTC),
        snippet="",
        body="",
    )


class FakeSource:
    def __init__(self, emails: list[Email]) -> None:
        self.emails = emails
        self.calls: list[tuple[str, int]] = []

    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        self.calls.append((query, max_results))
        return self.emails[:max_results]


@pytest.fixture
def use_source(monkeypatch):
    def install(emails: list[Email]) -> FakeSource:
        source = FakeSource(emails)
        monkeypatch.setattr(cli, "get_credentials", lambda *a: object())
        monkeypatch.setattr(cli.GmailSource, "from_credentials", lambda creds: source)
        return source

    return install


def test_fetch_command_prints_emails(use_source, capsys):
    use_source([make_email("rrhh@empresa.com", "Entrevista")])

    cli.main(["fetch", "-q", "newer_than:1d"])

    out = capsys.readouterr().out
    assert f"{SENT_AT.astimezone():%Y-%m-%d %H:%M}" in out
    assert "rrhh@empresa.com" in out
    assert "Entrevista" in out


LINKEDIN = "LinkedIn <jobs-noreply@linkedin.com>"


def test_track_shows_latest_status_per_application(use_source, capsys):
    source = use_source(
        [
            make_email(LINKEDIN, "Ana, se ha enviado tu solicitud a Acme", day=10, msg_id="1"),
            make_email(
                LINKEDIN, "Tu solicitud para el puesto de Backend Dev en Acme", day=12, msg_id="2"
            ),
            make_email(LINKEDIN, "Globex ha visto tu solicitud", day=11, msg_id="3"),
            make_email("amigo@example.com", "¿Quedamos?", day=13, msg_id="4"),
        ]
    )

    cli.main(["track", "-p", "linkedin", "--since", "2w", "-n", "50"])

    out = capsys.readouterr().out
    first, second = out.splitlines()[:2]
    assert "rechazada" in first
    assert "Acme" in first
    assert "Backend Dev" in first
    assert "vista" in second
    assert "Globex" in second
    assert "2 candidaturas (4 correos revisados)" in out
    assert "Aviso" not in out
    assert source.calls == [("from:(jobs-noreply@linkedin.com) newer_than:14d", 50)]


def test_track_uses_all_platforms_by_default_and_warns_at_max(use_source, capsys):
    source = use_source([make_email("x@example.com", "Hola", msg_id=str(i)) for i in range(3)])

    cli.main(["track", "-n", "3"])

    query, _ = source.calls[0]
    for sender in ("jobs-noreply@linkedin.com", "pushinfojobs", "indeedapply@indeed.com"):
        assert sender in query
    assert query.endswith("newer_than:30d")
    assert "Aviso: se ha llegado al máximo de 3 correos" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("value", "expected"),
    [("7d", "7d"), ("2w", "14d"), ("6M", "6m"), ("1y", "1y"), (" 30d ", "30d")],
)
def test_parse_period(value, expected):
    assert cli.parse_period(value) == expected


@pytest.mark.parametrize("value", ["", "7", "d", "3x", "0d", "-1d", "1.5m"])
def test_parse_period_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_period(value)


def test_track_rejects_unknown_platform(use_source):
    use_source([])

    with pytest.raises(SystemExit):
        cli.main(["track", "-p", "glassdoor"])
