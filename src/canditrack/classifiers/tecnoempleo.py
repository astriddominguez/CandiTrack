"""Reglas para los correos de candidaturas de Tecnoempleo (info@ / comunicaciones@).

La parte de texto plano de estos correos solo trae CSS: la información está en el HTML.

- Envío ("Tecnoempleo.com >> CV recibido"):
  "Oferta: <puesto> Empresa: <empresa> Provincia: ..."
- Lectura ("Tecnoempleo > Curriculum leido por la empresa"):
  "<empresa> ha leído tu CV La empresa ha leído tu CV en la Oferta <puesto> el día ..."

Se ignoran:
- "Cambio de estado en tu Candidatura": no dice a qué estado, y en los correos reales llega
  el mismo día que el aviso de lectura de la misma oferta.
- "Tienes alguna candidatura descartada" y "Tienes N avisos pendientes": no dicen cuál.
- "<Empresa> quiere recibir tu CV": es interés de un reclutador, no una candidatura tuya.
"""

import re
from email.utils import parseaddr

from canditrack.classifiers.text import normalize
from canditrack.models import ApplicationEvent, Email, EventType

PLATFORM = "tecnoempleo"
SENDERS = ("info@tecnoempleo.com", "comunicaciones@tecnoempleo.com")

HTML_PATTERNS: list[tuple[EventType, re.Pattern[str]]] = [
    (
        EventType.SUBMITTED,
        re.compile(r"Oferta:\s*(?P<position>.+?)\s*Empresa:\s*(?P<company>.+?)\s*Provincia:"),
    ),
    (
        EventType.VIEWED,
        re.compile(
            r"^(?P<company>.+?) ha leído tu CV\s*La empresa ha leído tu CV en la Oferta "
            r"(?P<position>.+?) el día \d"
        ),
    ),
]


class TecnoempleoClassifier:
    """Detecta envíos y lecturas de CV en Tecnoempleo."""

    def classify(self, email: Email) -> ApplicationEvent | None:
        if parseaddr(email.sender)[1].lower() not in SENDERS:
            return None

        html = normalize(email.html_text)
        for event_type, pattern in HTML_PATTERNS:
            if match := pattern.search(html):
                return ApplicationEvent(
                    type=event_type,
                    platform=PLATFORM,
                    company=match["company"].strip(),
                    position=match["position"].strip(),
                    date=email.date,
                    email_id=email.id,
                    thread_id=email.thread_id,
                )
        return None
