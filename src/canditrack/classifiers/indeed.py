"""Reglas para los correos de candidaturas de Indeed (indeedapply@ / noreply@indeed.com).

- Solicitud enviada: el puesto va en el asunto ("Solicitud en Indeed: <puesto>"). La
  empresa solo aparece en la parte HTML ("...se han enviado a <empresa>.") en los correos
  actuales, y en la línea "Empleo: <puesto> en <empresa> en <lugar>" en los antiguos.
- Solicitud vista: "Buenas noticias: <empresa> vio tu solicitud".
- Rechazo: "Actualización sobre tu solicitud en <empresa>" con un "Lamentablemente..." en
  el cuerpo (el asunto por sí solo no dice si es un rechazo).
"""

import re
from email.utils import parseaddr
from html import unescape

from canditrack.models import ApplicationEvent, Email, EventType

PLATFORM = "indeed"
APPLY_SENDER = "indeedapply@indeed.com"
UPDATE_SENDERS = {"noreply@indeed.com", "no-reply@indeed.com"}

SUBMITTED_SUBJECT = re.compile(r"^Solicitud en Indeed:\s*(?P<position>.+)$", re.I)
SUBMITTED_HTML = re.compile(r"se han enviado a (?P<company>.+?)\. ¡Buena suerte", re.I)
SUBMITTED_PLAIN = re.compile(r"Empleo: (?P<job>.+?) Nombre:", re.I)

VIEWED_SUBJECT = re.compile(r"^Buenas noticias:\s*(?P<company>.+?) vio tu solicitud$", re.I)
VIEWED_BODY = re.compile(r"tu solicitud a su empleo de (?P<position>.+?)\.(?: |$)", re.I)

REJECTED_SUBJECT = re.compile(r"^Actualización sobre tu solicitud en (?P<company>.+)$", re.I)
# "<puesto> en <empresa>"; el cuerpo repite el texto, así que nos quedamos con la primera.
REJECTED_BODY = re.compile(r"solicitud para el puesto de (?P<job>.+?)\. Lamentablemente", re.I)

# Caracteres invisibles de relleno que Indeed mete en los correos.
_REMOVE_INVISIBLE = dict.fromkeys(map(ord, "­͏​‌‍⁠﻿"))


class IndeedClassifier:
    """Detecta solicitudes enviadas, vistas y rechazadas en Indeed."""

    def classify(self, email: Email) -> ApplicationEvent | None:
        sender = parseaddr(email.sender)[1].lower()
        subject = _normalize(email.subject)

        if sender == APPLY_SENDER:
            return _submitted(email, subject) or _viewed(email, subject)
        if sender in UPDATE_SENDERS:
            return _rejected(email, subject)
        return None


def _submitted(email: Email, subject: str) -> ApplicationEvent | None:
    match = SUBMITTED_SUBJECT.match(subject)
    if not match:
        return None
    position = match["position"].strip()

    company = None
    if html := SUBMITTED_HTML.search(_normalize(email.html_text)):
        company = html["company"]
    elif plain := SUBMITTED_PLAIN.search(_normalize(email.body)):
        # "<puesto> en <empresa> en <lugar>": quitamos el puesto y nos quedamos con lo
        # que hay hasta el último " en " (el lugar).
        job = plain["job"].removeprefix(f"{position} en ")
        company = job.rsplit(" en ", 1)[0] if " en " in job else job
    if not company:
        return None
    return _event(EventType.SUBMITTED, email, company, position)


def _viewed(email: Email, subject: str) -> ApplicationEvent | None:
    match = VIEWED_SUBJECT.match(subject)
    if not match:
        return None
    body = VIEWED_BODY.search(_normalize(email.body))
    return _event(EventType.VIEWED, email, match["company"], body and body["position"])


def _rejected(email: Email, subject: str) -> ApplicationEvent | None:
    subject_match = REJECTED_SUBJECT.match(subject)
    body_match = REJECTED_BODY.search(_normalize(email.body))
    if not subject_match or not body_match:
        return None
    company = subject_match["company"]
    position = body_match["job"].removesuffix(f" en {company}")
    return _event(EventType.REJECTED, email, company, position)


def _event(
    event_type: EventType, email: Email, company: str, position: str | None
) -> ApplicationEvent:
    return ApplicationEvent(
        type=event_type,
        platform=PLATFORM,
        company=company.strip(),
        position=position.strip() if position else None,
        date=email.date,
        email_id=email.id,
        thread_id=email.thread_id,
    )


def _normalize(text: str) -> str:
    """Decodifica entidades HTML, quita caracteres invisibles y une los espacios."""
    previous = None
    while previous != text:
        previous, text = text, unescape(text)
    return " ".join(text.translate(_REMOVE_INVISIBLE).split())
