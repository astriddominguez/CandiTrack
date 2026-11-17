# CandiTrack

[![CI](https://github.com/astriddominguez/CandiTrack/actions/workflows/ci.yml/badge.svg)](https://github.com/astriddominguez/CandiTrack/actions/workflows/ci.yml)

Sistema inteligente de seguimiento de candidaturas laborales conectado a Gmail.

## Puesta en marcha

1. Configura el acceso a Gmail siguiendo [docs/gmail-setup.md](docs/gmail-setup.md)
   (proyecto de Google Cloud, OAuth y `credentials.json`).
2. Instala dependencias y prueba la conexión:

   ```bash
   uv sync
   uv run canditrack fetch            # últimos correos de los últimos 7 días
   ```

## Desarrollo

```bash
uv sync               # crea .venv e instala dependencias (incluye dev)

uv run ruff check .   # lint
uv run ruff format .  # formateo
uv run pytest         # tests
```

Para añadir dependencias: `uv add <paquete>` (o `uv add --dev <paquete>`).

## Flujo de trabajo

- `main` está protegida: los cambios entran solo por Pull Request.
- La CI (GitHub Actions) ejecuta lint y tests en cada PR.

## Versiones

Las versiones siguen [SemVer](https://semver.org/lang/es/) y se publican con
[release-please](https://github.com/googleapis/release-please):

1. Los commits (o títulos de PR con *squash*) siguen
   [Conventional Commits](https://www.conventionalcommits.org/es/): `feat:`, `fix:`, `docs:`, `ci:`...
2. Al fusionar en `main`, release-please abre o actualiza un **PR de release** con la nueva
   versión y el `CHANGELOG.md` (`feat` → versión menor, `fix` → parche).
3. Al fusionar ese PR se crean el tag `vX.Y.Z` y la GitHub Release.

Requiere el secreto `RELEASE_PLEASE_TOKEN` (fine-grained token con permisos *Contents* y
*Pull requests* de lectura y escritura sobre este repositorio).

