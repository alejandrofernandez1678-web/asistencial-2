"""Entorno de Alembic: usa el mismo motor y los mismos modelos que la aplicación.

En SQLite, Alembic modifica tablas copiándolas (modo batch). Para eso se
apagan las claves foráneas durante la migración y al final se verifica que
no haya quedado ninguna referencia rota (PRAGMA foreign_key_check).
"""

from alembic import context
from sqlalchemy import text

from app import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.db import Base, motor

target_metadata = Base.metadata


def ejecutar() -> None:
    conexion_externa = context.config.attributes.get("connection")
    conexion = conexion_externa or motor.connect()
    es_sqlite = conexion.dialect.name == "sqlite"
    try:
        if es_sqlite:
            conexion.commit()  # PRAGMA foreign_keys no tiene efecto dentro de una transacción
            conexion.exec_driver_sql("PRAGMA foreign_keys=OFF")
        context.configure(connection=conexion, target_metadata=target_metadata,
                          render_as_batch=True, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        if es_sqlite:
            rotas = conexion.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if rotas:
                raise RuntimeError(f"La migración dejó claves foráneas rotas: {rotas}")
            conexion.exec_driver_sql("PRAGMA foreign_keys=ON")
        conexion.commit()
    finally:
        if conexion_externa is None:
            conexion.close()


if context.is_offline_mode():
    raise SystemExit("SISGEF no usa migraciones en modo offline; ejecute contra una base.")
ejecutar()
