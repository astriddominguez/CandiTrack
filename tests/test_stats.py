from datetime import UTC, date, datetime, timedelta

import pytest

from canditrack.models import ApplicationEvent, EventType
from canditrack.platforms import PLATFORMS
from canditrack.stats import PlatformStats, compute_stats, format_stats
from canditrack.tracking import build_applications

TODAY = date(2026, 11, 20)
NOON = datetime(2026, 11, 20, 12, tzinfo=UTC)


def event(type_, days_ago, company="Acme", platform="linkedin", hours=0.0):
    # A mediodía UTC: el mismo día en cualquier zona horaria europea o americana.
    return ApplicationEvent(
        type=type_,
        platform=platform,
        company=company,
        position="Dev",
        date=NOON - timedelta(days=days_ago, hours=hours),
        email_id=f"{company}-{type_}-{days_ago}-{hours}",
        thread_id="t",
    )


def stats_for(events, platforms=("linkedin",), period="60d", stale_days=21):
    return compute_stats(
        build_applications(events),
        [PLATFORMS[name] for name in platforms],
        period,
        TODAY,
        stale_days,
    )


def test_counts_responses_rejections_and_stale_applications():
    events = [
        # Vista 2 días después del envío.
        event(EventType.SUBMITTED, 30, "Vista"),
        event(EventType.VIEWED, 28, "Vista"),
        # Rechazada 6 días después (sin vista previa): cuenta como respuesta.
        event(EventType.SUBMITTED, 20, "Rechazo"),
        event(EventType.REJECTED, 14, "Rechazo"),
        # Enviada hace 25 días sin novedades: sin respuesta.
        event(EventType.SUBMITTED, 25, "Olvidada"),
        # Enviada hace 5 días: todavía no cuenta como sin respuesta.
        event(EventType.SUBMITTED, 5, "Reciente"),
        # Proceso cerrado: no es una respuesta de la empresa ni está "sin respuesta".
        event(EventType.SUBMITTED, 40, "Cerrada"),
        event(EventType.CLOSED, 10, "Cerrada"),
    ]

    stats = stats_for(events)
    row = stats.rows["linkedin"]

    assert (row.sent, row.responded, row.rejected, row.no_response) == (5, 2, 1, 1)
    assert sorted(row.response_days) == [2, 6]
    assert row.median_days_to_response == 4


def test_applications_sent_before_period_are_ignored():
    events = [event(EventType.SUBMITTED, 70, "Antigua"), event(EventType.REJECTED, 10, "Antigua")]

    assert stats_for(events).total == PlatformStats()


def test_stale_threshold_is_configurable():
    events = [event(EventType.SUBMITTED, 10, "A"), event(EventType.SUBMITTED, 3, "B")]

    assert stats_for(events, stale_days=21).total.no_response == 0
    assert stats_for(events, stale_days=7).total.no_response == 1


def test_total_median_uses_all_response_times_not_median_of_medians():
    events = [
        event(EventType.SUBMITTED, 30, "A"),
        event(EventType.VIEWED, 29, "A"),  # 1 día
        event(EventType.SUBMITTED, 30, "B"),
        event(EventType.VIEWED, 28, "B"),  # 2 días
        event(EventType.SUBMITTED, 30, "C", platform="tecnoempleo"),
        event(EventType.VIEWED, 20, "C", platform="tecnoempleo"),  # 10 días
    ]

    stats = stats_for(events, platforms=("linkedin", "tecnoempleo"))

    assert stats.rows["linkedin"].median_days_to_response == 1.5
    assert stats.rows["tecnoempleo"].median_days_to_response == 10
    assert stats.total.median_days_to_response == 2


def test_format_stats():
    events = [
        event(EventType.SUBMITTED, 30, "A"),
        event(EventType.REJECTED, 27, "A"),
        event(EventType.SUBMITTED, 30, "B"),
        event(EventType.SUBMITTED, 10, "C", platform="tecnoempleo"),
        event(EventType.VIEWED, 10, "C", platform="tecnoempleo", hours=-3),
    ]

    text = format_stats(stats_for(events, platforms=("linkedin", "tecnoempleo")))

    assert text.splitlines()[:5] == [
        "CandiTrack · estadísticas · últimos 60 días (21 sep – 20 nov 2026)",
        "",
        "             Enviadas  Con respuesta  Rechazadas  Sin respuesta  Días hasta respuesta",
        "LinkedIn            2        1 (50%)     1 (50%)        1 (50%)                     3",
        "Tecnoempleo         1       1 (100%)      0 (0%)         0 (0%)                    <1",
    ]
    assert text.splitlines()[-1] == (
        "Ojo: Tecnoempleo no avisa por correo de rechazos: "
        "sus cifras de respuesta salen más bajas de lo real."
    )


def test_format_without_applications_and_without_caveats():
    text = format_stats(stats_for([]))

    assert text.splitlines()[3].split() == ["LinkedIn", "0", "0", "0", "0", "-"]
    assert "Ojo" not in text


@pytest.mark.parametrize(
    ("platforms", "caveat"),
    [
        (
            ("infojobs", "indeed"),
            "Ojo: InfoJobs y Indeed no avisan por correo de vistas ni de rechazos: ",
        ),
        (
            ("indeed", "tecnoempleo"),
            "Ojo: Indeed no avisa por correo de vistas ni de rechazos; "
            "Tecnoempleo no avisa por correo de rechazos: ",
        ),
    ],
)
def test_caveats_name_what_each_platform_does_not_notify(platforms, caveat):
    assert format_stats(stats_for([], platforms=platforms)).splitlines()[-1].startswith(caveat)
