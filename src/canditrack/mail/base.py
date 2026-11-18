"""Interfaces comunes para las fuentes de correo (Gmail, caché, fakes de test...)."""

from typing import Protocol

from canditrack.models import Email


class MailSource(Protocol):
    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        """Devuelve los correos que cumplen `query` (sintaxis de búsqueda de Gmail)."""
        ...


class RemoteMailSource(MailSource, Protocol):
    """Fuente que permite listar IDs (barato) y descargar correos (caro) por separado."""

    def list_ids(self, query: str = "", max_results: int = 50) -> list[str]: ...

    def get_messages(self, ids: list[str]) -> list[Email]: ...
