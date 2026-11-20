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

## Uso

`canditrack track` lee los correos de las plataformas de empleo y muestra cada candidatura
con su estado más reciente (`enviada`, `vista`, `rechazada` o `cerrada`):

```bash
uv run canditrack track                        # todas las plataformas, últimos 30 días
uv run canditrack track -p linkedin -p indeed  # solo esas plataformas
uv run canditrack track --since 6m -n 1000     # periodo (7d, 4w, 6m, 1y...) y máximo de correos
```

Plataformas soportadas: `linkedin`, `infojobs`, `indeed` y `tecnoempleo`. Solo se descargan los correos de
sus remitentes, así que las alertas de empleo y el resto del buzón no cuentan para el máximo.

Los correos descargados se guardan en una base de datos SQLite local (`canditrack.db`, o la
ruta que indiques con `--db`). La primera ejecución puede tardar unos minutos (Gmail limita
cuántos correos se pueden leer por minuto); las siguientes solo descargan los correos nuevos.
El archivo contiene tus correos: está en `.gitignore` y no debe compartirse.

### Resumen

`canditrack summary` cuenta las candidaturas **enviadas** en los últimos días, por plataforma,
y en qué estado están ahora (vivas, rechazadas o con el proceso cerrado):

```bash
uv run canditrack summary          # últimos 60 días hasta hoy
uv run canditrack summary -s 30d   # otro periodo: 7d, 4w, 3m, 1y...
```

```
CandiTrack · últimos 60 días (20 sep – 19 nov 2026)

          Postuladas  Vivas  Rechazadas  Cerradas
LinkedIn         131     94          37         0
InfoJobs          51     40           0        11
Indeed            32     32           0         0
Total            214    166          37        11
```

Solo cuentan las candidaturas enviadas dentro del periodo, con su estado de hoy. Admite las
mismas opciones `-p`, `-n`, `--db` y `--config` que `track`.

### Estadísticas

`canditrack stats` compara las plataformas: cuántas candidaturas reciben respuesta, cuántas
se rechazan, cuántas siguen sin noticias y cuánto tarda la primera respuesta.

```bash
uv run canditrack stats                # últimos 60 días
uv run canditrack stats -s 30d --stale 2w
```

```
             Enviadas  Con respuesta  Rechazadas  Sin respuesta  Días hasta respuesta
LinkedIn          131       54 (41%)    39 (30%)       51 (39%)                     3
Tecnoempleo        10        3 (30%)      0 (0%)         0 (0%)                    <1
```

- **Con respuesta**: la empresa vio la candidatura o la rechazó.
- **Sin respuesta**: solo enviada y sin novedades en 21 días o más (`--stale`).
- **Días hasta respuesta**: mediana entre el envío y la primera respuesta.

No todas las plataformas avisan por correo de lo mismo (InfoJobs e Indeed no avisan de
vistas ni rechazos; Tecnoempleo, de rechazos): la salida lo indica, porque sus cifras de
respuesta salen más bajas de lo real.

### API REST

`canditrack serve` arranca una API REST (FastAPI) que sirve los mismos datos. Lee solo la
base de datos local, sin conectar con Gmail: para actualizarla, ejecuta `canditrack track`.

```bash
uv run canditrack serve    # http://127.0.0.1:8000
```

La especificación **OpenAPI** se genera automáticamente: `/openapi.json`, con documentación
interactiva en `/docs` (Swagger UI) y `/redoc`.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/health` | Estado del servicio y versión |
| `GET` | `/api/v1/platforms` | Plataformas soportadas |
| `GET` | `/api/v1/applications` | Candidaturas; filtros `platform`, `status`, `since` y paginación `limit`/`offset` |
| `GET` | `/api/v1/applications/{id}` | Una candidatura con todos sus eventos (404 si no existe) |
| `GET` | `/api/v1/summary` | Resumen del periodo (`since`, por defecto `60d`; `platform` repetible) |
| `GET` | `/api/v1/stats` | Estadísticas por plataforma (`since`, `stale_days`, `platform`) |

```bash
curl "http://127.0.0.1:8000/api/v1/applications?status=rejected&limit=5"
```

Por defecto solo escucha en `127.0.0.1` (este equipo); usa `--host` y `--port` para cambiarlo.

### Configuración

Para no repetir opciones, copia [canditrack.example.toml](canditrack.example.toml) como
`canditrack.toml` y ajusta los valores por defecto (plataformas, periodo, máximo y base de
datos). Es opcional; para usar otro archivo, `--config ruta/al/archivo.toml`.

Prioridad: opción en la línea de comandos > `canditrack.toml` > valor por defecto.

## Desarrollo

```bash
uv sync               # crea .venv e instala dependencias (incluye dev)

uv run ruff check .   # lint
uv run ruff format .  # formateo
uv run mypy           # comprobación de tipos (modo estricto)
uv run pytest --cov   # tests y cobertura (mínimo 95 %)
```

Para añadir dependencias: `uv add <paquete>` (o `uv add --dev <paquete>`).

## Flujo de trabajo

- `main` está protegida: los cambios entran solo por Pull Request.
- La CI (GitHub Actions) ejecuta lint, comprobación de tipos y tests en cada PR, y falla si
  la cobertura baja del 95 %. La tabla de cobertura sale en el resumen de cada ejecución.

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

