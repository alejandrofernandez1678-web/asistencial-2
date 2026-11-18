"""Esquema CESFAM v0.5: recetas crónicas, apoderados, despacho y catálogo farmacéutico

Cambios (ver docs/PLAN_v0.5.md):
  * Tablas nuevas: sectores, apoderados, despachos_domicilio.
  * pacientes: sector, PRAIS, postrado, alergias, dirección.
  * medicamentos: principio activo, concentración, forma farmacéutica,
    unidad de dispensación y GES.
  * recetas: tipo (AGUDA / CRONICA / RETENIDA), entregas autorizadas y
    realizadas, intervalo, próxima fecha de retiro y médico; se elimina
    es_retenida (pasa a ser tipo = RETENIDA).
  * detalles_receta: cantidad por entrega.
  * dispensaciones: número de entrega y quién retira (paciente, apoderado o tercero).
  * movimientos_stock: el tipo admite DEVOLUCION.
  * Rol MEDICO.

Los datos existentes se migran sin pérdida: cada receta pasa a AGUDA o
RETENIDA con una entrega, y el nombre de cada medicamento se separa en
principio activo, concentración y forma.

Revisión: 0002
Anterior: 0001
Fecha: 2026-11-17
"""

import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TIPOS_MOVIMIENTO_V04 = "'INGRESO','DISPENSACION','ANULACION_DISPENSACION','MERMA','AJUSTE','ANULACION_LOTE'"
TIPOS_MOVIMIENTO_V05 = TIPOS_MOVIMIENTO_V04 + ",'DEVOLUCION'"

# Palabra que sigue a la concentración en el nombre -> (forma farmacéutica, unidad de dispensación)
FORMAS_POR_TEXTO = {
    "comprimido": ("COMPRIMIDO", "COMPRIMIDO"), "capsula": ("CAPSULA", "CAPSULA"),
    "inhalador": ("INHALADOR", "INHALADOR"), "jarabe": ("JARABE", "FRASCO"),
    "suspension": ("SUSPENSION", "FRASCO"), "gotas": ("GOTAS", "FRASCO"),
    "solucion": ("SOLUCION_INYECTABLE", "AMPOLLA"), "ampolla": ("SOLUCION_INYECTABLE", "AMPOLLA"),
    "crema": ("CREMA", "POMO"), "frasco": ("SOLUCION_INYECTABLE", "FRASCO"),
}
_NOMBRE = re.compile(r"^(?P<activo>.+?)\s+(?P<conc>\d+(?:[.,]\d+)?\s*(?:mg|mcg|g|ui|ml|%)(?:\s*/\s*(?:\d+(?:[.,]\d+)?\s*)?[a-z]+)?)\s*(?P<resto>.*)$",
                     re.IGNORECASE)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def separar_nombre(nombre: str) -> tuple[str, str | None, str, str]:
    """"Losartán 50 mg comprimidos" -> ("Losartán", "50 mg", "COMPRIMIDO", "COMPRIMIDO")."""
    coincidencia = _NOMBRE.match(nombre.strip())
    if not coincidencia:
        return nombre.strip(), None, "OTRO", "UNIDAD"
    resto = _sin_tildes(coincidencia["resto"])
    forma, unidad = next((v for clave, v in FORMAS_POR_TEXTO.items() if resto.startswith(clave)), ("OTRO", "UNIDAD"))
    return coincidencia["activo"].strip(), coincidencia["conc"].strip(), forma, unidad


# --------------------------------------------------------------- triggers
def _triggers_sqlite(tabla: str, crear: bool) -> None:
    for sufijo, evento in (("sin_update", "UPDATE"), ("sin_delete", "DELETE")):
        if crear:
            op.execute(f"CREATE TRIGGER tg_{tabla}_{sufijo} BEFORE {evento} ON {tabla} "
                       f"BEGIN SELECT RAISE(ABORT, '{tabla} es de solo insercion'); END;")
        else:
            op.execute(f"DROP TRIGGER IF EXISTS tg_{tabla}_{sufijo}")


