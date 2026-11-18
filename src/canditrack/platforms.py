"""Registro de plataformas soportadas: su clasificador y los remitentes de sus correos."""

from dataclasses import dataclass

from canditrack.classifiers import indeed, infojobs, linkedin
from canditrack.classifiers.base import Classifier


@dataclass(frozen=True)
class Platform:
    name: str
    classifier: Classifier
    # Remitentes para la búsqueda de Gmail (`from:`); acotan qué correos se descargan.
    senders: tuple[str, ...]


PLATFORMS: dict[str, Platform] = {
    p.name: p
    for p in (
        Platform(linkedin.PLATFORM, linkedin.LinkedInClassifier(), (linkedin.SENDER,)),
        # "from:pushinfojobs" cubre todos los subdominios (push., comms., notify.).
        Platform(infojobs.PLATFORM, infojobs.InfoJobsClassifier(), (infojobs.SENDER_LOCAL_PART,)),
        Platform(
            indeed.PLATFORM,
            indeed.IndeedClassifier(),
            (indeed.APPLY_SENDER, *sorted(indeed.UPDATE_SENDERS)),
        ),
    )
}


def gmail_query(platforms: list[Platform], newer_than: str) -> str:
    """Búsqueda de Gmail para los correos de esas plataformas en el periodo dado (p. ej. "30d")."""
    senders = " OR ".join(s for p in platforms for s in p.senders)
    return f"from:({senders}) newer_than:{newer_than}"
