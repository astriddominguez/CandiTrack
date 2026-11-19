from datetime import UTC, datetime

import pytest

from canditrack.classifiers.linkedin import LinkedInClassifier
from canditrack.models import Email, EventType

SENDER = "LinkedIn <jobs-noreply@linkedin.com>"
DATE = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
REJECTED_BODY = "Tu actualización de Acme\nhttps://www.linkedin.com/help?lipi=urn%3Ali%3Apage%3Aemail_email_jobs_application_rejected_01%3Babc"
VIEWED_BODY = "https://www.linkedin.com/?trk=eml-email_jobs_job_application_viewed_01-header"


def make_email(subject: str, body: str = "", sender: str = SENDER, html_text: str = "") -> Email:
    return Email(
        id="msg-1",
        thread_id="thr-1",
        sender=sender,
        subject=subject,
        date=DATE,
        snippet="",
        body=body,
        html_text=html_text,
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


SUBMITTED_BODY = (
    "Se ha enviado tu solicitud a Acme Corp S.L..\r\n\r\n"
    "Backend Developer (Python & IA)\r\n"
    "Acme Corp S.L.\r\n"
    "Barcelona\r\n"
    "Ver anuncio de empleo: https://www.linkedin.com/jobs/view/1\r\n"
    "Descubre otros empleos similares que podrían interesarte\r\n"
    "Data Engineer\r\nGlobex\r\n"
)


def test_submitted_takes_position_from_body():
    event = classifier.classify(
        make_email("Ana, se ha enviado tu solicitud a Acme Corp S.L.", SUBMITTED_BODY)
    )

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.company == "Acme Corp S.L."
    assert event.position == "Backend Developer (Python & IA)"


VIEWED_HTML = (
    "Acme ha visto tu solicitud \u034f \u034f Han visto tu solicitud ¡Muy bien! "
    "El equipo de selección de Acme se ha fijado en ti. AI Engineer &amp; MLOps Acme · España "
    "Solicitado el 16 nov Descubre empleos similares Data Engineer Globex · España"
)


def test_viewed_takes_position_from_html():
    event = classifier.classify(
        make_email("Acme ha visto tu solicitud", VIEWED_BODY, html_text=VIEWED_HTML)
    )

    assert event is not None
    assert event.type is EventType.VIEWED
    assert event.position == "AI Engineer & MLOps"


def test_viewed_without_matching_company_in_html_has_no_position():
    html = VIEWED_HTML.replace("MLOps Acme ·", "MLOps Acme Iberia ·")

    event = classifier.classify(
        make_email("Acme ha visto tu solicitud", VIEWED_BODY, html_text=html)
    )

    assert event is not None
    assert event.position is None


def test_submitted_without_position_in_body_still_detected():
    event = classifier.classify(make_email("Ana, your application was sent to Globex"))

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.position is None
