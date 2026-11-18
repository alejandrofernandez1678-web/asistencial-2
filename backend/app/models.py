"""Modelo de datos (ORM) - versión corregida según la retroalimentación del MER.

Cambios respecto del MER del Informe 2:
  * Campos de control en todas las tablas de negocio: creado_en, creado_por,
    actualizado_en, actualizado_por (CamposControl).
  * Baja lógica de catálogos (medicamentos, ubicaciones, usuarios): activo,
    fecha_baja, baja_por, motivo_baja (BajaLogica). Nunca se borra una fila.
  * Anulación de dispensaciones (equivalente a la "venta" en un CESFAM):
    estado VIGENTE/ANULADA + quién, cuándo y por qué. El stock se repone.
  * Anulación de lotes mal ingresados: estado ANULADO + motivo, y ajustes
    de cantidad registrados como movimientos.
  * Nueva tabla movimientos_stock (kardex, solo inserción): toda entrada,
    salida, merma, ajuste o anulación queda registrada con su saldo.
  * asientos_controlados admite asientos de RECTIFICACION que referencian
    al asiento original, porque el libro es inmutable.
"""

from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, DDL, ForeignKey, Index,
                        Integer, SmallInteger, String, UniqueConstraint, event, false, text)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from .db import Base
from .reloj import ahora


class CamposControl:
    """Auditoría mínima de cada fila: quién y cuándo la creó y la modificó."""

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, nullable=False)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=ahora)

    @declared_attr
    def creado_por(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))

    @declared_attr
    def actualizado_por(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))


class BajaLogica:
    """Dar de baja = desactivar con motivo; la fila y su historia se conservan."""

    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_baja: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_baja: Mapped[str | None] = mapped_column(String(250))

    @declared_attr
    def baja_por(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))


# --------------------------------------------------------------- seguridad
class Roles(Base):
    __tablename__ = "roles"
    id_rol: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(30), unique=True)
    descripcion: Mapped[str] = mapped_column(String(150), default="")


class Usuarios(CamposControl, BajaLogica, Base):
    __tablename__ = "usuarios"
    id_usuario: Mapped[int] = mapped_column(primary_key=True)
    rut: Mapped[str] = mapped_column(String(12), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    pin_hash: Mapped[str | None] = mapped_column(String(200))  # firma del Q.F. para controlados
    id_rol: Mapped[int] = mapped_column(ForeignKey("roles.id_rol", ondelete="RESTRICT"))
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rol: Mapped[Roles] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL


# --------------------------------------------------------------- pacientes
class Sectores(CamposControl, BajaLogica, Base):
    """Sector territorial del CESFAM (p. ej. Sector Verde, Azul, Rural)."""
    __tablename__ = "sectores"
    id_sector: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(40), unique=True)


class ProgramasSalud(CamposControl, Base):
    __tablename__ = "programas_salud"
    id_programa: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    es_ges: Mapped[bool] = mapped_column(Boolean, default=False)


class Pacientes(CamposControl, Base):
    __tablename__ = "pacientes"
    id_paciente: Mapped[int] = mapped_column(primary_key=True)
    rut_hmac: Mapped[str] = mapped_column(String(64), unique=True)   # búsqueda sin guardar el RUT en claro
    rut_enmascarado: Mapped[str] = mapped_column(String(16))
    nombre: Mapped[str] = mapped_column(String(120))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    tramo_fonasa: Mapped[str | None] = mapped_column(String(1))
    id_sector: Mapped[int | None] = mapped_column(ForeignKey("sectores.id_sector", ondelete="RESTRICT"))
    es_prais: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # PRAIS se suma a FONASA
    es_postrado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    alergias: Mapped[str | None] = mapped_column(String(500))
    direccion: Mapped[str | None] = mapped_column(String(200))  # solo para despacho a domicilio

    programas: Mapped[list[ProgramasSalud]] = relationship(secondary="pacientes_programas")
    sector: Mapped[Sectores | None] = relationship()
    __table_args__ = (
        CheckConstraint("tramo_fonasa IS NULL OR tramo_fonasa IN ('A','B','C','D')", name="ck_pacientes_tramo"),
    )


class Apoderados(CamposControl, BajaLogica, Base):
    """Tercero autorizado a retirar medicamentos en nombre del paciente."""
    __tablename__ = "apoderados"
    id_apoderado: Mapped[int] = mapped_column(primary_key=True)
    id_paciente: Mapped[int] = mapped_column(ForeignKey("pacientes.id_paciente", ondelete="RESTRICT"))
    rut_hmac: Mapped[str] = mapped_column(String(64))
    rut_enmascarado: Mapped[str] = mapped_column(String(16))
    nombre: Mapped[str] = mapped_column(String(120))
    parentesco: Mapped[str] = mapped_column(String(30))
    telefono: Mapped[str | None] = mapped_column(String(20))
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (UniqueConstraint("id_paciente", "rut_hmac", name="uq_apoderados_paciente_rut"),)


