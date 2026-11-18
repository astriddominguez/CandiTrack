from canditrack.platforms import PLATFORMS, gmail_query


def test_registry_has_all_platforms():
    assert sorted(PLATFORMS) == ["indeed", "infojobs", "linkedin"]
    assert all(p.senders for p in PLATFORMS.values())


def test_gmail_query_only_includes_selected_platform_senders():
    query = gmail_query([PLATFORMS["linkedin"], PLATFORMS["infojobs"]], "30d")

    assert query == "from:(jobs-noreply@linkedin.com OR pushinfojobs) newer_than:30d"


def test_gmail_query_with_indeed_includes_update_senders():
    query = gmail_query([PLATFORMS["indeed"]], "6m")

    assert query == (
        "from:(indeedapply@indeed.com OR no-reply@indeed.com OR noreply@indeed.com) newer_than:6m"
    )
