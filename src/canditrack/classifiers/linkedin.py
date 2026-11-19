"""Reglas para los correos de candidaturas de LinkedIn (jobs-noreply@linkedin.com).

LinkedIn usa plantillas fijas. Cuando el cuerpo incluye el identificador interno de la
plantilla (p. ej. ``email_jobs_application_rejected_01`` en los enlaces) es la señal más
fiable porque no depende del idioma; si no, se usa el asunto.
"""

import re
from email.utils import parseaddr

from canditrack.classifiers.text import normalize
from canditrack.models import ApplicationEvent, Email, EventType

PLATFORM = "linkedin"
SENDER = "jobs-noreply@linkedin.com"

# Identificadores de plantilla presentes en los enlaces del cuerpo.
TEMPLATE_IDS = {
    "email_jobs_application_rejected_": EventType.REJECTED,
    "email_jobs_job_application_viewed_": EventType.VIEWED,
}

# El asunto suele empezar por el nombre del usuario: "Ana, se ha enviado...".
_NAME = r"^(?:[^,]+,\s*)?"

SUBJECT_PATTERNS: list[tuple[EventType, re.Pattern[str]]] = [
    (
        EventType.SUBMITTED,
        re.compile(_NAME + r"se ha enviado tu solicitud a (?P<company>.+)$", re.I),
    ),
    (
        EventType.SUBMITTED,
        re.compile(_NAME + r"your application was sent to (?P<company>.+)$", re.I),
    ),
    (EventType.VIEWED, re.compile(r"^(?P<company>.+?) ha visto tu solicitud$", re.I)),
    (EventType.VIEWED, re.compile(r"^(?P<company>.+?) viewed your application$", re.I)),
    # La parte de la empresa va tras el ÚLTIMO " en " / " at " (el puesto puede contenerlo).
    (
        EventType.REJECTED,
        re.compile(r"^Tu solicitud para el puesto de\s+(?P<position>.+) en (?P<company>.+)$", re.I),
    ),
    (
        EventType.REJECTED,
        re.compile(r"^Your application to\s+(?P<position>.+) at (?P<company>.+)$", re.I),
    ),
]


# Envío: el puesto va en la primera línea no vacía tras "Se ha enviado tu solicitud a
# <empresa>.". Los correos usan saltos de línea \r\n.
SUBMITTED_POSITION = re.compile(
    r"^Se ha enviado tu solicitud a [^\r\n]+\.[ \t]*(?:\r?\n[ \t]*)+(?P<position>[^\r\n]+)",
    re.I | re.M,
)
# Visualización (parte HTML): "...se ha fijado en ti. <puesto> <empresa> · <lugar>".
VIEWED_POSITION = re.compile(r"se ha fijado en ti\. (?P<job>.+?) · ", re.I)


class LinkedInClassifier:
    """Detecta envíos, visualizaciones y rechazos de candidaturas en LinkedIn."""

    def classify(self, email: Email) -> ApplicationEvent | None:
        if parseaddr(email.sender)[1].lower() != SENDER:
            return None

        subject = " ".join(email.subject.split())
        template_type = _type_from_template(email.body)

        for event_type, pattern in SUBJECT_PATTERNS:
            if template_type is not None and event_type != template_type:
                continue
            match = pattern.match(subject)
            if match:
                company = match["company"].strip()
                return ApplicationEvent(
                    type=event_type,
                    platform=PLATFORM,
                    company=company,
                    position=_group(match, "position") or _position_from_body(email, company),
                    date=email.date,
                    email_id=email.id,
                    thread_id=email.thread_id,
                )
        return None


def _position_from_body(email: Email, company: str) -> str | None:
    """El asunto de los envíos y visualizaciones no dice el puesto, pero el cuerpo sí."""
    if submitted := SUBMITTED_POSITION.search(email.body):
        return submitted["position"].strip()
    if viewed := VIEWED_POSITION.search(normalize(email.html_text)):
        # "<puesto> <empresa> · <lugar>": solo si la empresa coincide con la del asunto
        # podemos separar con seguridad dónde acaba el puesto.
        job = viewed["job"]
        if job.casefold().endswith(f" {company.casefold()}"):
            return job[: -len(company) - 1].strip()
    return None


def _type_from_template(body: str) -> EventType | None:
    for template_id, event_type in TEMPLATE_IDS.items():
        if template_id in body:
            return event_type
    return None


def _group(match: re.Match[str], name: str) -> str | None:
    value = match.groupdict().get(name)
    return value.strip() if value else None
