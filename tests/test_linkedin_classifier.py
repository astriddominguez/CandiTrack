from datetime import UTC, datetime

import pytest

from canditrack.classifiers.linkedin import LinkedInClassifier
from canditrack.models import Email, EventType

SENDER = "LinkedIn <jobs-noreply@linkedin.com>"
DATE = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
REJECTED_BODY = "Tu actualización de Acme\nhttps://www.linkedin.com/help?lipi=urn%3Ali%3Apage%3Aemail_email_jobs_application_rejected_01%3Babc"
VIEWED_BODY = "https://www.linkedin.com/?trk=eml-email_jobs_job_application_viewed_01-header"


def make_email(subject: str, body: str = "", sender: str = SENDER) -> Email:
    return Email(
        id="msg-1",
        thread_id="thr-1",
        sender=sender,
        subject=subject,
        date=DATE,
        snippet="",
        body=body,
    )


classifier = LinkedInClassifier()


@pytest.mark.parametrize(
    ("subject", "company"),
    [
        ("Ana, se ha enviado tu solicitud a Acme Corp", "Acme Corp"),
        ("Ana, your application was sent to Globex", "Globex"),
        ("se ha enviado tu solicitud a Initech", "Initech"),
    ],
)
def test_submitted(subject, company):
    event = classifier.classify(make_email(subject))

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.company == company
    assert event.position is None
    assert event.platform == "linkedin"
    assert (event.email_id, event.thread_id, event.date) == ("msg-1", "thr-1", DATE)


def test_viewed():
    event = classifier.classify(make_email("Acme Corp ha visto tu solicitud", VIEWED_BODY))

    assert event is not None
    assert event.type is EventType.VIEWED
    assert event.company == "Acme Corp"


def test_rejected_extracts_position_and_company():
    subject = "Tu solicitud para el puesto de  Desarrollador/a Python (100% remoto) en Acme Corp"
    event = classifier.classify(make_email(subject, REJECTED_BODY))

    assert event is not None
    assert event.type is EventType.REJECTED
    assert event.position == "Desarrollador/a Python (100% remoto)"
    assert event.company == "Acme Corp"


def test_rejected_position_containing_en_uses_last_one():
    subject = "Tu solicitud para el puesto de Prácticas en Data en Globex España"
    event = classifier.classify(make_email(subject, REJECTED_BODY))

    assert event is not None
    assert event.position == "Prácticas en Data"
    assert event.company == "Globex España"


def test_rejected_in_english():
    event = classifier.classify(make_email("Your application to Backend Engineer at Globex"))

    assert event is not None
    assert event.type is EventType.REJECTED
    assert (event.position, event.company) == ("Backend Engineer", "Globex")


def test_template_id_wins_over_ambiguous_subject():
    # Mismo asunto que un "visto", pero la plantilla dice que es un rechazo: no se clasifica
    # como "visto" por error.
    event = classifier.classify(make_email("Acme ha visto tu solicitud", REJECTED_BODY))

    assert event is None


@pytest.mark.parametrize(
    "subject",
    [
        "Ana, solicita ya el empleo de Backend Developer en Acme",
        "Nuevos empleos similares a Python Developer en Globex",
        "Acme busca personal para el puesto de Backend",
        "Ana, tienes novedades sobre tus solicitudes esta semana",
        "Ana, ¿estás buscando empleo?",
    ],
)
def test_ignores_job_suggestions_and_promotions(subject):
    assert classifier.classify(make_email(subject)) is None


@pytest.mark.parametrize(
    "sender",
    [
        "LinkedIn <jobalerts-noreply@linkedin.com>",
        "LinkedIn <newsletters-noreply@linkedin.com>",
        "Fake <jobs-noreply@linkedin.com.evil.example>",
    ],
)
def test_ignores_other_senders(sender):
    email = make_email("Ana, se ha enviado tu solicitud a Acme", sender=sender)

    assert classifier.classify(email) is None
