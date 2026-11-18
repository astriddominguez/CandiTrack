"""Modelos de dominio de CandiTrack, independientes del proveedor de correo."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True)
class Email:
    """Un correo electrónico tal y como lo usa CandiTrack."""

    id: str
    thread_id: str
    sender: str
    subject: str
    date: datetime
    snippet: str
    body: str  # texto plano; si el correo solo trae HTML, el HTML convertido a texto
    html_text: str = ""  # la parte HTML convertida a texto (a veces trae datos que faltan en body)


class EventType(StrEnum):
    """Lo que ha ocurrido en una candidatura."""

    SUBMITTED = "submitted"  # la solicitud se ha enviado
    VIEWED = "viewed"  # la empresa ha visto la solicitud
    REJECTED = "rejected"  # la empresa ha descartado la candidatura
    CLOSED = "closed"  # el proceso de selección ha terminado (la oferta se ha cerrado)


@dataclass(frozen=True)
class ApplicationEvent:
    """Un evento de una candidatura detectado a partir de un correo."""

    type: EventType
    platform: str
    company: str
    position: str | None
    date: datetime
    email_id: str
    thread_id: str
