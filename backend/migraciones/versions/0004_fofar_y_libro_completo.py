"""FOFAR y libro de controlados completo (v0.6)

  * Libro (D.S. 404/405 art. 18): asientos INGRESO, MERMA y AJUSTE ligados a un lote
    (id_lote); id_detalle_disp pasa a ser opcional. La receta guarda prescriptor, domicilio
    del paciente y N.º de receta cheque; el medicamento indica si exige receta cheque.
  * Lotes: proveedor, documento de recepción y costo (inventario valorizado).
  * Kardex: movimientos PRESTAMO_SALIDA y PRESTAMO_ENTRADA.
  * Tablas nuevas: solicitudes_despacho, faltantes, reclamos (indicadores FOFAR 1 y 2),
    tomas_inventario y conteos_inventario (indicador 3), actividades_farmaceuticas y
    programacion_actividades (indicador 4) y prestamos (Anexo 1 FOFAR).

Revisión: 0004
Anterior: 0003
Fecha: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TIPOS_ASIENTO_V05 = "'SALIDA','RECTIFICACION','DEVOLUCION'"
TIPOS_ASIENTO_V06 = TIPOS_ASIENTO_V05 + ",'INGRESO','MERMA','AJUSTE'"
ORIGEN_ASIENTO = ("(tipo IN ('SALIDA','RECTIFICACION','DEVOLUCION') AND id_detalle_disp IS NOT NULL) OR "
                  "(tipo IN ('INGRESO','MERMA','AJUSTE') AND id_lote IS NOT NULL)")
TIPOS_MOVIMIENTO_V05 = ("'INGRESO','DISPENSACION','ANULACION_DISPENSACION','MERMA','AJUSTE','ANULACION_LOTE',"
                        "'DEVOLUCION'")
TIPOS_MOVIMIENTO_V06 = TIPOS_MOVIMIENTO_V05 + ",'PRESTAMO_SALIDA','PRESTAMO_ENTRADA'"
TABLAS_NUEVAS = ("reclamos", "faltantes", "solicitudes_despacho", "conteos_inventario", "tomas_inventario",
                 "actividades_farmaceuticas", "programacion_actividades", "prestamos")


def _triggers_sqlite(tabla: str, crear: bool) -> None:
    for sufijo, evento in (("sin_update", "UPDATE"), ("sin_delete", "DELETE")):
        if crear:
            op.execute(f"CREATE TRIGGER tg_{tabla}_{sufijo} BEFORE {evento} ON {tabla} "
                       f"BEGIN SELECT RAISE(ABORT, '{tabla} es de solo insercion'); END;")
        else:
            op.execute(f"DROP TRIGGER IF EXISTS tg_{tabla}_{sufijo}")


class _SinTriggers:
    """Las tablas de solo inserción se reconstruyen en SQLite: se quitan los triggers y se reponen."""

    def __init__(self, tabla: str):
        self.tabla = tabla
        self.es_sqlite = op.get_bind().dialect.name == "sqlite"

    def __enter__(self):
        if self.es_sqlite:
            _triggers_sqlite(self.tabla, crear=False)

    def __exit__(self, *_):
        if self.es_sqlite:
            _triggers_sqlite(self.tabla, crear=True)


def _crear_tablas_nuevas() -> None:
    op.create_table('programacion_actividades',
    sa.Column('anio', sa.SmallInteger(), autoincrement=False, nullable=False),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint('cantidad > 0', name='ck_programacion_cantidad'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('anio')
    )
    op.create_table('tomas_inventario',
    sa.Column('id_toma', sa.Integer(), nullable=False),
    sa.Column('id_ubicacion', sa.Integer(), nullable=True),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('fecha_apertura', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fecha_cierre', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cerrada_por', sa.Integer(), nullable=True),
    sa.Column('observacion', sa.String(length=250), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint("estado IN ('ABIERTA','CERRADA')", name='ck_tomas_estado'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['cerrada_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_ubicacion'], ['ubicaciones.id_ubicacion'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id_toma')
    )
    with op.batch_alter_table('tomas_inventario', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tomas_inventario_estado'), ['estado'], unique=False)

    op.create_table('prestamos',
    sa.Column('id_prestamo', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('establecimiento', sa.String(length=120), nullable=False),
    sa.Column('id_medicamento', sa.Integer(), nullable=False),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('fecha_compromiso', sa.Date(), nullable=False),
    sa.Column('documento', sa.String(length=30), nullable=True),
    sa.Column('observacion', sa.String(length=250), nullable=True),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('fecha_devolucion', sa.Date(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint("estado IN ('PENDIENTE','DEVUELTO')", name='ck_prestamos_estado'),
    sa.CheckConstraint("tipo IN ('OTORGADO','RECIBIDO')", name='ck_prestamos_tipo'),
    sa.CheckConstraint('cantidad > 0', name='ck_prestamos_cantidad'),
    sa.CheckConstraint('fecha_compromiso >= fecha', name='ck_prestamos_compromiso'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_medicamento'], ['medicamentos.id_medicamento'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id_prestamo')
    )
    with op.batch_alter_table('prestamos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_prestamos_estado'), ['estado'], unique=False)

    op.create_table('actividades_farmaceuticas',
    sa.Column('id_actividad', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=24), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('id_paciente', sa.Integer(), nullable=True),
    sa.Column('id_medicamento', sa.Integer(), nullable=True),
    sa.Column('id_lote', sa.Integer(), nullable=True),
    sa.Column('descripcion', sa.String(length=1000), nullable=False),
    sa.Column('resultado', sa.String(length=500), nullable=True),
    sa.Column('participantes', sa.Integer(), nullable=True),
    sa.Column('gravedad', sa.String(length=10), nullable=True),
    sa.Column('fecha_notificacion', sa.Date(), nullable=True),
    sa.Column('folio_isp', sa.String(length=30), nullable=True),
    sa.Column('id_usuario', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('fecha_anulacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('anulada_por', sa.Integer(), nullable=True),
    sa.Column('motivo_anulacion', sa.String(length=250), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint("estado IN ('VIGENTE','ANULADA')", name='ck_actividades_estado'),
    sa.CheckConstraint("gravedad IS NULL OR gravedad IN ('LEVE','MODERADA','GRAVE')", name='ck_actividades_gravedad'),
    sa.CheckConstraint("tipo IN ('REVISION_MEDICACION','CONCILIACION','EDUCACION','SEGUIMIENTO_FT','RAM','FALLA_CALIDAD','EVENTO_ADVERSO','TALLER')", name='ck_actividades_tipo'),
    sa.CheckConstraint('participantes IS NULL OR participantes > 0', name='ck_actividades_participantes'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['anulada_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_lote'], ['lotes.id_lote'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_medicamento'], ['medicamentos.id_medicamento'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_paciente'], ['pacientes.id_paciente'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_usuario'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id_actividad')
    )
    with op.batch_alter_table('actividades_farmaceuticas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_actividades_farmaceuticas_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_actividades_farmaceuticas_tipo'), ['tipo'], unique=False)

    op.create_table('conteos_inventario',
    sa.Column('id_conteo', sa.Integer(), nullable=False),
    sa.Column('id_toma', sa.Integer(), nullable=False),
    sa.Column('id_lote', sa.Integer(), nullable=False),
    sa.Column('cantidad_contada', sa.Integer(), nullable=True),
    sa.Column('stock_al_contar', sa.Integer(), nullable=True),
    sa.Column('contado_por', sa.Integer(), nullable=True),
    sa.Column('fecha_conteo', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ajuste_aplicado', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint('cantidad_contada IS NULL OR cantidad_contada >= 0', name='ck_conteos_cantidad'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['contado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_lote'], ['lotes.id_lote'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_toma'], ['tomas_inventario.id_toma'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id_conteo'),
    sa.UniqueConstraint('id_toma', 'id_lote', name='uq_conteos_toma_lote')
    )
    op.create_table('solicitudes_despacho',
    sa.Column('id_solicitud', sa.Integer(), nullable=False),
    sa.Column('id_receta', sa.Integer(), nullable=False),
    sa.Column('id_dispensacion', sa.Integer(), nullable=True),
    sa.Column('numero_entrega', sa.SmallInteger(), nullable=False),
    sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id_usuario', sa.Integer(), nullable=False),
    sa.Column('resultado', sa.String(length=10), nullable=False),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('detalle', sa.JSON(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint("estado IN ('VIGENTE','ANULADA')", name='ck_solicitudes_estado'),
    sa.CheckConstraint("resultado IN ('COMPLETA','SIN_STOCK','RECHAZO')", name='ck_solicitudes_resultado'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_dispensacion'], ['dispensaciones.id_dispensacion'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_receta'], ['recetas.id_receta'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_usuario'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id_solicitud'),
    sa.UniqueConstraint('id_dispensacion')
    )
    with op.batch_alter_table('solicitudes_despacho', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_solicitudes_despacho_fecha_hora'), ['fecha_hora'], unique=False)
        batch_op.create_index(batch_op.f('ix_solicitudes_despacho_id_receta'), ['id_receta'], unique=False)

    op.create_table('faltantes',
    sa.Column('id_faltante', sa.Integer(), nullable=False),
    sa.Column('id_solicitud', sa.Integer(), nullable=False),
    sa.Column('id_detalle_receta', sa.Integer(), nullable=False),
    sa.Column('numero_entrega', sa.SmallInteger(), nullable=False),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('motivo', sa.String(length=16), nullable=False),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
    sa.Column('plazo', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fecha_solucion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id_dispensacion_solucion', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint("(motivo = 'SIN_STOCK' AND plazo IS NOT NULL) OR (motivo = 'RECHAZO_PACIENTE' AND plazo IS NULL)", name='ck_faltantes_plazo'),
    sa.CheckConstraint("estado IN ('PENDIENTE','ENTREGADO','RECHAZO','ANULADO')", name='ck_faltantes_estado'),
    sa.CheckConstraint("motivo IN ('SIN_STOCK','RECHAZO_PACIENTE')", name='ck_faltantes_motivo'),
    sa.CheckConstraint('cantidad > 0', name='ck_faltantes_cantidad'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_detalle_receta'], ['detalles_receta.id_detalle_receta'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_dispensacion_solucion'], ['dispensaciones.id_dispensacion'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_solicitud'], ['solicitudes_despacho.id_solicitud'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id_faltante')
    )
    with op.batch_alter_table('faltantes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faltantes_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_faltantes_id_detalle_receta'), ['id_detalle_receta'], unique=False)
        batch_op.create_index(batch_op.f('ix_faltantes_id_solicitud'), ['id_solicitud'], unique=False)

    op.create_table('reclamos',
    sa.Column('id_reclamo', sa.Integer(), nullable=False),
    sa.Column('id_paciente', sa.Integer(), nullable=False),
    sa.Column('id_faltante', sa.Integer(), nullable=True),
    sa.Column('canal', sa.String(length=16), nullable=False),
    sa.Column('folio_externo', sa.String(length=30), nullable=True),
    sa.Column('descripcion', sa.String(length=500), nullable=False),
    sa.Column('fecha_reclamo', sa.DateTime(timezone=True), nullable=False),
    sa.Column('plazo', sa.DateTime(timezone=True), nullable=False),
    sa.Column('estado', sa.String(length=12), nullable=False),
    sa.Column('fecha_solucion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('solucion', sa.String(length=250), nullable=True),
    sa.Column('recibe_nombre', sa.String(length=120), nullable=True),
    sa.Column('resuelto_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.CheckConstraint("canal IN ('OIRS','SALUD_RESPONDE','PRESENCIAL')", name='ck_reclamos_canal'),
    sa.CheckConstraint("estado IN ('ABIERTO','RESUELTO','NO_ATINGENTE')", name='ck_reclamos_estado'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_faltante'], ['faltantes.id_faltante'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_paciente'], ['pacientes.id_paciente'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['resuelto_por'], ['usuarios.id_usuario'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id_reclamo')
    )
    with op.batch_alter_table('reclamos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reclamos_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_reclamos_fecha_reclamo'), ['fecha_reclamo'], unique=False)
        batch_op.create_index(batch_op.f('ix_reclamos_id_paciente'), ['id_paciente'], unique=False)


def upgrade() -> None:
    _crear_tablas_nuevas()
    with _SinTriggers("asientos_controlados"), op.batch_alter_table("asientos_controlados") as batch:
        batch.add_column(sa.Column("id_lote", sa.Integer(), nullable=True))
        batch.alter_column("id_detalle_disp", existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key("fk_asientos_lote", "lotes", ["id_lote"], ["id_lote"], ondelete="RESTRICT")
        batch.drop_constraint("ck_asientos_tipo", type_="check")
        batch.create_check_constraint("ck_asientos_tipo", f"tipo IN ({TIPOS_ASIENTO_V06})")
        batch.create_check_constraint("ck_asientos_origen", ORIGEN_ASIENTO)
    with _SinTriggers("movimientos_stock"), op.batch_alter_table("movimientos_stock") as batch:
        batch.drop_constraint("ck_movimientos_tipo", type_="check")
        batch.create_check_constraint("ck_movimientos_tipo", f"tipo IN ({TIPOS_MOVIMIENTO_V06})")

    with op.batch_alter_table("lotes") as batch:
        batch.add_column(sa.Column("proveedor", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("tipo_documento", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("numero_documento", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("fecha_documento", sa.Date(), nullable=True))
        batch.add_column(sa.Column("costo_total", sa.Integer(), nullable=True))
        batch.create_check_constraint("ck_lotes_costo", "costo_total IS NULL OR costo_total >= 0")
        batch.create_check_constraint("ck_lotes_tipo_documento", "tipo_documento IS NULL OR tipo_documento IN "
                                      "('FACTURA','GUIA','PRESTAMO','DONACION')")
    with op.batch_alter_table("medicamentos") as batch:
        batch.add_column(sa.Column("requiere_receta_cheque", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.create_check_constraint("ck_medicamentos_receta_cheque", "NOT requiere_receta_cheque OR es_controlado")
    with op.batch_alter_table("recetas") as batch:
        batch.add_column(sa.Column("prescriptor_nombre", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("prescriptor_rut", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("domicilio_paciente", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("numero_receta_cheque", sa.String(length=20), nullable=True))


def downgrade() -> None:
    conexion = op.get_bind()
    if conexion.execute(sa.text("SELECT 1 FROM asientos_controlados WHERE tipo IN ('INGRESO','MERMA','AJUSTE')")).first():
        raise RuntimeError("El libro tiene asientos de ingreso, merma o ajuste; la versión 0003 no puede representarlos.")
    if conexion.execute(sa.text("SELECT 1 FROM movimientos_stock WHERE tipo LIKE 'PRESTAMO%'")).first():
        raise RuntimeError("El kardex tiene movimientos de préstamo; la versión 0003 no puede representarlos.")
    for tabla in ("solicitudes_despacho", "reclamos", "tomas_inventario", "actividades_farmaceuticas", "prestamos"):
        if conexion.execute(sa.text(f"SELECT 1 FROM {tabla}")).first():
            raise RuntimeError(f"La tabla {tabla} tiene datos; la versión 0003 no puede representarlos.")

    with op.batch_alter_table("recetas") as batch:
        for columna in ("numero_receta_cheque", "domicilio_paciente", "prescriptor_rut", "prescriptor_nombre"):
            batch.drop_column(columna)
    with op.batch_alter_table("medicamentos") as batch:
        batch.drop_constraint("ck_medicamentos_receta_cheque", type_="check")
        batch.drop_column("requiere_receta_cheque")
    with op.batch_alter_table("lotes") as batch:
        batch.drop_constraint("ck_lotes_tipo_documento", type_="check")
        batch.drop_constraint("ck_lotes_costo", type_="check")
        for columna in ("costo_total", "fecha_documento", "numero_documento", "tipo_documento", "proveedor"):
            batch.drop_column(columna)
    with _SinTriggers("movimientos_stock"), op.batch_alter_table("movimientos_stock") as batch:
        batch.drop_constraint("ck_movimientos_tipo", type_="check")
        batch.create_check_constraint("ck_movimientos_tipo", f"tipo IN ({TIPOS_MOVIMIENTO_V05})")
    with _SinTriggers("asientos_controlados"), op.batch_alter_table("asientos_controlados") as batch:
        batch.drop_constraint("ck_asientos_origen", type_="check")
        batch.drop_constraint("ck_asientos_tipo", type_="check")
        batch.create_check_constraint("ck_asientos_tipo", f"tipo IN ({TIPOS_ASIENTO_V05})")
        batch.drop_constraint("fk_asientos_lote", type_="foreignkey")
        batch.alter_column("id_detalle_disp", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("id_lote")
    for tabla in TABLAS_NUEVAS:
        op.drop_table(tabla)
