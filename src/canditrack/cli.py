"""Línea de comandos de CandiTrack."""

import argparse
from datetime import date, timedelta
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
from canditrack.platforms import PLATFORMS, Platform, classify_emails, gmail_query
from canditrack.storage import EmailCache
from canditrack.summary import DEFAULT_PERIOD, format_summary, period_start, summarize
from canditrack.tracking import Application, build_applications

# Ancho de la columna de plataforma en `track`: el del nombre más largo.
_PLATFORM_WIDTH = max(len(name) for name in PLATFORMS)

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

    defaults = TrackConfig()
    track = sub.add_parser(
        "track",
        help="Muestra el estado de tus candidaturas",
        description=f"Los valores por defecto se pueden cambiar en {DEFAULT_CONFIG_PATH}.",
    )
    track.add_argument(
        "-s",
        "--since",
        type=parse_period,
        help=f"Periodo a revisar: 7d, 4w, 6m, 1y... (por defecto, {defaults.since})",
    )
    _add_selection_arguments(track)

    summary = sub.add_parser(
        "summary",
        help="Resumen: candidaturas enviadas en un periodo y en qué estado están",
        description=f"Los valores por defecto se pueden cambiar en {DEFAULT_CONFIG_PATH}.",
    )
    summary.add_argument(
        "-s",
        "--since",
        type=parse_period,
        help=f"Periodo hasta hoy: 7d, 4w, 3m... (por defecto, {DEFAULT_PERIOD})",
    )
    _add_selection_arguments(summary)

    serve = sub.add_parser(
        "serve",
        help="Arranca la API REST (documentación en /docs)",
        description="La API lee la base de datos local; no necesita acceso a Gmail.",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Dirección en la que escuchar (por defecto, 127.0.0.1: solo este equipo)",
    )
    serve.add_argument("--port", type=positive_int, default=8000, help="Puerto (por defecto, 8000)")
    serve.add_argument(
        "--db", type=Path, help="Base de datos local (por defecto, la de la configuración)"
    )
    serve.add_argument("--config", type=Path, help="Archivo de configuración")

    args = parser.parse_args(argv)
    if args.command == "serve":
        _run_serve(args, serve)
        return

    today = date.today()
    if args.command != "fetch":
        _resolve_options(args, track if args.command == "track" else summary)

    source = GmailSource.from_credentials(get_credentials(args.credentials, args.token))

    if args.command == "fetch":
        _run_fetch(source, args)
        return

    with EmailCache(args.db) as cache:
        cached = CachedMailSource(source, cache)
        if args.command == "track":
            read = _run_track(cached, args)
        else:
            read = _run_summary(cached, args, today)

    if read >= args.max:
        print(f"Aviso: se ha llegado al máximo de {args.max} correos; amplíalo con -n.")


def _resolve_options(args: argparse.Namespace, subparser: argparse.ArgumentParser) -> None:
    """Completa las opciones que no se han pasado con la configuración."""
    try:
        config = load_config(args.config)
    except ConfigError as e:
        subparser.error(str(e))
    _apply_config(args, config.track)


def _run_serve(args: argparse.Namespace, subparser: argparse.ArgumentParser) -> None:
    # Importaciones aquí: el resto de comandos no necesita cargar FastAPI ni uvicorn.
    import uvicorn

    from canditrack.api import create_app

    try:
        config = load_config(args.config)
    except ConfigError as e:
        subparser.error(str(e))
    db = args.db or config.track.db
    print(f"Base de datos: {db}  ·  documentación: http://{args.host}:{args.port}/docs")
    uvicorn.run(create_app(db), host=args.host, port=args.port)


def _run_fetch(source: GmailSource, args: argparse.Namespace) -> None:
    for email in source.fetch(args.query, args.max):
        local_date = email.date.astimezone()
        print(f"{local_date:%Y-%m-%d %H:%M}  {email.sender[:40]:<40}  {email.subject}")


def _run_track(source: CachedMailSource, args: argparse.Namespace) -> int:
    platforms = [PLATFORMS[name] for name in args.platform]
    query = gmail_query(platforms, args.since)
    applications, read = _load_applications(source, platforms, query, args.max)
    for app in applications:
        print(
            f"{app.updated.astimezone():%Y-%m-%d}  {app.platform:<{_PLATFORM_WIDTH}}  "
            f"{STATUS_LABELS[app.status]:<9}  {app.company[:35]:<35}  {app.position or '-'}"
        )
    print(
        f"\n{len(applications)} candidaturas ({read} correos revisados, "
        f"{source.downloaded} descargados de Gmail)"
    )
    return read


def _run_summary(source: CachedMailSource, args: argparse.Namespace, today: date) -> int:
    platforms = [PLATFORMS[name] for name in args.platform]
    # Gmail interpreta "after:" en su zona horaria: dos días de margen, y luego se filtra
    # por la fecha local. Se busca hasta hoy para conocer el estado actual de cada una.
    query = gmail_query(platforms, after=period_start(args.since, today) - timedelta(days=2))
    applications, read = _load_applications(source, platforms, query, args.max)
    labels = {p.name: p.label for p in platforms}
    print(format_summary(summarize(applications, labels, args.since, today)))
    return read


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    """Opciones comunes de `track` y `summary`.

    Sin valor por defecto (None): si no se pasan, se usa el archivo de configuración.
    """
    defaults = TrackConfig()
    parser.add_argument(
        "-p",
        "--platform",
        action="append",
        choices=sorted(PLATFORMS),
        help="Plataforma a revisar; se puede repetir (por defecto, todas)",
    )
    parser.add_argument(
        "-n",
        "--max",
        type=positive_int,
        help=f"Máximo de correos a leer (por defecto, {defaults.max})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help=f"Base de datos local con los correos ya descargados (por defecto, {defaults.db})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=f"Archivo de configuración (por defecto, {DEFAULT_CONFIG_PATH} si existe)",
    )
    _add_auth_arguments(parser)


def _apply_config(args: argparse.Namespace, config: TrackConfig) -> None:
    """Rellena las opciones que no se han pasado con lo que diga la configuración."""
    args.platform = args.platform or list(config.platforms) or sorted(PLATFORMS)
    if args.command == "track":
        args.since = args.since or config.since
    else:
        args.since = args.since or DEFAULT_PERIOD
    args.max = args.max or config.max
    args.db = args.db or config.db


def _load_applications(
    source: CachedMailSource, platforms: list[Platform], query: str, max_results: int
) -> tuple[list[Application], int]:
    """Descarga (o lee de la caché), clasifica y agrupa. Devuelve (candidaturas, correos)."""
    emails = source.fetch(query, max_results)
    return build_applications(classify_emails(emails, platforms)), len(emails)


def _add_auth_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS_PATH)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN_PATH)


if __name__ == "__main__":
    main()
