"""Línea de comandos de CandiTrack."""

import argparse
import re
from pathlib import Path

from canditrack.mail.cached import CachedMailSource
from canditrack.mail.gmail import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_TOKEN_PATH,
    GmailSource,
    get_credentials,
)
from canditrack.models import EventType
from canditrack.platforms import PLATFORMS, gmail_query
from canditrack.storage import DEFAULT_DB_PATH, EmailCache
from canditrack.tracking import build_applications

STATUS_LABELS = {
    EventType.SUBMITTED: "enviada",
    EventType.VIEWED: "vista",
    EventType.REJECTED: "rechazada",
    EventType.CLOSED: "cerrada",
}

_PERIOD = re.compile(r"^(\d+)([dwmy])$")


def parse_period(value: str) -> str:
    """Convierte "7d", "4w", "6m" o "1y" al formato de `newer_than:` de Gmail."""
    match = _PERIOD.match(value.strip().lower())
    if not match or int(match[1]) == 0:
        raise argparse.ArgumentTypeError(
            f"periodo no válido: {value!r} (usa p. ej. 7d, 4w, 6m o 1y)"
        )
    amount, unit = int(match[1]), match[2]
    # Gmail no entiende semanas: se pasan a días.
    return f"{amount * 7}d" if unit == "w" else f"{amount}{unit}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="canditrack")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Lista correos de Gmail")
    fetch.add_argument("-q", "--query", default="newer_than:7d", help="Búsqueda de Gmail")
    fetch.add_argument("-n", "--max", type=int, default=10, help="Máximo de correos")
    _add_auth_arguments(fetch)

    track = sub.add_parser("track", help="Muestra el estado de tus candidaturas")
    track.add_argument(
        "-p",
        "--platform",
        action="append",
        choices=sorted(PLATFORMS),
        help="Plataforma a revisar; se puede repetir (por defecto, todas)",
    )
    track.add_argument(
        "-s",
        "--since",
        type=parse_period,
        default="30d",
        help="Periodo a revisar: 7d, 4w, 6m, 1y... (por defecto, 30d)",
    )
    track.add_argument("-n", "--max", type=int, default=500, help="Máximo de correos a leer")
    track.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Base de datos local con los correos ya descargados (por defecto, {DEFAULT_DB_PATH})",
    )
    _add_auth_arguments(track)

    args = parser.parse_args(argv)
    source = GmailSource.from_credentials(get_credentials(args.credentials, args.token))

    if args.command == "fetch":
        for email in source.fetch(args.query, args.max):
            local_date = email.date.astimezone()
            print(f"{local_date:%Y-%m-%d %H:%M}  {email.sender[:40]:<40}  {email.subject}")

    elif args.command == "track":
        with EmailCache(args.db) as cache:
            _track(CachedMailSource(source, cache), args)


def _track(source: CachedMailSource, args: argparse.Namespace) -> None:
    platforms = [PLATFORMS[name] for name in args.platform or sorted(PLATFORMS)]
    emails = source.fetch(gmail_query(platforms, args.since), args.max)

    events = []
    for email in emails:
        for platform in platforms:
            if event := platform.classifier.classify(email):
                events.append(event)
                break

    applications = build_applications(events)
    for app in applications:
        print(
            f"{app.updated.astimezone():%Y-%m-%d}  {app.platform:<8}  "
            f"{STATUS_LABELS[app.status]:<9}  {app.company[:35]:<35}  {app.position or '-'}"
        )
    print(
        f"\n{len(applications)} candidaturas ({len(emails)} correos revisados, "
        f"{source.downloaded} descargados de Gmail)"
    )
    if len(emails) >= args.max:
        print(f"Aviso: se ha llegado al máximo de {args.max} correos; amplíalo con -n.")


def _add_auth_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS_PATH)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN_PATH)


if __name__ == "__main__":
    main()
