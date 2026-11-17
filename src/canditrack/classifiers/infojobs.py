"""Reglas para los correos de candidaturas de InfoJobs (pushinfojobs@*.infojobs.net).

A diferencia de LinkedIn, los asuntos de InfoJobs son genéricos ("Te has inscrito a una
oferta") y no incluyen la empresa, así que el puesto y la empresa se sacan del cuerpo.
Los avisos genéricos ("Tenemos novedades en tu candidatura", resúmenes semanales...) no
dicen a qué candidatura se refieren y se ignoran.
"""

import re
from email.utils import parseaddr
from html import unescape

from canditrack.models import ApplicationEvent, Email, EventType

PLATFORM = "infojobs"
SENDER_LOCAL_PART = "pushinfojobs"
SENDER_DOMAIN = "infojobs.net"

BODY_PATTERNS: list[tuple[EventType, re.Pattern[str]]] = [
    # Plantilla actual (desde 2019): puesto y empresa.
    (
        EventType.SUBMITTED,
        re.compile(
            r"Te has inscrito en la oferta (?P<position>.+?) Puedes seguir el estado"
            r".*? Y (?P<company>.+?) te ha dejado este mensaje",
            re.I,
        ),
    ),
    # Plantilla antigua (2018): solo la empresa.
    (
        EventType.SUBMITTED,
        re.compile(r"¡tú decides! (?P<company>.+?) ha dejado este mensaje para ti", re.I),
    ),
    # La empresa va tras el ÚLTIMO " en " (el puesto puede contenerlo).
    (
        EventType.CLOSED,
        re.compile(r"el proceso para (?P<position>.+) en (?P<company>.+?) ha finalizado", re.I),
    ),
]


class InfoJobsClassifier:
    """Detecta inscripciones y procesos finalizados en InfoJobs."""

    def classify(self, email: Email) -> ApplicationEvent | None:
        if not _is_infojobs_sender(email.sender):
            return None

        body = _normalize(email.body)
        for event_type, pattern in BODY_PATTERNS:
            match = pattern.search(body)
            if match:
                return ApplicationEvent(
                    type=event_type,
                    platform=PLATFORM,
                    company=match["company"].strip(),
                    position=_group(match, "position"),
                    date=email.date,
                    email_id=email.id,
                    thread_id=email.thread_id,
                )
        return None


def _is_infojobs_sender(sender: str) -> bool:
    local, _, domain = parseaddr(sender)[1].lower().partition("@")
    return local == SENDER_LOCAL_PART and (
        domain == SENDER_DOMAIN or domain.endswith("." + SENDER_DOMAIN)
    )


def _normalize(body: str) -> str:
    """Decodifica entidades HTML (a veces dobles: ``&amp;amp;``) y une los espacios."""
    previous = None
    while previous != body:
        previous, body = body, unescape(body)
    return " ".join(body.split())


def _group(match: re.Match[str], name: str) -> str | None:
    value = match.groupdict().get(name)
    return value.strip() if value else None
