from pathlib import Path

import pytest

from canditrack.config import Config, ConfigError, TrackConfig, load_config, normalize_period


def write(tmp_path: Path, content: str, name: str = "canditrack.toml") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_missing_default_file_gives_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert load_config() == Config()


def test_default_file_is_used_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path, '[track]\nsince = "2w"\n')

    assert load_config().track.since == "14d"


def test_explicit_file_must_exist(tmp_path):
    with pytest.raises(ConfigError, match="no existe"):
        load_config(tmp_path / "otro.toml")


def test_full_config(tmp_path):
    path = write(
        tmp_path,
        """
        [track]
        platforms = ["indeed", "linkedin", "indeed"]
        since = "6M"
        max = 1000
        db = "datos/correos.db"
        """,
    )

    assert load_config(path) == Config(
        track=TrackConfig(
            platforms=("indeed", "linkedin"),
            since="6m",
            max=1000,
            db=tmp_path / "datos" / "correos.db",  # relativa a la carpeta del archivo
        )
    )


def test_absolute_db_path_is_kept(tmp_path):
    path = write(tmp_path, '[track]\ndb = "/var/lib/canditrack/c.db"\n')

    assert load_config(path).track.db == Path("/var/lib/canditrack/c.db")


def test_partial_config_keeps_other_defaults(tmp_path):
    path = write(tmp_path, "[track]\nmax = 50\n")

    assert load_config(path).track == TrackConfig(max=50)


def test_empty_file_gives_defaults(tmp_path):
    assert load_config(write(tmp_path, "")) == Config()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("[track\n", "no es TOML válido"),
        ("[trak]\n", "clave desconocida trak"),
        ("[track]\nplataforms = []\n", "clave desconocida track.plataforms"),
        ('track = "x"\n', r"\[track\] tiene que ser una sección"),
        ('[track]\nplatforms = "linkedin"\n', "tiene que ser una lista"),
        ('[track]\nplatforms = ["glassdoor"]\n', "plataforma desconocida 'glassdoor'"),
        ('[track]\nsince = "3x"\n', "track.since: periodo no válido"),
        ("[track]\nsince = 30\n", "track.since tiene que ser un texto"),
        ("[track]\nmax = 0\n", "track.max tiene que ser un número entero mayor que 0"),
        ('[track]\nmax = "500"\n', "track.max tiene que ser"),
        ("[track]\nmax = true\n", "track.max tiene que ser"),
        ("[track]\ndb = 1\n", "track.db tiene que ser un texto"),
    ],
)
def test_invalid_config_is_reported_with_file_name(tmp_path, content, message):
    path = write(tmp_path, content)

    with pytest.raises(ConfigError, match=message) as error:
        load_config(path)
    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("7d", "7d"), ("2w", "14d"), ("6M", "6m"), ("1y", "1y"), (" 30d ", "30d")],
)
def test_normalize_period(value, expected):
    assert normalize_period(value) == expected


@pytest.mark.parametrize("value", ["", "7", "d", "3x", "0d", "-1d", "1.5m"])
def test_normalize_period_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="periodo no válido"):
        normalize_period(value)
