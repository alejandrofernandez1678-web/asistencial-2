"""Devoluciones de pacientes: medicamento entregado que vuelve a la farmacia.

Distinto de anular una dispensación (error de registro): aquí la entrega fue
real y la receta sigue contando lo entregado. El Q.F. decide el destino:
  * REINGRESO: el envase está íntegro; vuelve al mismo lote con un movimiento
    DEVOLUCION en el kardex. Solo si el lote está disponible y no vencido.
  * DESCARTE: no vuelve al stock; queda el registro (y su motivo).
En controlados se agrega además un asiento DEVOLUCION en el libro.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..models import AsientosControlados, DetallesDispensacion, Devoluciones, Usuarios
from .auditoria import registrar_evento
from .inventario import exigir_motivo, mover_stock, obtener_lote
from ..reloj import iso_utc
from .libro import registrar_asiento

DESTINOS = ("REINGRESO", "DESCARTE")


def describir_devolucion(d: Devoluciones) -> dict:
    return {"id_devolucion": d.id_devolucion, "id_detalle_disp": d.id_detalle_disp, "cantidad": d.cantidad,
            "destino": d.destino, "motivo": d.motivo, "fecha_hora": iso_utc(d.fecha_hora),
            "medicamento": d.detalle.lote.medicamento.nombre, "lote": d.detalle.lote.codigo_lote}


def registrar_devolucion(db: Session, qf: Usuarios, *, id_detalle_disp: int, cantidad: int, destino: str,
                         motivo: str, hoy: date) -> Devoluciones:
    motivo = exigir_motivo(motivo)
    if destino not in DESTINOS:
        raise ReglaNegocioError("DESTINO_INVALIDO", "El destino debe ser REINGRESO o DESCARTE.")
    detalle = db.get(DetallesDispensacion, id_detalle_disp)
    if detalle is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La línea de entrega no existe.")
    if detalle.dispensacion.estado != "VIGENTE":
        raise ReglaNegocioError("DISPENSACION_ANULADA", "La entrega fue anulada; no hay nada que devolver.")
    devuelto = db.scalar(select(func.coalesce(func.sum(Devoluciones.cantidad), 0)).where(
        Devoluciones.id_detalle_disp == id_detalle_disp)) or 0
    if cantidad <= 0 or cantidad > detalle.cantidad - devuelto:
        raise ReglaNegocioError("CANTIDAD_INVALIDA",
                                f"Se pueden devolver entre 1 y {detalle.cantidad - devuelto} unidades de esta línea.")
    medicamento = detalle.lote.medicamento
    if medicamento.es_controlado and db.scalar(select(AsientosControlados.id_asiento).where(
            AsientosControlados.id_detalle_disp == id_detalle_disp, AsientosControlados.tipo == "DEVOLUCION")):
        raise ReglaNegocioError("DEVOLUCION_CONTROLADO_REGISTRADA",
                                "Esta línea de controlado ya tiene una devolución en el libro.")

    lote = obtener_lote(db, detalle.id_lote)
    if destino == "REINGRESO" and (lote.estado != "DISPONIBLE" or lote.fecha_vencimiento <= hoy):
        raise ReglaNegocioError("REINGRESO_NO_PERMITIDO",
                                f"El lote {lote.codigo_lote} no admite reingreso (está {lote.estado.lower()} o vencido); "
                                "registre la devolución como descarte.")

    devolucion = Devoluciones(id_detalle_disp=id_detalle_disp, cantidad=cantidad, destino=destino, motivo=motivo,
                              id_usuario=qf.id_usuario, creado_por=qf.id_usuario)
    db.add(devolucion)
    db.flush()
    if destino == "REINGRESO":
        mover_stock(db, lote, tipo="DEVOLUCION", cantidad=cantidad, usuario=qf, motivo=motivo,
                    referencia_tipo="devoluciones", referencia_id=devolucion.id_devolucion)
    if medicamento.es_controlado:
        registrar_asiento(db, tipo="DEVOLUCION", detalle=detalle, qf=qf, contenido={
            "folio": detalle.dispensacion.receta.folio, "medicamento": medicamento.codigo,
            "nombre": medicamento.nombre, "lote": lote.codigo_lote,
            "cantidad": cantidad,
            "destino": destino, "motivo": motivo})
    registrar_evento(db, tipo="DEVOLUCION_REGISTRADA", entidad="devoluciones", id_entidad=devolucion.id_devolucion,
                     id_usuario=qf.id_usuario, id_dispensacion=detalle.id_dispensacion, cantidad=cantidad,
                     destino=destino, controlado=medicamento.es_controlado)
    return devolucion