def _cambiar_tipos_movimiento(tipos: str) -> None:
    """El kardex es de solo inserción: en SQLite la tabla se reconstruye, así que
    los triggers se quitan antes y se vuelven a crear después."""
    es_sqlite = op.get_bind().dialect.name == "sqlite"
    if es_sqlite:
        _triggers_sqlite("movimientos_stock", crear=False)
    with op.batch_alter_table("movimientos_stock") as batch:
        batch.drop_constraint("ck_movimientos_tipo", type_="check")
        batch.create_check_constraint("ck_movimientos_tipo", f"tipo IN ({tipos})")
    if es_sqlite:
        _triggers_sqlite("movimientos_stock", crear=True)


# ------------------------------------------------------------------ upgrade
def upgrade() -> None:
    conexion = op.get_bind()

    op.create_table(
        "sectores",
        sa.Column("id_sector", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=40), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("fecha_baja", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_baja", sa.String(length=250), nullable=True),
        sa.Column("baja_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["baja_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id_sector"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "apoderados",
        sa.Column("id_apoderado", sa.Integer(), nullable=False),
        sa.Column("id_paciente", sa.Integer(), nullable=False),
        sa.Column("rut_hmac", sa.String(length=64), nullable=False),
        sa.Column("rut_enmascarado", sa.String(length=16), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("parentesco", sa.String(length=30), nullable=False),
        sa.Column("telefono", sa.String(length=20), nullable=True),
        sa.Column("vigente_hasta", sa.Date(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("fecha_baja", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_baja", sa.String(length=250), nullable=True),
        sa.Column("baja_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["baja_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["id_paciente"], ["pacientes.id_paciente"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id_apoderado"),
        sa.UniqueConstraint("id_paciente", "rut_hmac", name="uq_apoderados_paciente_rut"),
    )
    op.create_table(
        "despachos_domicilio",
        sa.Column("id_despacho", sa.Integer(), nullable=False),
        sa.Column("id_dispensacion", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=12), nullable=False),
        sa.Column("id_responsable", sa.Integer(), nullable=True),
        sa.Column("fecha_salida", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_entrega", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recibe_nombre", sa.String(length=120), nullable=True),
        sa.Column("observacion", sa.String(length=250), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.CheckConstraint("estado IN ('PREPARANDO','EN_RUTA','ENTREGADO','FALLIDO')", name="ck_despachos_estado"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["id_dispensacion"], ["dispensaciones.id_dispensacion"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["id_responsable"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id_despacho"),
        sa.UniqueConstraint("id_dispensacion"),
    )
    op.create_index("ix_despachos_domicilio_estado", "despachos_domicilio", ["estado"])

    # 1) Columnas nuevas, primero admitiendo nulos para poder completar los datos existentes.
    with op.batch_alter_table("pacientes") as batch:
        batch.add_column(sa.Column("id_sector", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("es_prais", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("es_postrado", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("alergias", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("direccion", sa.String(length=200), nullable=True))
    with op.batch_alter_table("medicamentos") as batch:
        batch.add_column(sa.Column("principio_activo", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("concentracion", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("forma_farmaceutica", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("unidad_dispensacion", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("es_ges", sa.Boolean(), server_default=sa.false(), nullable=False))
    with op.batch_alter_table("recetas") as batch:
        batch.add_column(sa.Column("tipo_receta", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("total_entregas", sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column("entregas_realizadas", sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column("intervalo_dias", sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column("proxima_fecha_retiro", sa.Date(), nullable=True))
        batch.add_column(sa.Column("id_medico", sa.Integer(), nullable=True))
    with op.batch_alter_table("detalles_receta") as batch:
        batch.add_column(sa.Column("cant_por_entrega", sa.Integer(), nullable=True))
    with op.batch_alter_table("dispensaciones") as batch:
        batch.add_column(sa.Column("numero_entrega", sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column("retira_tipo", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("id_apoderado", sa.Integer(), nullable=True))

    # 2) Migración de datos existentes.
    if conexion.execute(sa.text("SELECT 1 FROM roles WHERE nombre = 'MEDICO'")).first() is None:
        conexion.execute(sa.text("INSERT INTO roles (nombre, descripcion) VALUES ('MEDICO', :d)"),
                         {"d": "Médico: emite recetas"})

    ges = {fila.id_programa: bool(fila.es_ges)
           for fila in conexion.execute(sa.text("SELECT id_programa, es_ges FROM programas_salud"))}
    for fila in conexion.execute(sa.text("SELECT id_medicamento, nombre, id_programa FROM medicamentos")).all():
        activo, concentracion, forma, unidad = separar_nombre(fila.nombre)
        conexion.execute(sa.text(
            "UPDATE medicamentos SET principio_activo = :a, concentracion = :c, forma_farmaceutica = :f, "
            "unidad_dispensacion = :u, es_ges = :g WHERE id_medicamento = :i"),
            {"a": activo, "c": concentracion, "f": forma, "u": unidad,
             "g": ges.get(fila.id_programa, False), "i": fila.id_medicamento})

    conexion.execute(sa.text(
        "UPDATE recetas SET "
        "tipo_receta = CASE WHEN es_retenida THEN 'RETENIDA' ELSE 'AGUDA' END, "
        "total_entregas = 1, intervalo_dias = 30, "
        "entregas_realizadas = CASE WHEN estado = 'DISPENSADA' THEN 1 ELSE 0 END, "
        "proxima_fecha_retiro = CASE WHEN estado IN ('PENDIENTE', 'PARCIAL') THEN fecha_emision ELSE NULL END"))
    conexion.execute(sa.text("UPDATE detalles_receta SET cant_por_entrega = cant_prescrita"))
    conexion.execute(sa.text(
        "UPDATE dispensaciones SET numero_entrega = 1, "
        "retira_tipo = CASE WHEN rut_retira_hmac IS NULL THEN 'PACIENTE' ELSE 'TERCERO' END"))

    # 3) Columnas obligatorias, claves foráneas, restricciones e índices.
    with op.batch_alter_table("pacientes") as batch:
        batch.create_foreign_key("fk_pacientes_sector", "sectores", ["id_sector"], ["id_sector"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_pacientes_tramo", "tramo_fonasa IS NULL OR tramo_fonasa IN ('A','B','C','D')")
    with op.batch_alter_table("medicamentos") as batch:
        for columna in ("principio_activo", "forma_farmaceutica", "unidad_dispensacion"):
            batch.alter_column(columna, existing_type=sa.String(length=120 if columna == "principio_activo" else 30
                                                                     if columna == "forma_farmaceutica" else 20),
                               nullable=False)
        batch.create_index("ix_medicamentos_principio_activo", ["principio_activo"])
    with op.batch_alter_table("recetas") as batch:
        batch.alter_column("tipo_receta", existing_type=sa.String(length=10), nullable=False)
        for columna in ("total_entregas", "entregas_realizadas", "intervalo_dias"):
            batch.alter_column(columna, existing_type=sa.SmallInteger(), nullable=False)
        batch.create_foreign_key("fk_recetas_medico", "usuarios", ["id_medico"], ["id_usuario"], ondelete="RESTRICT")
        batch.create_index("ix_recetas_proxima_fecha_retiro", ["proxima_fecha_retiro"])
        batch.create_check_constraint("ck_recetas_tipo", "tipo_receta IN ('AGUDA','CRONICA','RETENIDA')")
        batch.create_check_constraint("ck_recetas_total_entregas", "total_entregas BETWEEN 1 AND 6")
        batch.create_check_constraint("ck_recetas_una_entrega", "tipo_receta = 'CRONICA' OR total_entregas = 1")
        batch.create_check_constraint("ck_recetas_entregas_realizadas", "entregas_realizadas BETWEEN 0 AND total_entregas")
        batch.create_check_constraint("ck_recetas_intervalo", "intervalo_dias BETWEEN 7 AND 90")
        batch.drop_column("es_retenida")
    with op.batch_alter_table("detalles_receta") as batch:
        batch.alter_column("cant_por_entrega", existing_type=sa.Integer(), nullable=False)
        batch.create_check_constraint("ck_detalles_receta_por_entrega",
                                      "cant_por_entrega > 0 AND cant_por_entrega <= cant_prescrita")
    with op.batch_alter_table("dispensaciones") as batch:
        batch.alter_column("numero_entrega", existing_type=sa.SmallInteger(), nullable=False)
        batch.alter_column("retira_tipo", existing_type=sa.String(length=10), nullable=False)
        batch.create_foreign_key("fk_dispensaciones_apoderado", "apoderados", ["id_apoderado"], ["id_apoderado"],
                                 ondelete="RESTRICT")
        batch.create_check_constraint("ck_dispensaciones_numero_entrega", "numero_entrega BETWEEN 1 AND 6")
        batch.create_check_constraint("ck_dispensaciones_retira_tipo", "retira_tipo IN ('PACIENTE','APODERADO','TERCERO')")
        batch.create_check_constraint("ck_dispensaciones_apoderado",
                                      "(retira_tipo = 'APODERADO' AND id_apoderado IS NOT NULL) OR "
                                      "(retira_tipo <> 'APODERADO' AND id_apoderado IS NULL)")

    _cambiar_tipos_movimiento(TIPOS_MOVIMIENTO_V05)


# ---------------------------------------------------------------- downgrade
def downgrade() -> None:
    conexion = op.get_bind()
    if conexion.execute(sa.text("SELECT 1 FROM movimientos_stock WHERE tipo = 'DEVOLUCION'")).first():
        raise RuntimeError("Hay movimientos DEVOLUCION en el kardex; la versión 0001 no puede representarlos.")
    if conexion.execute(sa.text("SELECT 1 FROM recetas WHERE tipo_receta = 'CRONICA'")).first():
        raise RuntimeError("Hay recetas crónicas; la versión 0001 no puede representarlas.")
    _cambiar_tipos_movimiento(TIPOS_MOVIMIENTO_V04)

    with op.batch_alter_table("recetas") as batch:
        batch.add_column(sa.Column("es_retenida", sa.Boolean(), server_default=sa.false(), nullable=False))
    conexion.execute(sa.text("UPDATE recetas SET es_retenida = (tipo_receta = 'RETENIDA')"))

    with op.batch_alter_table("dispensaciones") as batch:
        for nombre in ("ck_dispensaciones_apoderado", "ck_dispensaciones_retira_tipo", "ck_dispensaciones_numero_entrega"):
            batch.drop_constraint(nombre, type_="check")
        batch.drop_constraint("fk_dispensaciones_apoderado", type_="foreignkey")
        batch.drop_column("id_apoderado")
        batch.drop_column("retira_tipo")
        batch.drop_column("numero_entrega")
    with op.batch_alter_table("detalles_receta") as batch:
        batch.drop_constraint("ck_detalles_receta_por_entrega", type_="check")
        batch.drop_column("cant_por_entrega")
    with op.batch_alter_table("recetas") as batch:
        for nombre in ("ck_recetas_intervalo", "ck_recetas_entregas_realizadas", "ck_recetas_una_entrega",
                       "ck_recetas_total_entregas", "ck_recetas_tipo"):
            batch.drop_constraint(nombre, type_="check")
        batch.drop_index("ix_recetas_proxima_fecha_retiro")
        batch.drop_constraint("fk_recetas_medico", type_="foreignkey")
        for columna in ("id_medico", "proxima_fecha_retiro", "intervalo_dias", "entregas_realizadas",
                        "total_entregas", "tipo_receta"):
            batch.drop_column(columna)
    with op.batch_alter_table("medicamentos") as batch:
        batch.drop_index("ix_medicamentos_principio_activo")
        for columna in ("es_ges", "unidad_dispensacion", "forma_farmaceutica", "concentracion", "principio_activo"):
            batch.drop_column(columna)
    with op.batch_alter_table("pacientes") as batch:
        batch.drop_constraint("ck_pacientes_tramo", type_="check")
        batch.drop_constraint("fk_pacientes_sector", type_="foreignkey")
        for columna in ("direccion", "alergias", "es_postrado", "es_prais", "id_sector"):
            batch.drop_column(columna)

    conexion.execute(sa.text("DELETE FROM roles WHERE nombre = 'MEDICO' AND id_rol NOT IN "
                             "(SELECT id_rol FROM usuarios)"))
    op.drop_index("ix_despachos_domicilio_estado", table_name="despachos_domicilio")
    op.drop_table("despachos_domicilio")
    op.drop_table("apoderados")
    op.drop_table("sectores")