class PacientesProgramas(Base):
    __tablename__ = "pacientes_programas"
    id_paciente: Mapped[int] = mapped_column(ForeignKey("pacientes.id_paciente", ondelete="RESTRICT"),
                                             primary_key=True)
    id_programa: Mapped[int] = mapped_column(ForeignKey("programas_salud.id_programa", ondelete="RESTRICT"),
                                             primary_key=True)
    fecha_ingreso: Mapped[date] = mapped_column(Date)


# -------------------------------------------------------------- inventario
class Medicamentos(CamposControl, BajaLogica, Base):
    __tablename__ = "medicamentos"
    id_medicamento: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    codigo_barras: Mapped[str | None] = mapped_column(String(13), unique=True)  # EAN-13 (fabricante o interno 200...)
    nombre: Mapped[str] = mapped_column(String(120))
    principio_activo: Mapped[str] = mapped_column(String(120), index=True)
    concentracion: Mapped[str | None] = mapped_column(String(40))          # "50 mg", "100 UI/ml"
    forma_farmaceutica: Mapped[str] = mapped_column(String(30))            # ver domain/catalogo.FORMAS
    unidad_dispensacion: Mapped[str] = mapped_column(String(20))           # unidad mínima que se descuenta
    es_ges: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    unidades_envase: Mapped[int] = mapped_column(Integer)
    es_controlado: Mapped[bool] = mapped_column(Boolean, default=False)
    tipo_control: Mapped[str | None] = mapped_column(String(20))  # PSICOTROPICO / ESTUPEFACIENTE
    # Estupefacientes y psicotrópicos de las listas II y III (D.S. 404/405): exigen receta cheque.
    requiere_receta_cheque: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    umbral_critico: Mapped[int] = mapped_column(Integer, default=0)
    id_programa: Mapped[int | None] = mapped_column(ForeignKey("programas_salud.id_programa", ondelete="RESTRICT"))

    programa: Mapped[ProgramasSalud | None] = relationship()
    __table_args__ = (
        CheckConstraint("unidades_envase > 0", name="ck_medicamentos_unidades_envase"),
        CheckConstraint("umbral_critico >= 0", name="ck_medicamentos_umbral"),
        CheckConstraint("NOT requiere_receta_cheque OR es_controlado", name="ck_medicamentos_receta_cheque"),
    )


class Ubicaciones(CamposControl, BajaLogica, Base):
    __tablename__ = "ubicaciones"
    id_ubicacion: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    tipo: Mapped[str] = mapped_column(String(30))  # CASILLERO / ESTANTE / CAJA_SEGURIDAD


