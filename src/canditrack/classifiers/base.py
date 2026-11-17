"""Interfaz común para cualquier clasificador (reglas, IA...)."""

from typing import Protocol

from canditrack.models import ApplicationEvent, Email


class Classifier(Protocol):
    def classify(self, email: Email) -> ApplicationEvent | None:
        """Devuelve el evento de candidatura del correo, o None si no es relevante."""
        ...
