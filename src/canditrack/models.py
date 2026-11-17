"""Modelos de dominio de CandiTrack, independientes del proveedor de correo."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Email:
    """Un correo electrónico tal y como lo usa CandiTrack."""

    id: str
    thread_id: str
    sender: str
    subject: str
    date: datetime
    snippet: str
    body: str
