"""Almacenamiento local de correos en SQLite (un único archivo, sin servidor)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from types import TracebackType

from canditrack.models import Email

DEFAULT_DB_PATH = Path("canditrack.db")

# Versión del esquema; se guarda en la propia base de datos (PRAGMA user_version) para
# poder migrar las tablas en el futuro sin romper bases de datos existentes.
SCHEMA_VERSION = 1

_MIGRATIONS = {
    1: """
        CREATE TABLE emails (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            subject TEXT NOT NULL,
            date TEXT NOT NULL,          -- ISO 8601 con zona horaria
            snippet TEXT NOT NULL,
            body TEXT NOT NULL,
            html_text TEXT NOT NULL
        );
    """,
}

# Las consultas se montan con f-strings solo a partir de estos nombres fijos y de "?";
# los datos van siempre como parámetros, así que no hay riesgo de inyección SQL.
_COLUMNS = ("id", "thread_id", "sender", "subject", "date", "snippet", "body", "html_text")

# SQLite limita el número de parámetros por consulta: los IN (...) se hacen por trozos.
_CHUNK = 500


class EmailCache:
    """Guarda los correos ya descargados para no volver a pedirlos a Gmail."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self._conn = sqlite3.connect(path)
        self._migrate()

    def get_many(self, ids: Iterable[str]) -> dict[str, Email]:
        """Los correos guardados con esos IDs (los que no estén, no aparecen)."""
        ids = list(ids)
        found: dict[str, Email] = {}
        for start in range(0, len(ids), _CHUNK):
            chunk = ids[start : start + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM emails WHERE id IN ({placeholders})",
                chunk,
            )
            for row in rows:
                email = _from_row(row)
                found[email.id] = email
        return found

    def save_many(self, emails: Iterable[Email]) -> None:
        """Guarda (o sustituye) los correos, todos en una misma transacción."""
        with self._conn:
            self._conn.executemany(
                f"INSERT OR REPLACE INTO emails ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(_COLUMNS))})",
                [_to_row(e) for e in emails],
            )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> EmailCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"La base de datos usa el esquema v{version}, más nuevo que el que entiende "
                f"esta versión de CandiTrack (v{SCHEMA_VERSION}). Actualiza CandiTrack."
            )
        for target in range(version + 1, SCHEMA_VERSION + 1):
            with self._conn:
                self._conn.executescript(_MIGRATIONS[target])
                self._conn.execute(f"PRAGMA user_version = {target}")


def _to_row(email: Email) -> tuple[str, ...]:
    return (
        email.id,
        email.thread_id,
        email.sender,
        email.subject,
        email.date.isoformat(),
        email.snippet,
        email.body,
        email.html_text,
    )


def _from_row(row: tuple[str, ...]) -> Email:
    id_, thread_id, sender, subject, date, snippet, body, html_text = row
    return Email(
        id=id_,
        thread_id=thread_id,
        sender=sender,
        subject=subject,
        date=datetime.fromisoformat(date),
        snippet=snippet,
        body=body,
        html_text=html_text,
    )
