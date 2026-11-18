"""Fuente de correo que solo descarga lo que aún no está guardado en local."""

from canditrack.mail.base import RemoteMailSource
from canditrack.models import Email
from canditrack.storage import EmailCache

# Los correos nuevos se guardan cada SAVE_EVERY descargas: si la descarga se corta
# (Ctrl+C, límite de Gmail...), lo ya descargado no se pierde.
SAVE_EVERY = 50


class CachedMailSource:
    """Implementación de `MailSource` que combina una fuente remota con la caché local."""

    def __init__(self, remote: RemoteMailSource, cache: EmailCache) -> None:
        self._remote = remote
        self._cache = cache
        self.downloaded = 0  # correos descargados en la última llamada a `fetch`

    def fetch(self, query: str = "", max_results: int = 50) -> list[Email]:
        ids = self._remote.list_ids(query, max_results)
        emails = self._cache.get_many(ids)
        missing = [msg_id for msg_id in ids if msg_id not in emails]

        for start in range(0, len(missing), SAVE_EVERY):
            new = self._remote.get_messages(missing[start : start + SAVE_EVERY])
            self._cache.save_many(new)
            emails.update((e.id, e) for e in new)

        self.downloaded = len(missing)
        return [emails[msg_id] for msg_id in ids]