class Lotes(CamposControl, Base):
    __tablename__ = "lotes"
    id_lote: Mapped[int] = mapped_column(primary_key=True)
    id_medicamento: Mapped[int] = mapped_column(ForeignKey("medicamentos.id_medicamento", ondelete="RESTRICT"))
    codigo_lote: Mapped[str] = mapped_column(String(40))
    fecha_vencimiento: Mapped[date] = mapped_column(Date)
    unidades_ingresadas: Mapped[int] = mapped_column(Integer)
    unidades_disp: Mapped[int] = mapped_column(Integer)
    id_ubicacion: Mapped[int] = mapped_column(ForeignKey("ubicaciones.id_ubicacion", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(20), default="DISPONIBLE")
    fecha_anulacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    motivo_anulacion: Mapped[str | None] = mapped_column(String(250))
    # Documento de recepción (D.S. 404/405 art. 18 en controlados) y costo para valorizar el inventario (FOFAR)
    proveedor: Mapped[str | None] = mapped_column(String(120))
    tipo_documento: Mapped[str | None] = mapped_column(String(10))   # FACTURA / GUIA / PRESTAMO / DONACION
    numero_documento: Mapped[str | None] = mapped_column(String(30))
    fecha_documento: Mapped[date | None] = mapped_column(Date)
    costo_total: Mapped[int | None] = mapped_column(Integer)          # pesos (neto) de las unidades ingresadas

    medicamento: Mapped[Medicamentos] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL
    ubicacion: Mapped[Ubicaciones] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL
    __table_args__ = (
        UniqueConstraint("id_medicamento", "codigo_lote", name="uq_lotes_medicamento_codigo"),
        CheckConstraint("unidades_disp >= 0", name="ck_lotes_unidades_no_negativas"),
        CheckConstraint("unidades_ingresadas > 0", name="ck_lotes_unidades_ingresadas"),
        CheckConstraint("estado IN ('DISPONIBLE','ALERTA_SANITARIA','MERMA','ANULADO')", name="ck_lotes_estado"),
        CheckConstraint("costo_total IS NULL OR costo_total >= 0", name="ck_lotes_costo"),
        CheckConstraint("tipo_documento IS NULL OR tipo_documento IN ('FACTURA','GUIA','PRESTAMO','DONACION')",
                        name="ck_lotes_tipo_documento"),
        Index("ix_lotes_fefo", "id_medicamento", "fecha_vencimiento",
              postgresql_where=text("unidades_disp > 0"), sqlite_where=text("unidades_disp > 0")),
    )


class MovimientosStock(Base):
    """Kardex: una fila por cada cambio de stock. Solo inserción (trigger)."""
    __tablename__ = "movimientos_stock"
    id_movimiento: Mapped[int] = mapped_column(primary_key=True)
    id_lote: Mapped[int] = mapped_column(ForeignKey("lotes.id_lote", ondelete="RESTRICT"))
    tipo: Mapped[str] = mapped_column(String(30))
    cantidad: Mapped[int] = mapped_column(Integer)          # positiva = entrada, negativa = salida
    saldo_resultante: Mapped[int] = mapped_column(Integer)
    referencia_tipo: Mapped[str | None] = mapped_column(String(30))
    referencia_id: Mapped[int | None] = mapped_column(Integer)
    motivo: Mapped[str | None] = mapped_column(String(250))
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    __table_args__ = (
        CheckConstraint("tipo IN ('INGRESO','DISPENSACION','ANULACION_DISPENSACION','MERMA',"
                        "'AJUSTE','ANULACION_LOTE','DEVOLUCION','PRESTAMO_SALIDA','PRESTAMO_ENTRADA')",
                        name="ck_movimientos_tipo"),
        CheckConstraint("cantidad <> 0", name="ck_movimientos_cantidad"),
        CheckConstraint("saldo_resultante >= 0", name="ck_movimientos_saldo"),
        Index("ix_movimientos_lote_fecha", "id_lote", "fecha_hora"),
    )


class Mermas(CamposControl, Base):
    __tablename__ = "mermas"
    id_merma: Mapped[int] = mapped_column(primary_key=True)
    id_lote: Mapped[int] = mapped_column(ForeignKey("lotes.id_lote", ondelete="RESTRICT"))
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    cantidad: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(30))  # VENCIMIENTO / DANO / ALERTA_SANITARIA
    observacion: Mapped[str | None] = mapped_column(String(250))
    estado_devolucion: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_mermas_cantidad"),)


# --------------------------------------------------------------- recetas
class Recetas(CamposControl, Base):
    __tablename__ = "recetas"
    id_receta: Mapped[int] = mapped_column(primary_key=True)
    folio: Mapped[str] = mapped_column(String(30), unique=True)
    id_paciente: Mapped[int] = mapped_column(ForeignKey("pacientes.id_paciente", ondelete="RESTRICT"))
    fecha_emision: Mapped[date] = mapped_column(Date)
    tipo_receta: Mapped[str] = mapped_column(String(10), default="AGUDA")   # AGUDA / CRONICA / RETENIDA
    total_entregas: Mapped[int] = mapped_column(SmallInteger, default=1)
    entregas_realizadas: Mapped[int] = mapped_column(SmallInteger, default=0)
    intervalo_dias: Mapped[int] = mapped_column(SmallInteger, default=30)
    proxima_fecha_retiro: Mapped[date | None] = mapped_column(Date, index=True)
    id_medico: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    # Datos que el libro de controlados exige de la receta (D.S. 404/405 art. 18)
    prescriptor_nombre: Mapped[str | None] = mapped_column(String(120))
    prescriptor_rut: Mapped[str | None] = mapped_column(String(12))
    domicilio_paciente: Mapped[str | None] = mapped_column(String(200))
    numero_receta_cheque: Mapped[str | None] = mapped_column(String(20))

    paciente: Mapped[Pacientes] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL
    detalles: Mapped[list["DetallesReceta"]] = relationship(back_populates="receta", order_by="DetallesReceta.id_detalle_receta")
    __table_args__ = (
        CheckConstraint("estado IN ('PENDIENTE','PARCIAL','DISPENSADA','ANULADA')", name="ck_recetas_estado"),
        CheckConstraint("tipo_receta IN ('AGUDA','CRONICA','RETENIDA')", name="ck_recetas_tipo"),
        CheckConstraint("total_entregas BETWEEN 1 AND 6", name="ck_recetas_total_entregas"),
        CheckConstraint("tipo_receta = 'CRONICA' OR total_entregas = 1", name="ck_recetas_una_entrega"),
        CheckConstraint("entregas_realizadas BETWEEN 0 AND total_entregas", name="ck_recetas_entregas_realizadas"),
        CheckConstraint("intervalo_dias BETWEEN 7 AND 90", name="ck_recetas_intervalo"),
    )

    @property
    def es_retenida(self) -> bool:
        """Receta retenida (D.S. 404/405/466): la exige todo medicamento controlado."""
        return self.tipo_receta == "RETENIDA"


