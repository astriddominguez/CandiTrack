from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from canditrack.api import VERSION, create_app
from canditrack.models import Email
from canditrack.storage import EmailCache

LINKEDIN = "LinkedIn <jobs-noreply@linkedin.com>"
INFOJOBS = '"Mensajes InfoJobs.net" <pushinfojobs@notify.infojobs.net>'
NOW = datetime.now(UTC)


def make_email(msg_id: str, sender: str, subject: str, days_ago: int, body: str = "") -> Email:
    return Email(
        id=msg_id,
        thread_id=msg_id,
        sender=sender,
        subject=subject,
        date=NOW - timedelta(days=days_ago),
        snippet="",
        body=body,
    )


EMAILS = [
    # Acme: enviada hace 40 días y rechazada hace 5 → rechazada
    make_email("1", LINKEDIN, "Ana, se ha enviado tu solicitud a Acme", 40),
    make_email("2", LINKEDIN, "Tu solicitud para el puesto de Backend Dev en Acme", 5),
    # Globex: vista hace 2 días → vista
    make_email("3", LINKEDIN, "Globex ha visto tu solicitud", 2),
    # Initech (InfoJobs): proceso cerrado hace 10 días → cerrada
    make_email(
        "4",
        INFOJOBS,
        "¡Ana, este proceso ha finalizado!",
        10,
        "Te informamos de que el proceso para Data Engineer en Initech ha finalizado.",
    ),
    # Un correo que no es de candidaturas: no debe aparecer
    make_email("5", "amigo@example.com", "¿Quedamos?", 1),
]


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "test.db"
    with EmailCache(db) as cache:
        cache.save_many(EMAILS)
    return TestClient(create_app(db))


