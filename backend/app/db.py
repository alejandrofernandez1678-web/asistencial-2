"""Motor y sesión de SQLAlchemy.

Funciona con PostgreSQL (entorno real) y con SQLite (desarrollo rápido y
pruebas). En SQLite se activan las claves foráneas, que vienen apagadas.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import config


class Base(DeclarativeBase):
    pass


def crear_motor(url: str):
    if url.startswith("sqlite"):
        opciones = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            opciones["poolclass"] = StaticPool
        motor = create_engine(url, **opciones)

        @event.listens_for(motor, "connect")
        def _activar_fk(conexion, _):
            conexion.execute("PRAGMA foreign_keys=ON")

        return motor
    return create_engine(url, pool_pre_ping=True)


motor = crear_motor(config.database_url)
SesionLocal = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    sesion = SesionLocal()
    try:
        yield sesion
    finally:
        sesion.close()
