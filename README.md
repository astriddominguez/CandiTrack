# CandiTrack

[![CI](https://github.com/astriddominguez/CandiTrack/actions/workflows/ci.yml/badge.svg)](https://github.com/astriddominguez/CandiTrack/actions/workflows/ci.yml)

Sistema inteligente de seguimiento de candidaturas laborales conectado a Gmail.

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
