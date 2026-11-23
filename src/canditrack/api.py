"""API REST de CandiTrack (FastAPI). Solo lee de la base de datos local, no llama a Gmail.

La especificación OpenAPI se genera sola a partir de este código:
  /openapi.json  la especificación
  /docs          documentación interactiva (Swagger UI)
  /redoc         documentación (ReDoc)
"""

from datetime import date, datetime
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from canditrack.config import normalize_period
from canditrack.models import EventType
from canditrack.platforms import PLATFORMS, Platform, classify_emails
from canditrack.stats import DEFAULT_STALE_DAYS, PlatformStats, compute_stats
from canditrack.storage import DEFAULT_DB_PATH, EmailCache
from canditrack.summary import DEFAULT_PERIOD, Counts, period_start, summarize
from canditrack.tracking import Application, build_applications, filter_applications

API_PREFIX = "/api/v1"
VERSION = version("canditrack")
PERIOD_PATTERN = r"^[1-9]\d*[dwmy]$"  # 7d, 4w, 3m, 1y...


class PlatformName(StrEnum):
    """Plataformas soportadas: en OpenAPI aparece como lista cerrada de valores.

    Se declara explícitamente (y no a partir de PLATFORMS) para que mypy y el editor
    conozcan sus valores. Un test comprueba que coincide con el registro.
    """

    LINKEDIN = "linkedin"
    INFOJOBS = "infojobs"
    INDEED = "indeed"
    TECNOEMPLEO = "tecnoempleo"


# --- Modelos de respuesta (definen el esquema que se publica en OpenAPI) ---


class Health(BaseModel):
    """Estado del servicio."""

    status: Literal["ok"] = Field(description="Siempre `ok` si el servicio responde.")
    version: str = Field(description="Versión de CandiTrack.", examples=["0.8.0"])


class PlatformOut(BaseModel):
    """Plataforma de empleo soportada."""

    name: PlatformName = Field(description="Identificador, para usar en los filtros.")
    label: str = Field(description="Nombre para mostrar.", examples=["LinkedIn"])


class ApplicationOut(BaseModel):
    """Candidatura con su estado actual (el de su evento más reciente)."""

    id: str = Field(description="Identificador estable.", examples=["3f9a1c2b7d4e"])
    platform: PlatformName
    company: str = Field(examples=["Acme Corp"])
    position: str | None = Field(description="Puesto, si se conoce.", examples=["AI Engineer"])
    status: EventType = Field(
        description="`submitted` (enviada), `viewed` (vista), `rejected` (rechazada) o "
        "`closed` (proceso cerrado)."
    )
    submitted_at: datetime | None = Field(description="Fecha de envío, si se conoce.")
    updated_at: datetime = Field(description="Fecha del evento más reciente.")

    @classmethod
    def from_application(cls, app: Application) -> "ApplicationOut":
        submitted = next((e.date for e in app.events if e.type is EventType.SUBMITTED), None)
        return cls(
            id=app.id,
            platform=PlatformName(app.platform),
            company=app.company,
            position=app.position,
            status=app.status,
            submitted_at=submitted,
            updated_at=app.updated,
        )


class ApplicationPage(BaseModel):
    """Una página de candidaturas."""

    items: list[ApplicationOut]
    total: int = Field(description="Total de candidaturas que cumplen los filtros.")
    limit: int
    offset: int


class EventOut(BaseModel):
    """Un correo de la candidatura, ya clasificado."""

    type: EventType
    date: datetime
    position: str | None = Field(description="Puesto según este correo, si lo dice.")
    email_id: str = Field(description="ID del correo en Gmail.")


class ApplicationDetail(ApplicationOut):
    """Candidatura con todos sus eventos, del más antiguo al más reciente."""

    events: list[EventOut]

    @classmethod
    def from_application(cls, app: Application) -> "ApplicationDetail":
        return cls(
            **ApplicationOut.from_application(app).model_dump(),
            events=[
                EventOut(type=e.type, date=e.date, position=e.position, email_id=e.email_id)
                for e in app.events
            ],
        )


class Error(BaseModel):
    """Respuesta de error."""

    detail: str = Field(examples=["Candidatura no encontrada"])


class SummaryRow(BaseModel):
    """Recuentos de una plataforma (o del total)."""

    platform: PlatformName | None = Field(description="`null` en la fila del total.")
    label: str = Field(examples=["LinkedIn"])
    applied: int = Field(description="Candidaturas enviadas en el periodo.")
    alive: int = Field(description="De ellas, enviadas o vistas: sin respuesta negativa.")
    rejected: int
    closed: int = Field(description="Con el proceso cerrado.")


