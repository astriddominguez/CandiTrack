from datetime import UTC, date, datetime

import pytest

from canditrack.models import ApplicationEvent, EventType
from canditrack.summary import Counts, Summary, format_summary, period_start, summarize
from canditrack.tracking import build_applications

LABELS = {"linkedin": "LinkedIn", "infojobs": "InfoJobs", "indeed": "Indeed"}
TODAY = date(2026, 11, 19)


def event(type_, month, day, company="Acme", platform="linkedin", position="Dev"):
    # A mediodía UTC: el mismo día en cualquier zona horaria europea o americana.
    return ApplicationEvent(
        type=type_,
        platform=platform,
        company=company,
        position=position,
        date=datetime(2026, month, day, 12, tzinfo=UTC),
        email_id=f"{company}-{type_}-{month}-{day}",
        thread_id="t",
    )


def test_counts_applications_sent_in_period_by_current_status():
    events = [
        event(EventType.SUBMITTED, 11, 2, "Viva"),
        event(EventType.SUBMITTED, 11, 3, "Vista"),
        event(EventType.VIEWED, 11, 5, "Vista"),
        event(EventType.SUBMITTED, 10, 4, "Rechazo"),
        event(EventType.REJECTED, 11, 10, "Rechazo"),
        event(EventType.SUBMITTED, 10, 6, "Cerrada", platform="infojobs"),
        event(EventType.CLOSED, 11, 15, "Cerrada", platform="infojobs"),
    ]

    summary = summarize(build_applications(events), LABELS, "60d", TODAY)

    assert summary.rows == {
        "LinkedIn": Counts(applied=3, alive=2, rejected=1, closed=0),
        "InfoJobs": Counts(applied=1, alive=0, rejected=0, closed=1),
        "Indeed": Counts(),
    }
    assert summary.total == Counts(applied=4, alive=2, rejected=1, closed=1)
    assert (summary.start, summary.end) == (date(2026, 9, 20), TODAY)


def test_application_sent_before_period_does_not_count_even_if_rejected_inside():
    events = [
        event(EventType.SUBMITTED, 11, 5, "Antes"),
        event(EventType.REJECTED, 11, 15, "Antes"),
        event(EventType.REJECTED, 11, 16, "SinEnvio"),  # solicitud anterior a lo descargado
    ]

    summary = summarize(build_applications(events), LABELS, "7d", TODAY)

    assert summary.total == Counts()


def test_period_includes_its_first_day_and_today():
    events = [
        event(EventType.SUBMITTED, 11, 12, "PrimerDia"),
        event(EventType.SUBMITTED, 11, 19, "Hoy"),
        event(EventType.SUBMITTED, 11, 11, "Fuera"),
    ]

    summary = summarize(build_applications(events), LABELS, "7d", TODAY)

    assert summary.total.applied == 2


def test_only_selected_platforms_appear_in_order():
    events = [
        event(EventType.SUBMITTED, 11, 2, platform="indeed"),
        event(EventType.SUBMITTED, 11, 2, platform="linkedin"),
    ]

    summary = summarize(build_applications(events), {"indeed": "Indeed"}, "30d", TODAY)

    assert list(summary.rows) == ["Indeed"]
    assert summary.total.applied == 1


@pytest.mark.parametrize(
    ("period", "today", "start"),
    [
        ("60d", date(2026, 11, 19), date(2026, 9, 20)),
        ("7d", date(2026, 1, 3), date(2025, 12, 27)),
        ("2m", date(2026, 11, 19), date(2026, 9, 19)),
        ("1m", date(2026, 3, 31), date(2026, 2, 28)),  # no existe el 31 de febrero
        ("14m", date(2026, 1, 15), date(2024, 11, 15)),
        ("1y", date(2028, 2, 29), date(2027, 2, 28)),
    ],
)
def test_period_start(period, today, start):
    assert period_start(period, today) == start


def test_format_summary():
    summary = Summary(
        period="60d",
        start=date(2026, 9, 20),
        end=TODAY,
        rows={"LinkedIn": Counts(131, 94, 37, 0), "Indeed": Counts(32, 32, 0, 0)},
    )

    assert format_summary(summary) == (
        "CandiTrack · últimos 60 días (20 sep – 19 nov 2026)\n"
        "\n"
        "          Postuladas  Vivas  Rechazadas  Cerradas\n"
        "LinkedIn         131     94          37         0\n"
        "Indeed            32     32           0         0\n"
        "Total            163    126          37         0\n"
        "\n"
        "Vivas = enviadas o vistas, sin respuesta negativa todavía."
    )


@pytest.mark.parametrize(
    ("period", "start", "title"),
    [
        ("1d", date(2026, 11, 18), "último día (18 nov – 19 nov 2026)"),
        ("3m", date(2026, 8, 19), "últimos 3 meses (19 ago – 19 nov 2026)"),
        ("1y", date(2025, 11, 19), "último año (19 nov 2025 – 19 nov 2026)"),
    ],
)
def test_format_title(period, start, title):
    summary = Summary(period=period, start=start, end=TODAY, rows={})

    assert format_summary(summary).splitlines()[0] == f"CandiTrack · {title}"
