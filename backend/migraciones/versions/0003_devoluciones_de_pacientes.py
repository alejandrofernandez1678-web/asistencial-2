"""Devoluciones de pacientes

  * Tabla nueva `devoluciones`: lo que un paciente devuelve después de recibirlo,
    con destino REINGRESO (vuelve al lote, movimiento DEVOLUCION del kardex) o
    DESCARTE (no vuelve al stock).
  * El libro de controlados admite asientos de tipo DEVOLUCION.

Revisión: 0003
Anterior: 0002
Fecha: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TIPOS_ASIENTO_V05 = "'SALIDA','RECTIFICACION'"
TIPOS_ASIENTO_V06 = TIPOS_ASIENTO_V05 + ",'DEVOLUCION'"


def _triggers_sqlite(tabla: str, crear: bool) -> None:
    for sufijo, evento in (("sin_update", "UPDATE"), ("sin_delete", "DELETE")):
        if crear:
            op.execute(f"CREATE TRIGGER tg_{tabla}_{sufijo} BEFORE {evento} ON {tabla} "
                       f"BEGIN SELECT RAISE(ABORT, '{tabla} es de solo insercion'); END;")
        else:
            op.execute(f"DROP TRIGGER IF EXISTS tg_{tabla}_{sufijo}")


def _cambiar_tipos_asiento(tipos: str) -> None:
    """El libro es de solo inserción: en SQLite la tabla se reconstruye, así que
    los triggers se quitan antes y se vuelven a crear después."""
    es_sqlite = op.get_bind().dialect.name == "sqlite"
    if es_sqlite:
        _triggers_sqlite("asientos_controlados", crear=False)
    with op.batch_alter_table("asientos_controlados") as batch:
        batch.drop_constraint("ck_asientos_tipo", type_="check")
        batch.create_check_constraint("ck_asientos_tipo", f"tipo IN ({tipos})")
    if es_sqlite:
        _triggers_sqlite("asientos_controlados", crear=True)


def upgrade() -> None:
    op.create_table(
        "devoluciones",
        sa.Column("id_devolucion", sa.Integer(), nullable=False),
        sa.Column("id_detalle_disp", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("destino", sa.String(length=10), nullable=False),
        sa.Column("motivo", sa.String(length=250), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.CheckConstraint("destino IN ('REINGRESO','DESCARTE')", name="ck_devoluciones_destino"),
        sa.CheckConstraint("cantidad > 0", name="ck_devoluciones_cantidad"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["id_detalle_disp"], ["detalles_dispensacion.id_detalle_disp"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id_usuario"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id_devolucion"),
    )
    op.create_index("ix_devoluciones_id_detalle_disp", "devoluciones", ["id_detalle_disp"])
    _cambiar_tipos_asiento(TIPOS_ASIENTO_V06)


def downgrade() -> None:
    conexion = op.get_bind()
    if conexion.execute(sa.text("SELECT 1 FROM asientos_controlados WHERE tipo = 'DEVOLUCION'")).first():
        raise RuntimeError("El libro tiene asientos DEVOLUCION; la versión 0002 no puede representarlos.")
    if conexion.execute(sa.text("SELECT 1 FROM devoluciones")).first():
        raise RuntimeError("Hay devoluciones registradas; la versión 0002 no puede representarlas.")
    _cambiar_tipos_asiento(TIPOS_ASIENTO_V05)
    op.drop_index("ix_devoluciones_id_detalle_disp", table_name="devoluciones")
    op.drop_table("devoluciones")
