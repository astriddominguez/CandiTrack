from datetime import UTC, datetime

from canditrack.models import ApplicationEvent, EventType
from canditrack.tracking import build_applications


def event(
    type_: EventType,
    day: int,
    company: str = "Acme",
    position: str | None = None,
    platform: str = "linkedin",
) -> ApplicationEvent:
    return ApplicationEvent(
        type=type_,
        platform=platform,
        company=company,
        position=position,
        date=datetime(2026, 11, day, tzinfo=UTC),
        email_id=f"m{day}",
        thread_id=f"t{day}",
    )


def test_latest_event_sets_status_regardless_of_input_order():
    events = [
        event(EventType.REJECTED, 10, position="Dev"),
        event(EventType.SUBMITTED, 1, position="Dev"),
        event(EventType.VIEWED, 5, position="Dev"),
    ]

    [app] = build_applications(events)

    assert app.status is EventType.REJECTED
    assert app.updated == datetime(2026, 11, 10, tzinfo=UTC)
    assert [e.type for e in app.events] == [
        EventType.SUBMITTED,
        EventType.VIEWED,
        EventType.REJECTED,
    ]


def test_events_without_position_join_the_only_known_position():
    # LinkedIn: el envío y la visualización no dicen el puesto; el rechazo sí.
    events = [
        event(EventType.SUBMITTED, 1),
        event(EventType.VIEWED, 2),
        event(EventType.REJECTED, 3, company="ACME ", position="Backend Dev"),
    ]

    [app] = build_applications(events)

    assert app.position == "Backend Dev"
    assert app.status is EventType.REJECTED
    assert len(app.events) == 3


def test_events_without_position_stay_apart_when_position_is_ambiguous():
    events = [
        event(EventType.SUBMITTED, 1),
        event(EventType.REJECTED, 2, position="Backend Dev"),
        event(EventType.REJECTED, 3, position="Data Engineer"),
    ]

    apps = build_applications(events)

    assert sorted(a.position or "" for a in apps) == ["", "Backend Dev", "Data Engineer"]


def test_same_company_on_different_platforms_are_different_applications():
    events = [
        event(EventType.SUBMITTED, 1, position="Dev", platform="linkedin"),
        event(EventType.SUBMITTED, 2, position="Dev", platform="indeed"),
    ]

    apps = build_applications(events)

    assert [a.platform for a in apps] == ["indeed", "linkedin"]  # más reciente primero


def test_no_events():
    assert build_applications([]) == []


def test_application_id_is_stable_and_ignores_case_and_spaces():
    [a] = build_applications([event(EventType.SUBMITTED, 1, company="Acme", position="Dev")])
    [b] = build_applications([event(EventType.REJECTED, 9, company=" ACME ", position="dev")])
    [c] = build_applications([event(EventType.SUBMITTED, 1, company="Acme", position="QA")])

    assert a.id == b.id
    assert a.id != c.id
    assert len(a.id) == 12
