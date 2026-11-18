"""Línea de comandos de CandiTrack."""

import argparse
from pathlib import Path

from canditrack.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    TrackConfig,
    load_config,
    normalize_period,
)
from canditrack.mail.cached import CachedMailSource
from canditrack.mail.gmail import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_TOKEN_PATH,
    GmailSource,
    get_credentials,
)
from canditrack.models import EventType
from canditrack.platforms import PLATFORMS, gmail_query
from canditrack.storage import EmailCache
from canditrack.tracking import build_applications

STATUS_LABELS = {
    EventType.SUBMITTED: "enviada",
    EventType.VIEWED: "vista",
    EventType.REJECTED: "rechazada",
    EventType.CLOSED: "cerrada",
}


def parse_period(value: str) -> str:
    """Tipo de argparse para periodos ("7d", "4w", "6m", "1y")."""
    try:
        return normalize_period(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def positive_int(value: str) -> int:
    """Tipo de argparse para enteros mayores que 0."""
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number <= 0:
        raise argparse.ArgumentTypeError(f"tiene que ser un entero mayor que 0: {value!r}")
    return number


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="canditrack")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Lista correos de Gmail")
    fetch.add_argument("-q", "--query", default="newer_than:7d", help="Búsqueda de Gmail")
    fetch.add_argument("-n", "--max", type=int, default=10, help="Máximo de correos")
    _add_auth_arguments(fetch)

    # Sin valor por defecto (None): si no se pasan, se usa el archivo de configuración.
    defaults = TrackConfig()
    track = sub.add_parser(
        "track",
        help="Muestra el estado de tus candidaturas",
        description=f"Los valores por defecto se pueden cambiar en {DEFAULT_CONFIG_PATH}.",
    )
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
        help=f"Periodo a revisar: 7d, 4w, 6m, 1y... (por defecto, {defaults.since})",
    )
    track.add_argument(
        "-n",
        "--max",
        type=positive_int,
        help=f"Máximo de correos a leer (por defecto, {defaults.max})",
    )
    track.add_argument(
        "--db",
        type=Path,
        help=f"Base de datos local con los correos ya descargados (por defecto, {defaults.db})",
    )
    track.add_argument(
        "--config",
        type=Path,
        help=f"Archivo de configuración (por defecto, {DEFAULT_CONFIG_PATH} si existe)",
    )
    _add_auth_arguments(track)

    args = parser.parse_args(argv)

    if args.command == "track":
        try:
            config = load_config(args.config)
        except ConfigError as e:
            track.error(str(e))
        _apply_config(args, config.track)

    source = GmailSource.from_credentials(get_credentials(args.credentials, args.token))

    if args.command == "fetch":
        for email in source.fetch(args.query, args.max):
            local_date = email.date.astimezone()
            print(f"{local_date:%Y-%m-%d %H:%M}  {email.sender[:40]:<40}  {email.subject}")

    elif args.command == "track":
        with EmailCache(args.db) as cache:
            _track(CachedMailSource(source, cache), args)


def _apply_config(args: argparse.Namespace, config: TrackConfig) -> None:
    """Rellena las opciones que no se han pasado con lo que diga la configuración."""
    args.platform = args.platform or list(config.platforms) or sorted(PLATFORMS)
    args.since = args.since or config.since
    args.max = args.max or config.max
    args.db = args.db or config.db


def _track(source: CachedMailSource, args: argparse.Namespace) -> None:
    platforms = [PLATFORMS[name] for name in args.platform]
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
