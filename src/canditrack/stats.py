"""Estadísticas por plataforma: qué plataformas te dan respuesta y cuánto tardan.

Sobre las candidaturas *enviadas* en el periodo (como el resumen):

- Con respuesta: la empresa la vio o la rechazó. "Proceso cerrado" no cuenta: es la oferta
  la que se cierra, no la empresa respondiéndote.
- Rechazadas: su estado actual es rechazada.
- Sin respuesta: siguen solo como "enviada" y llevan `stale_days` días o más así.
- Días hasta respuesta: mediana de días entre el envío y la primera respuesta (la mediana,
  y no la media, para que un caso raro no distorsione el número).
"""

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime

from canditrack.models import EventType
from canditrack.platforms import Platform
from canditrack.summary import describe_period, period_start
from canditrack.tracking import Application

DEFAULT_STALE_DAYS = 21

_RESPONSES = (EventType.VIEWED, EventType.REJECTED)


@dataclass(frozen=True)
class PlatformStats:
    sent: int = 0
    responded: int = 0
    rejected: int = 0
    no_response: int = 0
    # Días entre el envío y la primera respuesta de cada candidatura con respuesta.
    response_days: tuple[float, ...] = field(default=(), repr=False)

    @property
    def median_days_to_response(self) -> float | None:
        return statistics.median(self.response_days) if self.response_days else None

    def __add__(self, other: "PlatformStats") -> "PlatformStats":
        return PlatformStats(
            self.sent + other.sent,
            self.responded + other.responded,
            self.rejected + other.rejected,
            self.no_response + other.no_response,
            self.response_days + other.response_days,
        )


@dataclass(frozen=True)
class Stats:
    period: str
    start: date
    end: date
    stale_days: int
    rows: dict[str, PlatformStats]  # nombre interno de la plataforma -> estadísticas
    platforms: dict[str, Platform]

    @property
    def total(self) -> PlatformStats:
        return sum(self.rows.values(), PlatformStats())


def compute_stats(
    applications: Iterable[Application],
    platforms: Iterable[Platform],
    period: str,
    today: date,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> Stats:
    platforms = {p.name: p for p in platforms}
    start = period_start(period, today)
    rows = {name: PlatformStats() for name in platforms}

    for app in applications:
        if app.platform not in rows:
            continue
        sent_at = _submitted_at(app, start, today)
        if sent_at is None:
            continue
        rows[app.platform] += _application_stats(app, sent_at, today, stale_days)

    return Stats(period, start, today, stale_days, rows, platforms)


def _submitted_at(app: Application, start: date, end: date) -> datetime | None:
    """Fecha del primer envío dentro del periodo (en hora local), o None si no hay."""
    return next(
        (
            e.date
            for e in app.events
            if e.type is EventType.SUBMITTED and start <= e.date.astimezone().date() <= end
        ),
        None,
    )


def _application_stats(
    app: Application, sent_at: datetime, today: date, stale_days: int
) -> PlatformStats:
    first_response = next(
        (e.date for e in app.events if e.type in _RESPONSES and e.date >= sent_at), None
    )
    waiting = (today - sent_at.astimezone().date()).days
    return PlatformStats(
        sent=1,
        responded=int(first_response is not None),
        rejected=int(app.status is EventType.REJECTED),
        no_response=int(app.status is EventType.SUBMITTED and waiting >= stale_days),
        response_days=(
            ((first_response - sent_at).total_seconds() / 86400,) if first_response else ()
        ),
    )


def format_stats(stats: Stats) -> str:
    """Las estadísticas como texto plano."""
    header = (
        "",
        "Enviadas",
        "Con respuesta",
        "Rechazadas",
        "Sin respuesta",
        "Días hasta respuesta",
    )
    rows = [(stats.platforms[name].label, s) for name, s in stats.rows.items()]
    rows.append(("Total", stats.total))
    width = max(len(label) for label, _ in rows)

    lines = [
        f"CandiTrack · estadísticas · {describe_period(stats.period, stats.start, stats.end)}",
        "",
        f"{header[0]:<{width}}  " + "  ".join(header[1:]),
    ]
    for label, s in rows:
        values = (
            str(s.sent),
            _with_percent(s.responded, s.sent),
            _with_percent(s.rejected, s.sent),
            _with_percent(s.no_response, s.sent),
            _days(s.median_days_to_response),
        )
        cells = "  ".join(f"{v:>{len(h)}}" for v, h in zip(values, header[1:], strict=True))
        lines.append(f"{label:<{width}}  {cells}")

    lines += [
        "",
        "Con respuesta = vista o rechazada por la empresa.",
        f"Sin respuesta = solo enviada y sin novedades en {stats.stale_days} días o más.",
        "Días hasta respuesta = mediana entre el envío y la primera respuesta.",
    ]
    lines += _caveats(list(stats.platforms.values()))
    return "\n".join(lines)


def _caveats(platforms: list[Platform]) -> list[str]:
    """Avisos sobre plataformas cuyas cifras de respuesta salen más bajas de lo real."""
    neither = [p.label for p in platforms if not p.notifies_views and not p.notifies_rejections]
    no_views = [p.label for p in platforms if not p.notifies_views and p.notifies_rejections]
    no_rejections = [p.label for p in platforms if p.notifies_views and not p.notifies_rejections]
    parts = []
    if neither:
        parts.append(f"{_join(neither)} {_verb(neither)} de vistas ni de rechazos")
    if no_views:
        parts.append(f"{_join(no_views)} {_verb(no_views)} de vistas")
    if no_rejections:
        parts.append(f"{_join(no_rejections)} {_verb(no_rejections)} de rechazos")
    if not parts:
        return []
    return [f"Ojo: {'; '.join(parts)}: sus cifras de respuesta salen más bajas de lo real."]


def _verb(names: list[str]) -> str:
    return "no avisa por correo" if len(names) == 1 else "no avisan por correo"


def _with_percent(part: int, whole: int) -> str:
    return f"{part} ({part / whole:.0%})" if whole else "0"


def _days(days: float | None) -> str:
    if days is None:
        return "-"
    return "<1" if days < 1 else f"{days:.0f}"


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} y {names[-1]}"