class SummaryOut(BaseModel):
    """Candidaturas enviadas en el periodo y su estado actual (como `canditrack summary`)."""

    period: str = Field(examples=["60d"])
    start: date
    end: date
    platforms: list[SummaryRow]
    total: SummaryRow


class StatsRow(BaseModel):
    """Estadísticas de una plataforma (o del total)."""

    platform: PlatformName | None = Field(description="`null` en la fila del total.")
    label: str = Field(examples=["LinkedIn"])
    sent: int = Field(description="Candidaturas enviadas en el periodo.")
    responded: int = Field(description="De ellas, vistas o rechazadas por la empresa.")
    rejected: int = Field(description="De ellas, rechazadas (estado actual).")
    no_response: int = Field(
        description="De ellas, solo enviadas y sin novedades en `stale_days` días o más."
    )
    median_days_to_response: float | None = Field(
        description="Mediana de días entre el envío y la primera respuesta; `null` si no hay.",
        examples=[3.2],
    )
    notifies_views: bool | None = Field(
        description="Si la plataforma avisa por correo cuando ven tu candidatura. Si no, "
        "`responded` sale más bajo de lo real. `null` en el total."
    )
    notifies_rejections: bool | None = Field(
        description="Si la plataforma avisa por correo de los rechazos. Si no, `rejected` y "
        "`responded` salen más bajos de lo real. `null` en el total."
    )


class StatsOut(BaseModel):
    """Estadísticas por plataforma (como `canditrack stats`)."""

    period: str = Field(examples=["60d"])
    start: date
    end: date
    stale_days: int = Field(examples=[21])
    platforms: list[StatsRow]
    total: StatsRow


