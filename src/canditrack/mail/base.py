"""Interfaz común para cualquier fuente de correo (Gmail, fakes de test...)."""

from typing import Protocol

from canditrack.models import Email


class MailSource(Protocol):
    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        """Devuelve los correos que cumplen `query` (sintaxis de búsqueda de Gmail)."""
        ...