def test_health(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": VERSION}


def test_openapi_spec_is_published(client):
    spec = client.get("/openapi.json").json()

    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "CandiTrack API"
    assert spec["info"]["version"] == VERSION
    assert {"/api/v1/health", "/api/v1/platforms", "/api/v1/applications"} <= set(spec["paths"])
    # Los valores cerrados se publican como enums.
    params = {p["name"]: p for p in spec["paths"]["/api/v1/applications"]["get"]["parameters"]}
    platform_schema = params["platform"]["schema"]["anyOf"][0]["$ref"].split("/")[-1]
    assert spec["components"]["schemas"][platform_schema]["enum"] == [
        "linkedin",
        "infojobs",
        "indeed",
        "tecnoempleo",
    ]


def test_interactive_docs_are_available(client):
    assert client.get("/docs").status_code == 200


def test_platforms(client):
    assert client.get("/api/v1/platforms").json() == [
        {"name": "linkedin", "label": "LinkedIn"},
        {"name": "infojobs", "label": "InfoJobs"},
        {"name": "indeed", "label": "Indeed"},
        {"name": "tecnoempleo", "label": "Tecnoempleo"},
    ]


def test_applications_are_listed_most_recent_first(client):
    body = client.get("/api/v1/applications").json()

    assert body["total"] == 3
    assert (body["limit"], body["offset"]) == (50, 0)
    assert [(a["company"], a["status"]) for a in body["items"]] == [
        ("Globex", "viewed"),
        ("Acme", "rejected"),
        ("Initech", "closed"),
    ]
    acme = body["items"][1]
    assert acme["platform"] == "linkedin"
    assert acme["position"] == "Backend Dev"
    assert acme["submitted_at"] is not None
    assert len(acme["id"]) == 12


def test_application_ids_are_stable(client):
    first = client.get("/api/v1/applications").json()["items"]
    second = client.get("/api/v1/applications").json()["items"]

    assert [a["id"] for a in first] == [a["id"] for a in second]
    assert len({a["id"] for a in first}) == 3


@pytest.mark.parametrize(
    ("params", "companies"),
    [
        ({"platform": "infojobs"}, ["Initech"]),
        ({"status": "rejected"}, ["Acme"]),
        ({"platform": "linkedin", "status": "viewed"}, ["Globex"]),
        ({"since": "7d"}, ["Globex", "Acme"]),
        ({"since": "1w"}, ["Globex", "Acme"]),
        ({"status": "submitted"}, []),
    ],
)
def test_applications_filters(client, params, companies):
    body = client.get("/api/v1/applications", params=params).json()

    assert [a["company"] for a in body["items"]] == companies
    assert body["total"] == len(companies)


def test_applications_pagination(client):
    body = client.get("/api/v1/applications", params={"limit": 2, "offset": 1}).json()

    assert [a["company"] for a in body["items"]] == ["Acme", "Initech"]
    assert body["total"] == 3


@pytest.mark.parametrize(
    "params",
    [
        {"platform": "glassdoor"},
        {"status": "entrevista"},
        {"since": "dos meses"},
        {"since": "0d"},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
    ],
)
def test_invalid_parameters_return_422(client, params):
    response = client.get("/api/v1/applications", params=params)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == next(iter(params))


def test_empty_database(tmp_path):
    client = TestClient(create_app(tmp_path / "nueva.db"))

    assert client.get("/api/v1/applications").json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def application_id(client, company):
    items = client.get("/api/v1/applications").json()["items"]
    return next(a["id"] for a in items if a["company"] == company)


def test_application_detail_includes_events_in_order(client):
    body = client.get(f"/api/v1/applications/{application_id(client, 'Acme')}").json()

    assert body["company"] == "Acme"
    assert body["status"] == "rejected"
    assert [(e["type"], e["email_id"]) for e in body["events"]] == [
        ("submitted", "1"),
        ("rejected", "2"),
    ]
    assert body["events"][1]["position"] == "Backend Dev"


def test_unknown_application_returns_404(client):
    response = client.get("/api/v1/applications/000000000000")

    assert response.status_code == 404
    assert response.json() == {"detail": "Candidatura no encontrada"}


def test_404_is_documented_in_openapi(client):
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/api/v1/applications/{application_id}"]["get"]["responses"]

    assert responses["404"]["content"]["application/json"]["schema"]["$ref"].endswith("/Error")


def test_summary_defaults_to_60_days_and_all_platforms(client):
    body = client.get("/api/v1/summary").json()

    assert body["period"] == "60d"
    assert [r["platform"] for r in body["platforms"]] == [
        "linkedin",
        "infojobs",
        "indeed",
        "tecnoempleo",
    ]
    # Solo cuenta Acme (enviada hace 40 días): Globex e Initech no tienen correo de envío.
    linkedin = body["platforms"][0]
    assert (linkedin["applied"], linkedin["alive"], linkedin["rejected"]) == (1, 0, 1)
    assert body["total"] == {
        "platform": None,
        "label": "Total",
        "applied": 1,
        "alive": 0,
        "rejected": 1,
        "closed": 0,
    }


def test_summary_period_and_platforms(client):
    params = [("since", "30d"), ("platform", "indeed"), ("platform", "linkedin")]
    body = client.get("/api/v1/summary", params=params).json()

    assert body["period"] == "30d"
    assert [r["label"] for r in body["platforms"]] == ["Indeed", "LinkedIn"]
    assert body["total"]["applied"] == 0  # Acme se envió hace 40 días


@pytest.mark.parametrize("params", [{"since": "dos"}, {"platform": "glassdoor"}])
def test_summary_invalid_parameters_return_422(client, params):
    assert client.get("/api/v1/summary", params=params).status_code == 422


def test_stats_defaults(client):
    body = client.get("/api/v1/stats").json()

    assert (body["period"], body["stale_days"]) == ("60d", 21)
    linkedin, infojobs, *_ = body["platforms"]
    # Acme: enviada hace 40 días y rechazada hace 5 → respondida en 35 días.
    assert linkedin == {
        "platform": "linkedin",
        "label": "LinkedIn",
        "sent": 1,
        "responded": 1,
        "rejected": 1,
        "no_response": 0,
        "median_days_to_response": 35.0,
        "notifies_views": True,
        "notifies_rejections": True,
    }
    assert (infojobs["notifies_views"], infojobs["notifies_rejections"]) == (False, False)
    assert body["total"]["platform"] is None
    assert body["total"]["notifies_views"] is None


def test_stats_parameters(client):
    params = [("since", "30d"), ("stale_days", "7"), ("platform", "tecnoempleo")]
    body = client.get("/api/v1/stats", params=params).json()

    assert (body["period"], body["stale_days"]) == ("30d", 7)
    assert [r["label"] for r in body["platforms"]] == ["Tecnoempleo"]
    assert body["total"]["sent"] == 0
    assert body["total"]["median_days_to_response"] is None


@pytest.mark.parametrize(
    "params", [{"since": "x"}, {"stale_days": 0}, {"stale_days": 400}, {"platform": "glassdoor"}]
)
def test_stats_invalid_parameters_return_422(client, params):
    assert client.get("/api/v1/stats", params=params).status_code == 422
