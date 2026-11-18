"""Versionado del esquema con Alembic (backend/migraciones).

* `actualizar_esquema`: lleva una base a la última versión sin borrar datos.
  Una base creada antes de adoptar Alembic (v0.4, sin tabla alembic_version)
  se marca primero como revisión 0001, que es exactamente ese esquema.
* `marcar_al_dia`: para una base recién creada desde los modelos (seed y
  pruebas), registra que ya está en la última versión.
"""

import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

CARPETA_BACKEND = Path(__file__).resolve().parents[1]
REVISION_BASE = "0001"


def _configuracion(conexion) -> Config:
    configuracion = Config(str(CARPETA_BACKEND / "alembic.ini"))
    configuracion.set_main_option("script_location", str(CARPETA_BACKEND / "migraciones"))
    configuracion.attributes["connection"] = conexion
    return configuracion


def _respaldar_sqlite(motor: Engine, conexion, configuracion: Config) -> None:
    """SQLite no revierte los cambios de estructura si una migración falla a mitad de camino:
    antes de migrar una base en archivo con datos, se guarda una copia junto a ella."""
    ruta = motor.url.database
    if motor.dialect.name != "sqlite" or not ruta or ruta == ":memory:" or not Path(ruta).exists():
        return
    actual = MigrationContext.configure(conexion).get_current_revision()
    destino = ScriptDirectory.from_config(configuracion).get_current_head()
    if actual != destino:
        shutil.copy2(ruta, f"{ruta}.respaldo-{actual or 'v0.4'}")


def actualizar_esquema(motor: Engine) -> None:
    with motor.connect() as conexion:
        tablas = set(inspect(conexion).get_table_names())
        configuracion = _configuracion(conexion)
        if "medicamentos" in tablas:
            _respaldar_sqlite(motor, conexion, configuracion)
        if "medicamentos" in tablas and "alembic_version" not in tablas:
            command.stamp(configuracion, REVISION_BASE)
        command.upgrade(configuracion, "head")


def marcar_al_dia(motor: Engine) -> None:
    with motor.connect() as conexion:
        command.stamp(_configuracion(conexion), "head")
        conexion.commit()
