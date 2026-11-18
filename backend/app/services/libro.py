"""Libro digital de controlados (D.S. 404 y 405, art. 18).

El reglamento exige registrar los ingresos (proveedor y factura o guía), los egresos
(N.º de receta cheque, médico, paciente y domicilio, quien retira) y los saldos.
Cada asiento se encadena por hash con el anterior y guarda el saldo del producto
después del movimiento; el libro es de solo inserción (trigger en la base).

Solo un Q.F. registra movimientos de controlados: recepción, merma y ajustes.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.libro import HASH_GENESIS, calcular_hash
from ..models import AsientosControlados, DetallesDispensacion, Lotes, Usuarios
from ..reloj import ahora
from ..security.rbac import Permisos, tiene_permiso


def exigir_qf(usuario: Usuarios, accion: str = "registrar movimientos de controlados") -> None:
    if not tiene_permiso(usuario.rol.nombre, Permisos.FIRMAR_CONTROLADOS):
        raise ReglaNegocioError("REQUIERE_QF", f"Solo un Q.F. puede {accion}.")


def saldo_medicamento(db: Session, id_medicamento: int) -> int:
    db.flush()
    return db.scalar(select(func.coalesce(func.sum(Lotes.unidades_disp), 0))
                     .where(Lotes.id_medicamento == id_medicamento)) or 0


def registrar_asiento(db: Session, *, tipo: str, qf: Usuarios, contenido: dict,
                      detalle: DetallesDispensacion | None = None, lote: Lotes | None = None,
                      id_asiento_origen: int | None = None) -> AsientosControlados:
    """Agrega un asiento al final de la cadena. Llamar después de mover el stock: el saldo ya lo incluye."""
    lote_referencia = lote if lote is not None else detalle.lote
    ultimo = db.scalar(select(AsientosControlados).order_by(AsientosControlados.nro_asiento.desc()).limit(1))
    nro = (ultimo.nro_asiento + 1) if ultimo else 1
    hash_previo = ultimo.hash_actual if ultimo else HASH_GENESIS
    contenido = {"nro_asiento": nro, "tipo": tipo, **contenido, "qf": qf.rut, "fecha_hora": ahora().isoformat(),
                 "saldo": saldo_medicamento(db, lote_referencia.id_medicamento)}
    asiento = AsientosControlados(nro_asiento=nro, tipo=tipo,
                                  id_detalle_disp=detalle.id_detalle_disp if detalle is not None else None,
                                  id_lote=lote.id_lote if lote is not None else None,
                                  id_asiento_origen=id_asiento_origen, id_usuario_qf=qf.id_usuario,
                                  contenido=contenido, hash_previo=hash_previo,
                                  hash_actual=calcular_hash(hash_previo, contenido))
    db.add(asiento)
    db.flush()
    return asiento


def asiento_de_lote(db: Session, *, tipo: str, lote: Lotes, cantidad: int, qf: Usuarios, motivo: str | None = None,
                    **extra) -> AsientosControlados:
    """INGRESO, MERMA o AJUSTE de un lote controlado (cantidad con signo: + entra, - sale)."""
    return registrar_asiento(db, tipo=tipo, qf=qf, lote=lote, contenido={
        "medicamento": lote.medicamento.codigo, "nombre": lote.medicamento.nombre, "lote": lote.codigo_lote,
        "vencimiento": lote.fecha_vencimiento.isoformat(), "cantidad": cantidad,
        **({"motivo": motivo} if motivo else {}), **extra})