class DetallesReceta(CamposControl, Base):
    __tablename__ = "detalles_receta"
    id_detalle_receta: Mapped[int] = mapped_column(primary_key=True)
    id_receta: Mapped[int] = mapped_column(ForeignKey("recetas.id_receta", ondelete="RESTRICT"))
    id_medicamento: Mapped[int] = mapped_column(ForeignKey("medicamentos.id_medicamento", ondelete="RESTRICT"))
    cant_prescrita: Mapped[int] = mapped_column(Integer)       # total = cant_por_entrega × total_entregas
    cant_por_entrega: Mapped[int] = mapped_column(Integer)     # unidades mínimas en cada entrega
    cant_entregada: Mapped[int] = mapped_column(Integer, default=0)
    posologia: Mapped[str] = mapped_column(String(200))

    receta: Mapped[Recetas] = relationship(back_populates="detalles")
    medicamento: Mapped[Medicamentos] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL
    __table_args__ = (
        CheckConstraint("cant_prescrita > 0", name="ck_detalles_receta_prescrita"),
        CheckConstraint("cant_por_entrega > 0 AND cant_por_entrega <= cant_prescrita",
                        name="ck_detalles_receta_por_entrega"),
        CheckConstraint("cant_entregada >= 0 AND cant_entregada <= cant_prescrita",
                        name="ck_detalles_receta_entregada"),
    )


class Dispensaciones(CamposControl, Base):
    __tablename__ = "dispensaciones"
    id_dispensacion: Mapped[int] = mapped_column(primary_key=True)
    id_receta: Mapped[int] = mapped_column(ForeignKey("recetas.id_receta", ondelete="RESTRICT"))
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    id_usuario_autoriza: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    numero_entrega: Mapped[int] = mapped_column(SmallInteger, default=1)      # "Entrega X de Y"
    retira_tipo: Mapped[str] = mapped_column(String(10), default="PACIENTE")  # PACIENTE / APODERADO / TERCERO
    id_apoderado: Mapped[int | None] = mapped_column(ForeignKey("apoderados.id_apoderado", ondelete="RESTRICT"))
    rut_retira_hmac: Mapped[str | None] = mapped_column(String(64))
    rut_retira_enmascarado: Mapped[str | None] = mapped_column(String(16))
    relacion: Mapped[str | None] = mapped_column(String(30))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    clave_idempotencia: Mapped[str] = mapped_column(String(64), unique=True)
    estado: Mapped[str] = mapped_column(String(10), default="VIGENTE")
    fecha_anulacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    motivo_anulacion: Mapped[str | None] = mapped_column(String(250))

    receta: Mapped[Recetas] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL
    detalles: Mapped[list["DetallesDispensacion"]] = relationship(back_populates="dispensacion")
    __table_args__ = (
        CheckConstraint("estado IN ('VIGENTE','ANULADA')", name="ck_dispensaciones_estado"),
        CheckConstraint("numero_entrega BETWEEN 1 AND 6", name="ck_dispensaciones_numero_entrega"),
        CheckConstraint("retira_tipo IN ('PACIENTE','APODERADO','TERCERO')", name="ck_dispensaciones_retira_tipo"),
        CheckConstraint("(retira_tipo = 'APODERADO' AND id_apoderado IS NOT NULL) OR "
                        "(retira_tipo <> 'APODERADO' AND id_apoderado IS NULL)", name="ck_dispensaciones_apoderado"),
    )


class DetallesDispensacion(CamposControl, Base):
    __tablename__ = "detalles_dispensacion"
    id_detalle_disp: Mapped[int] = mapped_column(primary_key=True)
    id_dispensacion: Mapped[int] = mapped_column(ForeignKey("dispensaciones.id_dispensacion", ondelete="RESTRICT"))
    id_detalle_receta: Mapped[int] = mapped_column(ForeignKey("detalles_receta.id_detalle_receta", ondelete="RESTRICT"))
    id_lote: Mapped[int] = mapped_column(ForeignKey("lotes.id_lote", ondelete="RESTRICT"))
    cantidad: Mapped[int] = mapped_column(Integer)

    dispensacion: Mapped[Dispensaciones] = relationship(back_populates="detalles")
    detalle_receta: Mapped[DetallesReceta] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL
    lote: Mapped[Lotes] = relationship(lazy="joined", innerjoin=True)  # FK obligatoria: INNER JOIN permite FOR UPDATE en PostgreSQL
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_detalles_disp_cantidad"),)


