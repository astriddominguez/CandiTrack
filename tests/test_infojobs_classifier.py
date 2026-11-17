from datetime import UTC, datetime

import pytest

from canditrack.classifiers.infojobs import InfoJobsClassifier
from canditrack.models import Email, EventType

SENDER = '"Mensajes InfoJobs.net" <pushinfojobs@comms.infojobs.net>'
DATE = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)

SUBMITTED_BODY = (
    "( https://link.comms.infojobs.net/abc )\n\n"
    "Perfecto. Te has inscrito en la oferta Programador/a Python &amp;amp; SQL - 100% Teletrabajo"
    " Puedes seguir el estado de tu candidatura en la web o la app\n\n"
    "Y Acme Corp, S.L. te ha dejado este mensaje: Muchas gracias por interesarte por nuestra"
    " oferta.<br/><br/>Departamento de RRHH\n\n"
    "Recuerda que es la empresa y no InfoJobs quien gestiona el proceso de selección."
)

OLD_SUBMITTED_BODY = (
    "InfoJobs\n\n"
    "                                 Te has inscrito a una oferta\n\n"
    "                                 Sigue el estado de la candidatura en la web o en la app,"
    " ¡tú decides!\n\n"
    "\t\t\t\t\t\t\t\t\t  Globex, SL ha dejado este mensaje para ti:\n\n"
    "\t\t\t\t\t\t\t\t\t  Hemos recibido tu inscripción"
)

CLOSED_BODY = (
    "( https://link.notify.infojobs.net/abc )\n\n"
    "Información sobre tus candidaturas Te informamos de que el proceso para Prácticas en Data"
    " en Initech España ha finalizado.\n\n"
    "VER CANDIDATURA ( https://link.notify.infojobs.net/def )"
)


def make_email(body: str, subject: str = "", sender: str = SENDER) -> Email:
    return Email(
        id="msg-1",
        thread_id="thr-1",
        sender=sender,
        subject=subject,
        date=DATE,
        snippet="",
        body=body,
    )


classifier = InfoJobsClassifier()


def test_submitted_extracts_position_and_company():
    event = classifier.classify(make_email(SUBMITTED_BODY, "Te has inscrito a una oferta"))

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.position == "Programador/a Python & SQL - 100% Teletrabajo"
    assert event.company == "Acme Corp, S.L."
    assert event.platform == "infojobs"
    assert (event.email_id, event.thread_id, event.date) == ("msg-1", "thr-1", DATE)


def test_submitted_old_template_has_company_only():
    event = classifier.classify(make_email(OLD_SUBMITTED_BODY, "Te has inscrito a una oferta"))

    assert event is not None
    assert event.type is EventType.SUBMITTED
    assert event.company == "Globex, SL"
    assert event.position is None


def test_closed_position_containing_en_uses_last_one():
    event = classifier.classify(make_email(CLOSED_BODY, "¡Ana, este proceso ha finalizado!"))

    assert event is not None
    assert event.type is EventType.CLOSED
    assert event.position == "Prácticas en Data"
    assert event.company == "Initech España"


@pytest.mark.parametrize(
    "sender",
    [
        "pushinfojobs@push.infojobs.net",
        "pushinfojobs@notify.infojobs.net",
        '"Mensajes InfoJobs.net " <PushInfoJobs@Comms.InfoJobs.net>',
    ],
)
def test_accepts_all_infojobs_notification_senders(sender):
    assert classifier.classify(make_email(SUBMITTED_BODY, sender=sender)) is not None


@pytest.mark.parametrize(
    "sender",
    [
        "Alerta de empleo InfoJobs <ofertas@push.infojobs.net>",
        "pushinfojobs@infojobs.net.evil.com",
        "LinkedIn <jobs-noreply@linkedin.com>",
    ],
)
def test_ignores_other_senders(sender):
    assert classifier.classify(make_email(SUBMITTED_BODY, sender=sender)) is None


@pytest.mark.parametrize(
    "body",
    [
        "Hay cambios en tu candidatura Entra para verlos desde la web o en la app",
        "Así evolucionan tus candidaturas El estado de al menos 5 de tus candidaturas ha cambiado",
        "Te has inscrito a una oferta Sigue el estado de la candidatura en la web o en la app, "
        "¡tú decides! VER MIS CANDIDATURAS",
    ],
)
def test_generic_notifications_are_ignored(body):
    assert classifier.classify(make_email(body)) is None
