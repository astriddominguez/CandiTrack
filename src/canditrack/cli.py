"""Línea de comandos de CandiTrack."""

import argparse
from pathlib import Path

from canditrack.mail.gmail import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_TOKEN_PATH,
    GmailSource,
    get_credentials,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="canditrack")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Lista correos de Gmail")
    fetch.add_argument("-q", "--query", default="newer_than:7d", help="Búsqueda de Gmail")
    fetch.add_argument("-n", "--max", type=int, default=10, help="Máximo de correos")
    fetch.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS_PATH)
    fetch.add_argument("--token", type=Path, default=DEFAULT_TOKEN_PATH)

    args = parser.parse_args(argv)

    if args.command == "fetch":
        source = GmailSource.from_credentials(get_credentials(args.credentials, args.token))
        for email in source.fetch(args.query, args.max):
            local_date = email.date.astimezone()
            print(f"{local_date:%Y-%m-%d %H:%M}  {email.sender[:40]:<40}  {email.subject}")


if __name__ == "__main__":
    main()
