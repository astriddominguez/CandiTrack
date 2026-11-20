"""Acceso a Gmail mediante la API oficial de Google (solo lectura)."""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from canditrack.models import Email

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

DEFAULT_CREDENTIALS_PATH = Path("credentials.json")
DEFAULT_TOKEN_PATH = Path("token.json")

# Reintentos (con espera exponencial) ante errores temporales y el límite por minuto
# de Gmail (403 rateLimitExceeded / 429), que salta al leer cientos de correos seguidos.
NUM_RETRIES = 6


def get_credentials(
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
) -> Credentials:
    """Carga el token guardado, lo refresca o lanza el flujo OAuth en el navegador."""
    creds: Credentials | None = None
    if token_path.exists():
        # google-auth no anota estos métodos.
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)  # type: ignore[no-untyped-call]

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())  # type: ignore[no-untyped-call]
        except RefreshError:
            # En modo "Testing" el refresh token caduca a los 7 días: volver a autorizar.
            creds = None

    if not creds or not creds.valid:
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"No se encuentra {credentials_path}. Consulta docs/gmail-setup.md."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json())
    return creds


class GmailSource:
    """Implementación de `MailSource` sobre la Gmail API."""

    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def from_credentials(cls, credentials: Credentials) -> GmailSource:
        return cls(build("gmail", "v1", credentials=credentials, cache_discovery=False))

    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        return self.get_messages(self.list_ids(query, max_results))

    def list_ids(self, query: str = "", max_results: int = 50) -> list[str]:
        """IDs de los correos que cumplen `query`, del más reciente al más antiguo (barato)."""
        messages = self._service.users().messages()
        ids: list[str] = []
        page_token: str | None = None

        while len(ids) < max_results:
            response = messages.list(
                userId="me",
                q=query,
                maxResults=min(500, max_results - len(ids)),
                pageToken=page_token,
            ).execute(num_retries=NUM_RETRIES)
            ids.extend(m["id"] for m in response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return ids[:max_results]

    def get_messages(self, ids: list[str]) -> list[Email]:
        """Descarga los correos completos (lento: una petición por correo)."""
        messages = self._service.users().messages()
        return [
            parse_message(
                messages.get(userId="me", id=msg_id, format="full").execute(num_retries=NUM_RETRIES)
            )
            for msg_id in ids
        ]


def parse_message(message: dict[str, Any]) -> Email:
    """Convierte un mensaje de la Gmail API (format='full') en un `Email`."""
    payload = message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    date = datetime.fromtimestamp(int(message.get("internalDate", 0)) / 1000, tz=UTC)
    plain = _find_part(payload, "text/plain")
    html = _find_part(payload, "text/html")
    html_text = _html_to_text(html) if html is not None else ""

    return Email(
        id=message["id"],
        thread_id=message.get("threadId", ""),
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        date=date,
        snippet=unescape(message.get("snippet", "")),
        body=plain if plain is not None else html_text,
        html_text=html_text,
    )


def _find_part(part: dict[str, Any], mime_type: str) -> str | None:
    if part.get("mimeType") == mime_type and part.get("body", {}).get("data"):
        return _decode(part["body"]["data"])
    for sub in part.get("parts", []):
        found = _find_part(sub, mime_type)
        if found is not None:
            return found
    return None


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", "", html))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()
