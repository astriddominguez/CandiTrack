from datetime import UTC, date, datetime

from canditrack.models import Email
from canditrack.platforms import PLATFORMS, classify_emails, gmail_query


def test_registry_has_all_platforms():
    assert sorted(PLATFORMS) == ["indeed", "infojobs", "linkedin", "tecnoempleo"]
    assert all(p.senders for p in PLATFORMS.values())


def test_gmail_query_only_includes_selected_platform_senders():
    query = gmail_query([PLATFORMS["linkedin"], PLATFORMS["infojobs"]], "30d")

    assert query == "from:(jobs-noreply@linkedin.com OR pushinfojobs) newer_than:30d"


def test_gmail_query_with_indeed_includes_update_senders():
    query = gmail_query([PLATFORMS["indeed"]], "6m")

    assert query == (
        "from:(indeedapply@indeed.com OR no-reply@indeed.com OR noreply@indeed.com) newer_than:6m"
    )


def test_gmail_query_with_start_date():
    query = gmail_query([PLATFORMS["linkedin"]], after=date(2026, 10, 30))

    assert query == "from:(jobs-noreply@linkedin.com) after:2026/10/30"


def test_platforms_have_display_labels():
    assert [p.label for p in PLATFORMS.values()] == [
        "LinkedIn",
        "InfoJobs",
        "Indeed",
        "Tecnoempleo",
    ]


def test_classify_emails_uses_the_matching_platform():
    def email(sender, subject):
        return Email("1", "t", sender, subject, datetime(2026, 11, 1, tzinfo=UTC), "", "")

    events = classify_emails(
        [
            email("jobs-noreply@linkedin.com", "Acme ha visto tu solicitud"),
            email("amigo@example.com", "Hola"),
        ],
        PLATFORMS.values(),
    )

    assert [(e.platform, e.company) for e in events] == [("linkedin", "Acme")]


def test_platforms_declare_what_they_notify():
    flags = {p.name: (p.notifies_views, p.notifies_rejections) for p in PLATFORMS.values()}

    assert flags == {
        "linkedin": (True, True),
        "infojobs": (False, False),
        "indeed": (False, False),
        "tecnoempleo": (True, False),
    }
