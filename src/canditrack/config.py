"""Archivo de configuración opcional (canditrack.toml) con los valores por defecto de `track`.

Prioridad: opción en la línea de comandos > archivo de configuración > valor por defecto.

    [track]
    platforms = ["linkedin", "indeed"]   # por defecto, todas
    since = "90d"                        # 7d, 4w, 6m, 1y...
    max = 1000
    db = "canditrack.db"                 # relativa a la carpeta del archivo de configuración
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from canditrack.platforms import PLATFORMS
from canditrack.storage import DEFAULT_DB_PATH

DEFAULT_CONFIG_PATH = Path("canditrack.toml")

_PERIOD = re.compile(r"^(\d+)([dwmy])$")


class ConfigError(Exception):
    """El archivo de configuración no existe, no es TOML válido o tiene valores incorrectos."""


@dataclass(frozen=True)
class TrackConfig:
    platforms: tuple[str, ...] = ()  # vacío = todas
    since: str = "30d"  # ya en el formato de `newer_than:` de Gmail
    max: int = 500
    db: Path = DEFAULT_DB_PATH


@dataclass(frozen=True)
class Config:
    track: TrackConfig = field(default_factory=TrackConfig)


def normalize_period(value: str) -> str:
    """Convierte "7d", "4w", "6m" o "1y" al formato de `newer_than:` de Gmail.

    Lanza ValueError si el periodo no es válido.
    """
    match = _PERIOD.match(value.strip().lower())
    if not match or int(match[1]) == 0:
        raise ValueError(f"periodo no válido: {value!r} (usa p. ej. 7d, 4w, 6m o 1y)")
    amount, unit = int(match[1]), match[2]
    # Gmail no entiende semanas: se pasan a días.
    return f"{amount * 7}d" if unit == "w" else f"{amount}{unit}"


def load_config(path: Path | None = None) -> Config:
    """Lee la configuración.

    Sin `path` se usa ./canditrack.toml si existe (y si no, los valores por defecto). Con
    `path` explícito, el archivo tiene que existir.
    """
    if path is None:
        if not DEFAULT_CONFIG_PATH.exists():
            return Config()
        path = DEFAULT_CONFIG_PATH

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"no existe el archivo de configuración {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} no es TOML válido: {e}") from None

    try:
        return _parse(data, base_dir=path.parent)
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from None


def _parse(data: dict[str, Any], base_dir: Path) -> Config:
    _check_keys(data, {"track"}, "")
    track = data.get("track", {})
    if not isinstance(track, dict):
        raise ConfigError("[track] tiene que ser una sección")
    _check_keys(track, {"platforms", "since", "max", "db"}, "track.")

    defaults = TrackConfig()
    return Config(
        track=TrackConfig(
            platforms=_platforms(track["platforms"]) if "platforms" in track else (),
            since=_since(track["since"]) if "since" in track else defaults.since,
            max=_max(track["max"]) if "max" in track else defaults.max,
            # Una ruta relativa se interpreta desde la carpeta del archivo de configuración.
            db=base_dir / _string(track["db"], "track.db") if "db" in track else defaults.db,
        )
    )


def _check_keys(table: dict[str, Any], allowed: set[str], prefix: str) -> None:
    if unknown := sorted(set(table) - allowed):
        raise ConfigError(
            f"clave desconocida {prefix}{unknown[0]} (válidas: {', '.join(sorted(allowed))})"
        )


def _platforms(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
        raise ConfigError('track.platforms tiene que ser una lista, p. ej. ["linkedin"]')
    for name in value:
        if name not in PLATFORMS:
            raise ConfigError(
                f"plataforma desconocida {name!r} en track.platforms "
                f"(válidas: {', '.join(sorted(PLATFORMS))})"
            )
    return tuple(dict.fromkeys(value))  # sin duplicados, conservando el orden


def _since(value: Any) -> str:
    try:
        return normalize_period(_string(value, "track.since"))
    except ValueError as e:
        raise ConfigError(f"track.since: {e}") from None


def _max(value: Any) -> int:
    # bool es subclase de int en Python: `max = true` no debe colar como 1.
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError("track.max tiene que ser un número entero mayor que 0")
    return value


def _string(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{key} tiene que ser un texto entre comillas")
    return value
