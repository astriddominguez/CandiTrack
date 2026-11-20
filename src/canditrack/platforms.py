"""Registro de plataformas soportadas: su clasificador y los remitentes de sus correos."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from canditrack.classifiers import indeed, infojobs, linkedin, tecnoempleo
from canditrack.classifiers.base import Classifier
from canditrack.models import ApplicationEvent, Email


@dataclass(frozen=True)
class Platform:
    name: str
    label: str  # nombre para mostrar
    classifier: Classifier
    # Remitentes para la búsqueda de Gmail (`from:`); acotan qué correos se descargan.
    senders: tuple[str, ...]


PLATFORMS: dict[str, Platform] = {
    p.name: p
    for p in (
        Platform(linkedin.PLATFORM, "LinkedIn", linkedin.LinkedInClassifier(), (linkedin.SENDER,)),
        # "from:pushinfojobs" cubre todos los subdominios (push., comms., notify.).
        Platform(
            infojobs.PLATFORM,
            "InfoJobs",
            infojobs.InfoJobsClassifier(),
            (infojobs.SENDER_LOCAL_PART,),
        ),
        Platform(
            indeed.PLATFORM,
            "Indeed",
            indeed.IndeedClassifier(),
            (indeed.APPLY_SENDER, *sorted(indeed.UPDATE_SENDERS)),
        ),
        Platform(
            tecnoempleo.PLATFORM,
            "Tecnoempleo",
            tecnoempleo.TecnoempleoClassifier(),
            tecnoempleo.SENDERS,
        ),
    )
}


def classify_emails(
    emails: Iterable[Email], platforms: Iterable[Platform]
) -> list[ApplicationEvent]:
    """Pasa cada correo por los clasificadores; se queda con el primer evento detectado."""
    platforms = list(platforms)
    events = []
    for email in emails:
        for platform in platforms:
            if event := platform.classifier.classify(email):
                events.append(event)
                break
    return events


def gmail_query(
    platforms: list[Platform], newer_than: str | None = None, *, after: date | None = None
) -> str:
    """Búsqueda de Gmail para los correos de esas plataformas.

    `newer_than` es un periodo relativo ("30d", "6m"); `after`, una fecha a partir de la cual
    buscar (Gmail interpreta la fecha en su propia zona horaria: conviene dejar margen).
    """
    senders = " OR ".join(s for p in platforms for s in p.senders)
    query = f"from:({senders})"
    if newer_than:
        query += f" newer_than:{newer_than}"
    if after:
        query += f" after:{after:%Y/%m/%d}"
    return query
