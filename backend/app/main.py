"""Punto de entrada de la API SISGEF-Asistencial (FastAPI)."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from . import models  # noqa: F401  (registra las tablas en Base.metadata)
from .api import admin, atencion, auth, dispensacion, fofar, inventario, publico, reportes
from .config import config
from .db import motor
from .domain.errores import ReglaNegocioError
from .esquema import actualizar_esquema

CARPETA_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

CABECERAS_SEGURIDAD = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    if config.entorno == "desarrollo":
        actualizar_esquema(motor)  # migraciones Alembic: crea o actualiza la base sin borrar datos
    yield


es_produccion = config.entorno == "produccion"
app = FastAPI(title="SISGEF-Asistencial API", version="0.3.0", lifespan=ciclo_de_vida,
              docs_url=None if es_produccion else "/docs", redoc_url=None,
              openapi_url=None if es_produccion else "/openapi.json")


@app.middleware("http")
async def cabeceras_seguridad(request: Request, siguiente):
    respuesta = await siguiente(request)
    for nombre, valor in CABECERAS_SEGURIDAD.items():
        if nombre == "Content-Security-Policy" and request.url.path in ("/docs", "/openapi.json"):
            continue  # Swagger UI necesita cargar sus propios recursos (solo en desarrollo)
        respuesta.headers.setdefault(nombre, valor)
    return respuesta


@app.exception_handler(ReglaNegocioError)
async def error_de_negocio(_: Request, error: ReglaNegocioError):
    estado = 404 if error.codigo == "NO_ENCONTRADO" else 422
    return JSONResponse(status_code=estado, content={"codigo": error.codigo, "detail": error.mensaje})


@app.exception_handler(IntegrityError)
async def error_de_integridad(_: Request, __: IntegrityError):
    # No se expone el detalle SQL al cliente.
    return JSONResponse(status_code=409, content={"codigo": "CONFLICTO",
                                                  "detail": "La operación entra en conflicto con otro registro. Reintente."})


@app.get("/api/salud", tags=["sistema"])
def salud():
    return {"estado": "ok", "version": app.version}


for modulo in (auth, inventario, dispensacion, atencion, fofar, reportes, publico, admin):
    app.include_router(modulo.router)

if CARPETA_FRONTEND.exists():
    app.mount("/", StaticFiles(directory=CARPETA_FRONTEND, html=True), name="frontend")
