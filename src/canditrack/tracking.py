"""Agrupa los eventos detectados en candidaturas y calcula su estado actual."""

import hashlib
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from canditrack.models import ApplicationEvent, EventType


@dataclass(frozen=True)
class Application:
    """Una candidatura: todos sus eventos y el estado según el más reciente."""

    platform: str
    company: str
    position: str | None
    status: EventType
    updated: datetime
    events: tuple[ApplicationEvent, ...]

    @property
    def id(self) -> str:
        """Identificador estable: el mismo mientras no cambien plataforma, empresa y puesto.

        Las candidaturas se recalculan en cada ejecución (no se guardan), así que no hay un
        ID de base de datos: se deriva de lo que identifica a la candidatura.
        """
        key = f"{self.platform}|{_key(self.company)}|{_key(self.position or '')}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]


def build_applications(events: Iterable[ApplicationEvent]) -> list[Application]:
    """Agrupa los eventos por candidatura; las más recientes primero.

    Una candidatura es (plataforma, empresa, puesto). Algunos correos no dicen el puesto
    (p. ej. "se ha enviado tu solicitud a Acme" en LinkedIn): si en esa empresa solo hay un
    puesto conocido, esos eventos se asignan a él; si hay varios, quedan aparte, porque no
    se puede saber a cuál pertenecen.
    """
    by_company: dict[tuple[str, str], list[ApplicationEvent]] = defaultdict(list)
    for event in events:
        by_company[(event.platform, _key(event.company))].append(event)

    applications: list[Application] = []
    for company_events in by_company.values():
        by_position: dict[str | None, list[ApplicationEvent]] = defaultdict(list)
        for event in company_events:
            by_position[_key(event.position) if event.position else None].append(event)

        known = [p for p in by_position if p is not None]
        if len(known) == 1 and None in by_position:
            by_position[known[0]].extend(by_position.pop(None))

        applications.extend(_application(group) for group in by_position.values())

    return sorted(applications, key=lambda a: a.updated, reverse=True)


def _application(events: list[ApplicationEvent]) -> Application:
    events = sorted(events, key=lambda e: e.date)
    latest = events[-1]
    position = next((e.position for e in reversed(events) if e.position), None)
    return Application(
        platform=latest.platform,
        company=latest.company,
        position=position,
        status=latest.type,
        updated=latest.date,
        events=tuple(events),
    )


def _key(text: str) -> str:
    return " ".join(text.casefold().split())


def filter_applications(
    applications: Iterable[Application],
    *,
    platform: str | None = None,
    status: EventType | None = None,
    company: str | None = None,
    updated_since: date | None = None,
) -> list[Application]:
    """Filtra candidaturas; los filtros que se dejan en None no se aplican.

    `company` busca el texto dentro del nombre de la empresa sin distinguir mayúsculas ni
    acentos ("tecnologias" encuentra "PSS Tecnologías"). `updated_since` compara con la
    fecha local del evento más reciente.
    """
    wanted = _fold(company) if company else None
    return [
        app
        for app in applications
        if (platform is None or app.platform == platform)
        and (status is None or app.status is status)
        and (wanted is None or wanted in _fold(app.company))
        and (updated_since is None or app.updated.astimezone().date() >= updated_since)
    ]


def _fold(text: str) -> str:
    """Minúsculas, sin acentos y con los espacios normalizados, para comparar textos."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_accents.casefold().split())
