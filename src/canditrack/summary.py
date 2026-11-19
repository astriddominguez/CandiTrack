"""Resumen de candidaturas: cuántas se enviaron en un periodo y en qué estado están ahora."""

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from canditrack.models import EventType
from canditrack.tracking import Application

DEFAULT_PERIOD = "60d"

_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_UNITS = {"d": ("día", "días"), "m": ("mes", "meses"), "y": ("año", "años")}


@dataclass(frozen=True)
class Counts:
    applied: int = 0
    alive: int = 0  # enviadas o vistas: todavía sin respuesta negativa
    rejected: int = 0
    closed: int = 0

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(
            self.applied + other.applied,
            self.alive + other.alive,
            self.rejected + other.rejected,
            self.closed + other.closed,
        )


@dataclass(frozen=True)
class Summary:
    period: str  # en el formato de Gmail ("60d", "3m", "1y")
    start: date
    end: date
    rows: dict[str, Counts]  # nombre para mostrar de la plataforma -> recuentos

    @property
    def total(self) -> Counts:
        return sum(self.rows.values(), Counts())


def period_start(period: str, today: date) -> date:
    """Primer día de un periodo ("60d", "3m", "1y") que termina hoy."""
    amount, unit = int(period[:-1]), period[-1]
    if unit == "d":
        return today - timedelta(days=amount)
    months = amount if unit == "m" else amount * 12
    year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
    # Si el día no existe en ese mes (31 de febrero...), el último día del mes.
    day = min(today.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def summarize(
    applications: Iterable[Application],
    platforms: dict[str, str],
    period: str,
    today: date,
) -> Summary:
    """Cuenta las candidaturas *enviadas* en el periodo, con su estado actual.

    `platforms` es {nombre interno: nombre para mostrar}, en el orden en que se quieren las
    filas. Solo cuentan las candidaturas con un correo de envío dentro del periodo (en hora
    local): el rechazo de una solicitud enviada antes del periodo no cuenta.
    """
    start = period_start(period, today)

    counts = {name: Counts() for name in platforms}
    for app in applications:
        if app.platform not in counts or not _submitted_in(app, start, today):
            continue
        counts[app.platform] += Counts(
            applied=1,
            alive=int(app.status in (EventType.SUBMITTED, EventType.VIEWED)),
            rejected=int(app.status is EventType.REJECTED),
            closed=int(app.status is EventType.CLOSED),
        )

    return Summary(
        period=period,
        start=start,
        end=today,
        rows={platforms[name]: c for name, c in counts.items()},
    )


def _submitted_in(app: Application, start: date, end: date) -> bool:
    return any(
        e.type is EventType.SUBMITTED and start <= e.date.astimezone().date() <= end
        for e in app.events
    )


def format_summary(summary: Summary) -> str:
    """El resumen como texto plano (para la terminal y, más adelante, para el correo)."""
    header = ("", "Postuladas", "Vivas", "Rechazadas", "Cerradas")
    rows = [*summary.rows.items(), ("Total", summary.total)]
    width = max(len(name) for name, _ in rows)

    lines = [f"CandiTrack · {_describe(summary)}", ""]
    lines.append(f"{header[0]:<{width}}  " + "  ".join(header[1:]))
    for name, c in rows:
        values = (c.applied, c.alive, c.rejected, c.closed)
        cells = "  ".join(f"{v:>{len(h)}}" for v, h in zip(values, header[1:], strict=True))
        lines.append(f"{name:<{width}}  {cells}")
    lines += ["", "Vivas = enviadas o vistas, sin respuesta negativa todavía."]
    return "\n".join(lines)


def _describe(summary: Summary) -> str:
    """ "últimos 60 días (20 sep – 19 nov 2026)"."""
    amount, unit = int(summary.period[:-1]), summary.period[-1]
    singular, plural = _UNITS[unit]
    span = f"último {singular}" if amount == 1 else f"últimos {amount} {plural}"
    start, end = summary.start, summary.end
    start_text = f"{start.day} {_MONTHS[start.month - 1]}"
    if start.year != end.year:
        start_text += f" {start.year}"
    return f"{span} ({start_text} – {end.day} {_MONTHS[end.month - 1]} {end.year})"