# --- Aplicación ---


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    """Crea la aplicación. `db_path` es la base de datos que rellena `canditrack track`."""
    app = FastAPI(
        title="CandiTrack API",
        version=VERSION,
        description=(
            "Seguimiento de candidaturas de empleo detectadas en Gmail "
            "(LinkedIn, InfoJobs, Indeed y Tecnoempleo). Los datos salen de la base de datos "
            "local; para actualizarlos, ejecuta `canditrack track`."
        ),
    )
    app.state.db_path = db_path

    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health", tags=["sistema"], summary="Estado del servicio")
    def health() -> Health:
        return Health(status="ok", version=VERSION)

    @router.get("/platforms", tags=["plataformas"], summary="Plataformas soportadas")
    def list_platforms() -> list[PlatformOut]:
        return [PlatformOut(name=PlatformName(p.name), label=p.label) for p in PLATFORMS.values()]

    @router.get(
        "/applications",
        tags=["candidaturas"],
        summary="Lista de candidaturas",
        description="Ordenadas de la actualizada más recientemente a la más antigua.",
    )
    def list_applications(
        request: Request,
        platform: Annotated[
            PlatformName | None, Query(description="Filtrar por plataforma.")
        ] = None,
        status: Annotated[EventType | None, Query(description="Filtrar por estado actual.")] = None,
        company: Annotated[
            str | None,
            Query(
                description="Empresa que contenga este texto (sin distinguir mayúsculas ni "
                "acentos).",
                min_length=1,
                examples=["arelance"],
            ),
        ] = None,
        since: Annotated[
            str | None,
            Query(
                description="Solo las actualizadas en este periodo hasta hoy: 7d, 4w, 3m, 1y...",
                pattern=PERIOD_PATTERN,
                examples=["30d"],
            ),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=500, description="Tamaño de la página.")] = 50,
        offset: Annotated[int, Query(ge=0, description="Candidaturas a saltar.")] = 0,
    ) -> ApplicationPage:
        applications = filter_applications(
            _load_applications(request.app.state.db_path),
            platform=platform,
            status=status,
            company=company,
            updated_since=period_start(normalize_period(since), date.today()) if since else None,
        )

        page = applications[offset : offset + limit]
        return ApplicationPage(
            items=[ApplicationOut.from_application(a) for a in page],
            total=len(applications),
            limit=limit,
            offset=offset,
        )

    @router.get(
        "/applications/{application_id}",
        tags=["candidaturas"],
        summary="Detalle de una candidatura",
        responses={404: {"model": Error, "description": "No existe ninguna con ese ID."}},
    )
    def get_application(request: Request, application_id: str) -> ApplicationDetail:
        for app_ in _load_applications(request.app.state.db_path):
            if app_.id == application_id:
                return ApplicationDetail.from_application(app_)
        raise HTTPException(status_code=404, detail="Candidatura no encontrada")

    @router.get(
        "/summary",
        tags=["resumen"],
        summary="Resumen del periodo",
        description=(
            "Candidaturas **enviadas** en el periodo, por plataforma, y su estado actual. "
            "Las enviadas antes del periodo no cuentan aunque se resuelvan dentro de él."
        ),
    )
    def get_summary(
        request: Request,
        since: Annotated[
            str,
            Query(description="Periodo hasta hoy: 7d, 4w, 3m, 1y...", pattern=PERIOD_PATTERN),
        ] = DEFAULT_PERIOD,
        platform: Annotated[
            list[PlatformName] | None,
            Query(description="Plataformas a incluir; se puede repetir (por defecto, todas)."),
        ] = None,
    ) -> SummaryOut:
        names = list(dict.fromkeys(platform)) if platform else list(PLATFORMS)
        labels = {name: PLATFORMS[name].label for name in names}
        summary = summarize(
            _load_applications(request.app.state.db_path),
            labels,
            normalize_period(since),
            date.today(),
        )
        name_by_label = {label: name for name, label in labels.items()}
        return SummaryOut(
            period=summary.period,
            start=summary.start,
            end=summary.end,
            platforms=[
                _summary_row(PlatformName(name_by_label[label]), label, counts)
                for label, counts in summary.rows.items()
            ],
            total=_summary_row(None, "Total", summary.total),
        )

    @router.get(
        "/stats",
        tags=["resumen"],
        summary="Estadísticas por plataforma",
        description=(
            "Respuestas, rechazos, candidaturas sin noticias y tiempo hasta la primera "
            "respuesta, sobre las candidaturas **enviadas** en el periodo. Ojo con las "
            "plataformas con `notifies_views` o `notifies_rejections` a `false`: sus cifras "
            "de respuesta salen más bajas de lo real."
        ),
    )
    def get_stats(
        request: Request,
        since: Annotated[
            str,
            Query(description="Periodo hasta hoy: 7d, 4w, 3m, 1y...", pattern=PERIOD_PATTERN),
        ] = DEFAULT_PERIOD,
        stale_days: Annotated[
            int,
            Query(ge=1, le=365, description="Días sin novedades para contar como sin respuesta."),
        ] = DEFAULT_STALE_DAYS,
        platform: Annotated[
            list[PlatformName] | None,
            Query(description="Plataformas a incluir; se puede repetir (por defecto, todas)."),
        ] = None,
    ) -> StatsOut:
        names = list(dict.fromkeys(platform)) if platform else list(PLATFORMS)
        stats = compute_stats(
            _load_applications(request.app.state.db_path),
            [PLATFORMS[name] for name in names],
            normalize_period(since),
            date.today(),
            stale_days,
        )
        return StatsOut(
            period=stats.period,
            start=stats.start,
            end=stats.end,
            stale_days=stats.stale_days,
            platforms=[_stats_row(stats.platforms[name], row) for name, row in stats.rows.items()],
            total=_stats_row(None, stats.total),
        )

    app.include_router(router)
    return app


def _summary_row(platform: "PlatformName | None", label: str, counts: Counts) -> SummaryRow:
    return SummaryRow(
        platform=platform,
        label=label,
        applied=counts.applied,
        alive=counts.alive,
        rejected=counts.rejected,
        closed=counts.closed,
    )


def _load_applications(db_path: Path) -> list[Application]:
    """Lee los correos guardados, los clasifica y los agrupa en candidaturas."""
    with EmailCache(db_path) as cache:
        emails = cache.all()
    return build_applications(classify_emails(emails, PLATFORMS.values()))


def _stats_row(platform: Platform | None, stats: PlatformStats) -> StatsRow:
    return StatsRow(
        platform=PlatformName(platform.name) if platform else None,
        label=platform.label if platform else "Total",
        sent=stats.sent,
        responded=stats.responded,
        rejected=stats.rejected,
        no_response=stats.no_response,
        median_days_to_response=(
            round(stats.median_days_to_response, 1)
            if stats.median_days_to_response is not None
            else None
        ),
        notifies_views=platform.notifies_views if platform else None,
        notifies_rejections=platform.notifies_rejections if platform else None,
    )
