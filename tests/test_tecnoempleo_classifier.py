from datetime import UTC, datetime

import pytest

from canditrack.classifiers.tecnoempleo import TecnoempleoClassifier
from canditrack.models import Email, EventType

INFO = '"Tecnoempleo.com" <info@tecnoempleo.com>'
DATE = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
# La parte de texto plano de Tecnoempleo solo trae CSS.
CSS = "@media only screen and (max-width: 640px) { .span-2 { float: none !important; } }"

SUBMITTED_HTML = (
    "Tu CV ha sido recibido por la empresa"
    "Oferta: Desarrollador/a Python &amp; SQL (100% remoto)"
    "Empresa: Acme Corp, S.L."
    "Provincia: 100% En remoto Sigue el estado de esta candidatura desde la web o en la App"
)
VIEWED_HTML = (
    "Acme Corp ha leído tu CV"
    "La empresa ha leído tu CV en la Oferta Devops el día 16 Noviembre de 2026 a las 10:09 "
    "horas. ¿Quieres saber más? Entrar en mi cuenta"
)


def make_email(subject: str, html_text: str, sender: str = INFO) -> Email:
    return Email(
        id="msg-1",
        thread_id="thr-1",
        sender=sender,
        subject=subject,
        date=DATE,
        snippet="",
        body=CSS,
        html_text=html_text,
    )


classifier = TecnoempleoClassifier()


def test_submitted():
    event = classifier.classify(make_email("Tecnoempleo.com >> CV recibido", SUBMITTED_HTML))

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.platform == "tecnoempleo"
    assert event.company == "Acme Corp, S.L."
    assert event.position == "Desarrollador/a Python & SQL (100% remoto)"
    assert (event.email_id, event.thread_id, event.date) == ("msg-1", "thr-1", DATE)


def test_viewed():
    subject = "Tecnoempleo > Curriculum leido por la empresa"
    event = classifier.classify(make_email(subject, VIEWED_HTML))

    assert event is not None
    assert event.type is EventType.VIEWED
    assert event.company == "Acme Corp"
    assert event.position == "Devops"


def test_old_sender_is_accepted():
    sender = '"Tecnoempleo.com" <comunicaciones@tecnoempleo.com>'

    assert classifier.classify(make_email("CV recibido", SUBMITTED_HTML, sender)) is not None


@pytest.mark.parametrize(
    ("subject", "html"),
    [
        (
            "tecnoempleo.com > Cambio de estado en tu Candidatura",
            "Tu Candidatura ha cambiado de estadoTu CV vinculado en la oferta Devops de la "
            "empresa Acme Corp ha cambiado de estado.",
        ),
        (
            "Tienes alguna candidatura descartada",
            "Alguna de tus candidaturas ha sido descartada... Pero no te preocupes",
        ),
        ("Tienes 1 aviso pendiente de leer", "Tienes avisos pendientesHas recibido notificaciones"),
        ("Acme Corp quiere recibir tu CV", "Acme Corp está interesada en tu perfil"),
    ],
)
def test_generic_notifications_are_ignored(subject, html):
    assert classifier.classify(make_email(subject, html)) is None


@pytest.mark.parametrize(
    "sender",
    [
        "alertas@push.tecnoempleo.com",
        "push@tecnoempleo.com",
        "info@tecnoempleo.com.evil.com",
        "LinkedIn <jobs-noreply@linkedin.com>",
    ],
)
def test_other_senders_are_ignored(sender):
    assert classifier.classify(make_email("CV recibido", SUBMITTED_HTML, sender)) is None