class Devoluciones(CamposControl, Base):
    """Medicamento que el paciente devuelve después de recibirlo.

    REINGRESO: el Q.F. lo aprueba y vuelve al mismo lote (movimiento DEVOLUCION en el kardex).
    DESCARTE: no vuelve al stock (envase abierto, mal conservado); solo queda el registro.
    """
    __tablename__ = "devoluciones"
    id_devolucion: Mapped[int] = mapped_column(primary_key=True)
    id_detalle_disp: Mapped[int] = mapped_column(ForeignKey("detalles_dispensacion.id_detalle_disp",
                                                            ondelete="RESTRICT"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    destino: Mapped[str] = mapped_column(String(10))
    motivo: Mapped[str] = mapped_column(String(250))
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    detalle: Mapped[DetallesDispensacion] = relationship(lazy="joined", innerjoin=True)
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_devoluciones_cantidad"),
        CheckConstraint("destino IN ('REINGRESO','DESCARTE')", name="ck_devoluciones_destino"),
    )


class DespachosDomicilio(CamposControl, Base):
    """Entrega a domicilio para pacientes postrados: PREPARANDO -> EN_RUTA -> ENTREGADO (o FALLIDO)."""
    __tablename__ = "despachos_domicilio"
    id_despacho: Mapped[int] = mapped_column(primary_key=True)
    id_dispensacion: Mapped[int] = mapped_column(ForeignKey("dispensaciones.id_dispensacion", ondelete="RESTRICT"),
                                                 unique=True)
    estado: Mapped[str] = mapped_column(String(12), default="PREPARANDO", index=True)
    id_responsable: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    fecha_salida: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fecha_entrega: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recibe_nombre: Mapped[str | None] = mapped_column(String(120))
    observacion: Mapped[str | None] = mapped_column(String(250))

    dispensacion: Mapped[Dispensaciones] = relationship(lazy="joined", innerjoin=True)
    __table_args__ = (
        CheckConstraint("estado IN ('PREPARANDO','EN_RUTA','ENTREGADO','FALLIDO')", name="ck_despachos_estado"),
    )


# ---------------------------------------------------------- controlados
class AsientosControlados(Base):
    """Libro digital de controlados (D.S. 404/405 art. 18). Solo inserción.

    Egresos ligados a una entrega: SALIDA, RECTIFICACION (anulación) y DEVOLUCION.
    Movimientos ligados a un lote: INGRESO (recepción con proveedor y factura),
    MERMA y AJUSTE (corrección, anulación de lote, toma de inventario o arqueo).
    Cada asiento guarda el saldo del producto después del movimiento.
    """
    __tablename__ = "asientos_controlados"
    id_asiento: Mapped[int] = mapped_column(primary_key=True)
    nro_asiento: Mapped[int] = mapped_column(Integer, unique=True)
    tipo: Mapped[str] = mapped_column(String(15), default="SALIDA")
    id_detalle_disp: Mapped[int | None] = mapped_column(ForeignKey("detalles_dispensacion.id_detalle_disp",
                                                                   ondelete="RESTRICT"))
    id_lote: Mapped[int | None] = mapped_column(ForeignKey("lotes.id_lote", ondelete="RESTRICT"))
    id_asiento_origen: Mapped[int | None] = mapped_column(ForeignKey("asientos_controlados.id_asiento",
                                                                     ondelete="RESTRICT"))
    id_usuario_qf: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    contenido: Mapped[dict] = mapped_column(JSON)
    hash_previo: Mapped[str] = mapped_column(String(64))
    hash_actual: Mapped[str] = mapped_column(String(64), unique=True)
    __table_args__ = (
        CheckConstraint("tipo IN ('SALIDA','RECTIFICACION','DEVOLUCION','INGRESO','MERMA','AJUSTE')",
                        name="ck_asientos_tipo"),
        CheckConstraint("(tipo IN ('SALIDA','RECTIFICACION','DEVOLUCION') AND id_detalle_disp IS NOT NULL) OR "
                        "(tipo IN ('INGRESO','MERMA','AJUSTE') AND id_lote IS NOT NULL)", name="ck_asientos_origen"),
        UniqueConstraint("id_detalle_disp", "tipo", name="uq_asientos_detalle_tipo"),
    )


# ------------------------------------------------- FOFAR: oportunidad y reclamos
class SolicitudesDespacho(CamposControl, Base):
    """Cada vez que se pide en ventanilla la entrega de una receta (indicador FOFAR N.º 1).

    resultado: COMPLETA (despacho total y oportuno), SIN_STOCK (faltó algo por quiebre)
    o RECHAZO (el paciente no quiso llevar parte de la entrega). `detalle` guarda, por
    línea, lo que correspondía y lo que se entregó.
    """
    __tablename__ = "solicitudes_despacho"
    id_solicitud: Mapped[int] = mapped_column(primary_key=True)
    id_receta: Mapped[int] = mapped_column(ForeignKey("recetas.id_receta", ondelete="RESTRICT"), index=True)
    id_dispensacion: Mapped[int | None] = mapped_column(ForeignKey("dispensaciones.id_dispensacion",
                                                                   ondelete="RESTRICT"), unique=True)
    numero_entrega: Mapped[int] = mapped_column(SmallInteger)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, index=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    resultado: Mapped[str] = mapped_column(String(10))
    estado: Mapped[str] = mapped_column(String(10), default="VIGENTE")
    detalle: Mapped[list] = mapped_column(JSON, default=list)

    receta: Mapped[Recetas] = relationship(lazy="joined", innerjoin=True)
    __table_args__ = (
        CheckConstraint("resultado IN ('COMPLETA','SIN_STOCK','RECHAZO')", name="ck_solicitudes_resultado"),
        CheckConstraint("estado IN ('VIGENTE','ANULADA')", name="ck_solicitudes_estado"),
    )


class Faltantes(CamposControl, Base):
    """Lo que no se pudo entregar en una solicitud. Si fue por quiebre de stock queda un
    compromiso de entrega con plazo de 24 horas hábiles (FOFAR)."""
    __tablename__ = "faltantes"
    id_faltante: Mapped[int] = mapped_column(primary_key=True)
    id_solicitud: Mapped[int] = mapped_column(ForeignKey("solicitudes_despacho.id_solicitud", ondelete="RESTRICT"),
                                              index=True)
    id_detalle_receta: Mapped[int] = mapped_column(ForeignKey("detalles_receta.id_detalle_receta",
                                                              ondelete="RESTRICT"), index=True)
    numero_entrega: Mapped[int] = mapped_column(SmallInteger)
    cantidad: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(16))
    estado: Mapped[str] = mapped_column(String(10), index=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    plazo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fecha_solucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_dispensacion_solucion: Mapped[int | None] = mapped_column(ForeignKey("dispensaciones.id_dispensacion",
                                                                            ondelete="RESTRICT"))

    solicitud: Mapped[SolicitudesDespacho] = relationship(lazy="joined", innerjoin=True)
    detalle_receta: Mapped[DetallesReceta] = relationship(lazy="joined", innerjoin=True)
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_faltantes_cantidad"),
        CheckConstraint("motivo IN ('SIN_STOCK','RECHAZO_PACIENTE')", name="ck_faltantes_motivo"),
        CheckConstraint("estado IN ('PENDIENTE','ENTREGADO','RECHAZO','ANULADO')", name="ck_faltantes_estado"),
        CheckConstraint("(motivo = 'SIN_STOCK' AND plazo IS NOT NULL) OR (motivo = 'RECHAZO_PACIENTE' AND plazo IS NULL)",
                        name="ck_faltantes_plazo"),
    )


