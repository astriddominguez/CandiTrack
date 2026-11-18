from datetime import UTC, datetime

import pytest

from canditrack.classifiers.indeed import IndeedClassifier
from canditrack.models import Email, EventType

APPLY = '"Solicitud vía Indeed" <indeedapply@indeed.com>'
UPDATE = '"Acme Corp S.L." <noreply@indeed.com>'
DATE = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)

SUBMITTED_HTML = (
    "96 We'll help you get started ͏­ ‌ ‌ "
    "Solicitud enviada AI Developer Acme Corp &amp;amp; Co. - Sagunt, VC, 46520 "
    "Los siguientes documentos se han enviado a Acme Corp &amp;amp; Co.. ¡Buena suerte! "
    "• Solicitud • CV"
)
SUBMITTED_PLAIN = (
    "Tu solicitud ha sido enviada. ¡Buena suerte!\n"
    "Si encuentras algún error en tu solicitud, por favor contacta con Indeed\n------"
)
OLD_SUBMITTED_PLAIN = (
    "Tu solicitud ha sido enviada. ¡Buena suerte!\n------\n"
    "Empleo: Camarero/a en terraza en Bar Pepe en Manresa, Barcelona provincia\n"
    "Nombre: Ana\nEmail: ana@example.com"
)
VIEWED_PLAIN = (
    "    ¡Enhorabuena, Globex ha visto tu solicitud a su empleo!\n"
    "Este email es para confirmar que la empresa ha visto tu solicitud a su empleo de "
    "Necesito florista.\nPara gestionar tus solicitudes en Indeed, haz clic"
)
_REJECTION = (
    "Gracias por enviar una solicitud para el puesto de Prácticas en Data en Acme Corp S.L.."
    "\nLamentablemente, Acme Corp S.L. ha pasado a la siguiente etapa en el proceso de "
    "contratación y tu solicitud no se encuentra entre las seleccionadas en esta ocasión.\n"
)
# Indeed repite el texto en el cuerpo.
REJECTED_PLAIN = "96" + _REJECTION + "͏ ͏\nActualización sobre tu solicitud" + _REJECTION


def make_email(subject: str, body: str = "", html_text: str = "", sender: str = APPLY) -> Email:
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


classifier = IndeedClassifier()


def test_submitted_takes_company_from_html():
    email = make_email("Solicitud en Indeed: AI Developer", SUBMITTED_PLAIN, SUBMITTED_HTML)
    event = classifier.classify(email)

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.position == "AI Developer"
    assert event.company == "Acme Corp & Co."
    assert event.platform == "indeed"
    assert (event.email_id, event.thread_id, event.date) == ("msg-1", "thr-1", DATE)


def test_submitted_old_template_takes_company_from_plain_text():
    email = make_email("Solicitud en Indeed: Camarero/a en terraza", OLD_SUBMITTED_PLAIN)
    event = classifier.classify(email)

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.position == "Camarero/a en terraza"
    assert event.company == "Bar Pepe"


def test_submitted_without_company_is_ignored():
    email = make_email("Solicitud en Indeed: AI Developer", SUBMITTED_PLAIN)

    assert classifier.classify(email) is None


def test_viewed():
    email = make_email("Buenas noticias: Globex vio tu solicitud", VIEWED_PLAIN)
    event = classifier.classify(email)

    assert event is not None
    assert event.type is EventType.VIEWED
    assert event.company == "Globex"
    assert event.position == "Necesito florista"


def test_rejected_uses_first_copy_and_subject_company():
    subject = "Actualización sobre tu solicitud en Acme Corp S.L."
    event = classifier.classify(make_email(subject, REJECTED_PLAIN, sender=UPDATE))

    assert event is not None
    assert event.type is EventType.REJECTED
    assert event.company == "Acme Corp S.L."
    assert event.position == "Prácticas en Data"


def test_update_without_rejection_text_is_ignored():
    subject = "Actualización sobre tu solicitud en Acme Corp S.L."
    body = "Gracias por enviar una solicitud. La empresa ha revisado tu candidatura."

    assert classifier.classify(make_email(subject, body, sender=UPDATE)) is None


@pytest.mark.parametrize(
    ("subject", "sender"),
    [
        ("¿Se ha puesto Globex en contacto contigo?", APPLY),
        ("Actualización: problema con la solicitud para Globex.", "no-reply@indeed.com"),
        ("Mensaje nuevo de Globex - Backend Developer", "no-reply@indeed.com"),
        ("Backend Developer en Globex", "donotreply@match.indeed.com"),
        ("Solicitud en Indeed: AI Developer", "alert@indeed.com"),
    ],
)
def test_other_indeed_emails_are_ignored(subject, sender):
    email = make_email(subject, SUBMITTED_PLAIN, SUBMITTED_HTML, sender=sender)

    assert classifier.classify(email) is None
