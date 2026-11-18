"""Migraciones Alembic: el esquema migrado coincide con los modelos y los datos v0.4 se conservan.

Cada prueba usa su propia base SQLite en archivo. Para PostgreSQL, apuntar
SISGEF_PRUEBAS_DATABASE_URL a una base vacía y usar `alembic upgrade head`.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError

from app.db import Base, crear_motor
from app.esquema import _configuracion, actualizar_esquema

AHORA = "2026-11-01 10:00:00"


@pytest.fixture
def motor_temporal(tmp_path):
    motor = crear_motor(f"sqlite:///{tmp_path / 'migracion.db'}")
    yield motor
    motor.dispose()


def migrar(motor, destino: str, bajar: bool = False) -> None:
    with motor.connect() as conexion:
        configuracion = _configuracion(conexion)
        (command.downgrade if bajar else command.upgrade)(configuracion, destino)


def test_it60_el_esquema_migrado_coincide_con_los_modelos(motor_temporal):
    migrar(motor_temporal, "head")
    with motor_temporal.connect() as conexion:
        diferencias = compare_metadata(MigrationContext.configure(conexion), Base.metadata)
    assert diferencias == []


def test_it61_el_kardex_sigue_siendo_de_solo_insercion_tras_migrar(motor_temporal):
    migrar(motor_temporal, "head")
    with motor_temporal.connect() as conexion:
        triggers = {f[0] for f in conexion.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'"))}
    assert triggers == {f"tg_{t}_{s}" for t in ("asientos_controlados", "movimientos_stock")
                        for s in ("sin_update", "sin_delete")}


def _datos_v04(conexion) -> None:
    sentencias = [
        "INSERT INTO roles (id_rol, nombre, descripcion) VALUES (1, 'QF', 'Q.F.')",
        "INSERT INTO usuarios (id_usuario, rut, nombre, password_hash, id_rol, intentos_fallidos, creado_en, activo) "
        f"VALUES (1, '15555555-6', 'Q.F.', 'x', 1, 0, '{AHORA}', 1)",
        f"INSERT INTO programas_salud (id_programa, nombre, es_ges, creado_en) VALUES (1, 'Cardiovascular', 1, '{AHORA}')",
        "INSERT INTO medicamentos (id_medicamento, codigo, codigo_barras, nombre, unidades_envase, es_controlado, "
        "umbral_critico, id_programa, creado_en, activo) VALUES "
        f"(1, 'LOS50', '2000000000015', 'Losartán 50 mg comprimidos', 30, 0, 0, 1, '{AHORA}', 1), "
        f"(2, 'CLZ2', '2000000000022', 'Clonazepam 2 mg comprimidos', 30, 1, 0, NULL, '{AHORA}', 1)",
        f"INSERT INTO pacientes (id_paciente, rut_hmac, rut_enmascarado, nombre, creado_en) "
        f"VALUES (1, 'h1', '12.345.***-5', 'María', '{AHORA}')",
        "INSERT INTO recetas (id_receta, folio, id_paciente, fecha_emision, es_retenida, estado, creado_en) VALUES "
        f"(1, 'RX-1', 1, '2026-10-30', 0, 'DISPENSADA', '{AHORA}'), (2, 'RX-2', 1, '2026-10-31', 1, 'PENDIENTE', '{AHORA}')",
        "INSERT INTO detalles_receta (id_detalle_receta, id_receta, id_medicamento, cant_prescrita, cant_entregada, "
        f"posologia, creado_en) VALUES (1, 1, 1, 30, 30, '1 al día', '{AHORA}'), (2, 2, 2, 30, 0, '1 en la noche', '{AHORA}')",
        "INSERT INTO dispensaciones (id_dispensacion, id_receta, id_usuario, rut_retira_hmac, fecha_hora, "
        f"clave_idempotencia, estado, creado_en) VALUES (1, 1, 1, 'h2', '{AHORA}', 'clave-1', 'VIGENTE', '{AHORA}')",
    ]
    for sentencia in sentencias:
        conexion.execute(text(sentencia))
    conexion.commit()


def test_it62_datos_v04_se_migran_sin_perdida_y_la_migracion_es_reversible(motor_temporal):
    migrar(motor_temporal, "0001")
    with motor_temporal.connect() as conexion:
        _datos_v04(conexion)
    migrar(motor_temporal, "head")

    with motor_temporal.connect() as conexion:
        consulta = lambda sql: conexion.execute(text(sql)).all()  # noqa: E731
        assert consulta("SELECT folio, tipo_receta, total_entregas, entregas_realizadas, proxima_fecha_retiro "
                        "FROM recetas ORDER BY folio") == [("RX-1", "AGUDA", 1, 1, None),
                                                           ("RX-2", "RETENIDA", 1, 0, "2026-10-31")]
        assert consulta("SELECT cant_por_entrega FROM detalles_receta ORDER BY 1") == [(30,), (30,)]
        assert consulta("SELECT numero_entrega, retira_tipo FROM dispensaciones") == [(1, "TERCERO")]
        assert consulta("SELECT principio_activo, concentracion, forma_farmaceutica, unidad_dispensacion, es_ges "
                        "FROM medicamentos WHERE codigo = 'LOS50'") == [("Losartán", "50 mg", "COMPRIMIDO",
                                                                         "COMPRIMIDO", 1)]
        assert ("MEDICO",) in consulta("SELECT nombre FROM roles")
        # Las nuevas reglas quedan en la base: una receta retenida no puede tener 2 entregas
        with pytest.raises(DatabaseError):
            conexion.execute(text("UPDATE recetas SET total_entregas = 2 WHERE folio = 'RX-2'"))
        conexion.rollback()

    migrar(motor_temporal, "0001", bajar=True)
    with motor_temporal.connect() as conexion:
        assert conexion.execute(text("SELECT folio, es_retenida FROM recetas ORDER BY folio")).all() == [
            ("RX-1", 0), ("RX-2", 1)]
        assert "apoderados" not in inspect(conexion).get_table_names()
    migrar(motor_temporal, "head")


def test_it63_base_v04_sin_alembic_se_marca_y_se_actualiza_al_arrancar(motor_temporal):
    migrar(motor_temporal, "0001")
    with motor_temporal.connect() as conexion:
        _datos_v04(conexion)
        conexion.execute(text("DROP TABLE alembic_version"))  # como una base creada con create_all (v0.4)
        conexion.commit()
    actualizar_esquema(motor_temporal)
    with motor_temporal.connect() as conexion:
        ultima = ScriptDirectory.from_config(_configuracion(conexion)).get_current_head()
        assert conexion.execute(text("SELECT version_num FROM alembic_version")).scalar() == ultima
        assert conexion.execute(text("SELECT count(*) FROM recetas")).scalar() == 2