class Reclamos(CamposControl, Base):
    """Reclamo del usuario por no entrega de medicamentos (Ley 20.584 / FOFAR indicador N.º 2):
    se resuelve entregando el fármaco dentro de 24 horas hábiles, con acta de recepción."""
    __tablename__ = "reclamos"
    id_reclamo: Mapped[int] = mapped_column(primary_key=True)
    id_paciente: Mapped[int] = mapped_column(ForeignKey("pacientes.id_paciente", ondelete="RESTRICT"), index=True)
    id_faltante: Mapped[int | None] = mapped_column(ForeignKey("faltantes.id_faltante", ondelete="RESTRICT"))
    canal: Mapped[str] = mapped_column(String(16))
    folio_externo: Mapped[str | None] = mapped_column(String(30))
    descripcion: Mapped[str] = mapped_column(String(500))
    fecha_reclamo: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, index=True)
    plazo: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(12), default="ABIERTO", index=True)
    fecha_solucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solucion: Mapped[str | None] = mapped_column(String(250))
    recibe_nombre: Mapped[str | None] = mapped_column(String(120))
    resuelto_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))

    paciente: Mapped[Pacientes] = relationship(lazy="joined", innerjoin=True)
    faltante: Mapped[Faltantes | None] = relationship()
    __table_args__ = (
        CheckConstraint("canal IN ('OIRS','SALUD_RESPONDE','PRESENCIAL')", name="ck_reclamos_canal"),
        CheckConstraint("estado IN ('ABIERTO','RESUELTO','NO_ATINGENTE')", name="ck_reclamos_estado"),
    )


