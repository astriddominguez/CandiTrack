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
        self.emails = {e.id: e for e in emails}
        self.calls: list[tuple[str, int]] = []
        self.downloaded: list[str] = []

    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        return self.get_messages(self.list_ids(query, max_results))

    def list_ids(self, query: str = "", max_results: int = 50) -> list[str]:
        self.calls.append((query, max_results))
        return list(self.emails)[:max_results]

    def get_messages(self, ids: list[str]) -> list[Email]:
        self.downloaded.extend(ids)
        return [self.emails[i] for i in ids]


@pytest.fixture
def use_source(monkeypatch, tmp_path):
    # Trabajar en una carpeta temporal: el canditrack.db por defecto se crea ahí, no en el repo.
    monkeypatch.chdir(tmp_path)

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
    assert "2 candidaturas (4 correos revisados, 4 descargados de Gmail)" in out
    assert "Aviso" not in out
    assert source.calls == [("from:(jobs-noreply@linkedin.com) newer_than:14d", 50)]


def test_track_reuses_local_database_on_next_run(use_source, capsys, tmp_path):
    source = use_source([make_email(LINKEDIN, "Globex ha visto tu solicitud")])
    db = tmp_path / "datos" / "mis-correos.db"
    db.parent.mkdir()

    cli.main(["track", "--db", str(db)])
    cli.main(["track", "--db", str(db)])

    out = capsys.readouterr().out
    assert "1 correos revisados, 1 descargados de Gmail" in out
    assert "1 correos revisados, 0 descargados de Gmail" in out
    assert source.downloaded == ["1"]
    assert db.exists()


def test_track_uses_all_platforms_by_default_and_warns_at_max(use_source, capsys):
    source = use_source([make_email("x@example.com", "Hola", msg_id=str(i)) for i in range(3)])

    cli.main(["track", "-n", "3"])

    query, _ = source.calls[0]
    for sender in ("jobs-noreply@linkedin.com", "pushinfojobs", "indeedapply@indeed.com"):
        assert sender in query
    assert query.endswith("newer_than:30d")
    assert "Aviso: se ha llegado al máximo de 3 correos" in capsys.readouterr().out


def test_parse_period_converts_to_argparse_error():
    assert cli.parse_period("2w") == "14d"
    with pytest.raises(argparse.ArgumentTypeError, match="periodo no válido"):
        cli.parse_period("3x")


@pytest.mark.parametrize("value", ["0", "-5", "abc", "1.5"])
def test_positive_int_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.positive_int(value)


def test_track_rejects_unknown_platform(use_source):
    use_source([])

    with pytest.raises(SystemExit):
        cli.main(["track", "-p", "glassdoor"])


CONFIG = """
[track]
platforms = ["indeed"]
since = "90d"
max = 7
db = "datos.db"
"""


def test_track_takes_defaults_from_config_file(use_source, tmp_path):
    source = use_source([])
    (tmp_path / "canditrack.toml").write_text(CONFIG, encoding="utf-8")

    cli.main(["track"])

    query, max_results = source.calls[0]
    assert query.startswith("from:(indeedapply@indeed.com ")
    assert query.endswith("newer_than:90d")
    assert max_results == 7
    assert (tmp_path / "datos.db").exists()


def test_command_line_options_override_config_file(use_source, tmp_path):
    source = use_source([])
    (tmp_path / "canditrack.toml").write_text(CONFIG, encoding="utf-8")

    cli.main(["track", "-p", "linkedin", "-s", "7d", "-n", "3", "--db", "otra.db"])

    assert source.calls == [("from:(jobs-noreply@linkedin.com) newer_than:7d", 3)]
    assert (tmp_path / "otra.db").exists()
    assert not (tmp_path / "datos.db").exists()


def test_track_uses_explicit_config_path(use_source, tmp_path):
    source = use_source([])
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    (config_dir / "mi.toml").write_text(CONFIG, encoding="utf-8")

    cli.main(["track", "--config", str(config_dir / "mi.toml")])

    assert source.calls[0][1] == 7
    assert (config_dir / "datos.db").exists()  # relativa a la carpeta del archivo


def test_invalid_config_file_stops_with_clear_error(use_source, tmp_path, capsys):
    source = use_source([])
    (tmp_path / "canditrack.toml").write_text('[track]\nplatforms = ["glassdoor"]\n')

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["track"])

    assert exit_info.value.code == 2
    assert "plataforma desconocida 'glassdoor'" in capsys.readouterr().err
    assert source.calls == []  # no llega a conectarse a Gmail