# ------------------------------------------------- FOFAR: inventario valorizado
class TomasInventario(CamposControl, Base):
    """Toma de inventario físico (total o de una ubicación). Se cuenta a ciegas y el Q.F.
    cierra: las diferencias se aplican como AJUSTE en el kardex."""
    __tablename__ = "tomas_inventario"
    id_toma: Mapped[int] = mapped_column(primary_key=True)
    id_ubicacion: Mapped[int | None] = mapped_column(ForeignKey("ubicaciones.id_ubicacion", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(10), default="ABIERTA", index=True)
    fecha_apertura: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cerrada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    observacion: Mapped[str | None] = mapped_column(String(250))

    ubicacion: Mapped[Ubicaciones | None] = relationship()
    conteos: Mapped[list["ConteosInventario"]] = relationship(back_populates="toma",
                                                              order_by="ConteosInventario.id_conteo")
    __table_args__ = (CheckConstraint("estado IN ('ABIERTA','CERRADA')", name="ck_tomas_estado"),)


class ConteosInventario(CamposControl, Base):
    __tablename__ = "conteos_inventario"
    id_conteo: Mapped[int] = mapped_column(primary_key=True)
    id_toma: Mapped[int] = mapped_column(ForeignKey("tomas_inventario.id_toma", ondelete="RESTRICT"))
    id_lote: Mapped[int] = mapped_column(ForeignKey("lotes.id_lote", ondelete="RESTRICT"))
    cantidad_contada: Mapped[int | None] = mapped_column(Integer)
    stock_al_contar: Mapped[int | None] = mapped_column(Integer)   # stock del sistema en el momento del conteo
    contado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    fecha_conteo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ajuste_aplicado: Mapped[int | None] = mapped_column(Integer)

    toma: Mapped[TomasInventario] = relationship(back_populates="conteos")
    lote: Mapped[Lotes] = relationship(lazy="joined", innerjoin=True)
    __table_args__ = (
        UniqueConstraint("id_toma", "id_lote", name="uq_conteos_toma_lote"),
        CheckConstraint("cantidad_contada IS NULL OR cantidad_contada >= 0", name="ck_conteos_cantidad"),
    )


# ------------------------------------------------- FOFAR: servicios farmacéuticos
class ActividadesFarmaceuticas(CamposControl, Base):
    """Atención farmacéutica, farmacovigilancia y talleres del Q.F. (FOFAR indicador N.º 4)."""
    __tablename__ = "actividades_farmaceuticas"
    id_actividad: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(24), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    id_paciente: Mapped[int | None] = mapped_column(ForeignKey("pacientes.id_paciente", ondelete="RESTRICT"))
    id_medicamento: Mapped[int | None] = mapped_column(ForeignKey("medicamentos.id_medicamento", ondelete="RESTRICT"))
    id_lote: Mapped[int | None] = mapped_column(ForeignKey("lotes.id_lote", ondelete="RESTRICT"))
    descripcion: Mapped[str] = mapped_column(String(1000))
    resultado: Mapped[str | None] = mapped_column(String(500))
    participantes: Mapped[int | None] = mapped_column(Integer)
    gravedad: Mapped[str | None] = mapped_column(String(10))
    fecha_notificacion: Mapped[date | None] = mapped_column(Date)      # ingreso al SVI del ISP
    folio_isp: Mapped[str | None] = mapped_column(String(30))
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(10), default="VIGENTE")
    fecha_anulacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    motivo_anulacion: Mapped[str | None] = mapped_column(String(250))

    paciente: Mapped[Pacientes | None] = relationship()
    medicamento: Mapped[Medicamentos | None] = relationship()
    lote: Mapped[Lotes | None] = relationship()
    __table_args__ = (
        CheckConstraint("tipo IN ('REVISION_MEDICACION','CONCILIACION','EDUCACION','SEGUIMIENTO_FT',"
                        "'RAM','FALLA_CALIDAD','EVENTO_ADVERSO','TALLER')", name="ck_actividades_tipo"),
        CheckConstraint("gravedad IS NULL OR gravedad IN ('LEVE','MODERADA','GRAVE')", name="ck_actividades_gravedad"),
        CheckConstraint("participantes IS NULL OR participantes > 0", name="ck_actividades_participantes"),
        CheckConstraint("estado IN ('VIGENTE','ANULADA')", name="ck_actividades_estado"),
    )


class ProgramacionActividades(CamposControl, Base):
    """Actividades farmacéuticas programadas para el año (meta: 50 % a junio, 100 % a diciembre)."""
    __tablename__ = "programacion_actividades"
    anio: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    cantidad: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_programacion_cantidad"),)


# ------------------------------------------------- FOFAR: préstamos entre establecimientos
class Prestamos(CamposControl, Base):
    """Préstamo de medicamentos con otro establecimiento ante un quiebre (Anexo 1 FOFAR).

    OTORGADO: sale stock nuestro (PRESTAMO_SALIDA) y vuelve al devolverlo.
    RECIBIDO: entra un lote (PRESTAMO_ENTRADA) y sale al devolverlo.
    """
    __tablename__ = "prestamos"
    id_prestamo: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))
    establecimiento: Mapped[str] = mapped_column(String(120))
    id_medicamento: Mapped[int] = mapped_column(ForeignKey("medicamentos.id_medicamento", ondelete="RESTRICT"))
    cantidad: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[date] = mapped_column(Date)
    fecha_compromiso: Mapped[date] = mapped_column(Date)
    documento: Mapped[str | None] = mapped_column(String(30))
    observacion: Mapped[str | None] = mapped_column(String(250))
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE", index=True)
    fecha_devolucion: Mapped[date | None] = mapped_column(Date)

    medicamento: Mapped[Medicamentos] = relationship(lazy="joined", innerjoin=True)
    __table_args__ = (
        CheckConstraint("tipo IN ('OTORGADO','RECIBIDO')", name="ck_prestamos_tipo"),
        CheckConstraint("cantidad > 0", name="ck_prestamos_cantidad"),
        CheckConstraint("estado IN ('PENDIENTE','DEVUELTO')", name="ck_prestamos_estado"),
        CheckConstraint("fecha_compromiso >= fecha", name="ck_prestamos_compromiso"),
    )


# ----------------------------------------------------------- auditoría
class EventosPendientes(Base):
    """Bandeja de salida (patrón outbox) hacia DynamoDB eventos_auditoria."""
    __tablename__ = "eventos_pendientes"
    id_evento: Mapped[int] = mapped_column(primary_key=True)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    tipo_evento: Mapped[str] = mapped_column(String(40))
    entidad: Mapped[str] = mapped_column(String(40))
    id_entidad: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_eventos_no_publicados", "publicado_en", "id_evento"),)


# ----------------------------------------- tablas de solo inserción (triggers)
def _proteger_solo_insercion(tabla) -> None:
    nombre = tabla.name
    event.listen(tabla, "after_create", DDL(
        f"CREATE TRIGGER tg_{nombre}_sin_update BEFORE UPDATE ON {nombre} "
        f"BEGIN SELECT RAISE(ABORT, '{nombre} es de solo insercion'); END;").execute_if(dialect="sqlite"))
    event.listen(tabla, "after_create", DDL(
        f"CREATE TRIGGER tg_{nombre}_sin_delete BEFORE DELETE ON {nombre} "
        f"BEGIN SELECT RAISE(ABORT, '{nombre} es de solo insercion'); END;").execute_if(dialect="sqlite"))
    event.listen(tabla, "after_create", DDL(
        f"CREATE OR REPLACE FUNCTION fn_{nombre}_solo_insercion() RETURNS trigger AS $$ "
        f"BEGIN RAISE EXCEPTION '{nombre} es de solo insercion' "
        f"USING ERRCODE = 'integrity_constraint_violation'; END; $$ LANGUAGE plpgsql; "
        f"CREATE TRIGGER tg_{nombre}_inmutable BEFORE UPDATE OR DELETE ON {nombre} "
        f"FOR EACH ROW EXECUTE FUNCTION fn_{nombre}_solo_insercion();").execute_if(dialect="postgresql"))


TABLAS_SOLO_INSERCION = (AsientosControlados.__table__, MovimientosStock.__table__)
for _tabla in TABLAS_SOLO_INSERCION:
    _proteger_solo_insercion(_tabla)


def borrar_esquema(motor) -> None:
    """Solo para desarrollo y pruebas: quita los triggers de inmutabilidad y borra todas las tablas."""
    es_sqlite = motor.dialect.name == "sqlite"
    with motor.connect() as conexion:
        if es_sqlite:  # DROP TABLE en SQLite borra fila a fila: se apagan FK y triggers primero
            conexion.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for tabla in TABLAS_SOLO_INSERCION:
            if es_sqlite:
                for sufijo in ("sin_update", "sin_delete"):
                    conexion.execute(text(f"DROP TRIGGER IF EXISTS tg_{tabla.name}_{sufijo}"))
            else:
                conexion.execute(text(f"DROP TABLE IF EXISTS {tabla.name} CASCADE"))
        Base.metadata.drop_all(conexion)
        conexion.execute(text("DROP TABLE IF EXISTS alembic_version"))
        conexion.commit()
        if es_sqlite:
            conexion.exec_driver_sql("PRAGMA foreign_keys=ON")
