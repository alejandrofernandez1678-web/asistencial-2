"""Préstamos de medicamentos entre establecimientos (OT FOFAR, Anexo 1).

Ante un quiebre de stock, un CESFAM presta a otro con un formulario y una fecha
comprometida de devolución. Cada préstamo mueve stock por el kardex:
  * OTORGADO: sale de nuestros lotes en orden FEFO (PRESTAMO_SALIDA); al devolverlo
    entra un lote (PRESTAMO_ENTRADA).
  * RECIBIDO: entra un lote (PRESTAMO_ENTRADA); al devolverlo sale en orden FEFO.
Los controlados no se prestan: su traspaso exige resolución sanitaria.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import fefo
from ..domain.errores import ReglaNegocioError
from ..models import Lotes, Medicamentos, Prestamos, Usuarios
from ..repositories.lotes import a_lote_fefo, lotes_de_medicamento
from .auditoria import registrar_evento
from .inventario import ingresar_lote, mover_stock


def describir_prestamo(p: Prestamos, hoy: date) -> dict:
    return {"id_prestamo": p.id_prestamo, "tipo": p.tipo, "establecimiento": p.establecimiento,
            "id_medicamento": p.id_medicamento, "medicamento": p.medicamento.nombre, "cantidad": p.cantidad,
            "fecha": p.fecha.isoformat(), "fecha_compromiso": p.fecha_compromiso.isoformat(),
            "documento": p.documento, "observacion": p.observacion, "estado": p.estado,
            "fecha_devolucion": p.fecha_devolucion.isoformat() if p.fecha_devolucion else None,
            "vencido": p.estado == "PENDIENTE" and p.fecha_compromiso < hoy}


def _salida_fefo(db: Session, usuario: Usuarios, prestamo: Prestamos, hoy: date, motivo: str) -> list[str]:
    lotes_orm = {l.codigo_lote: l for l in lotes_de_medicamento(db, prestamo.id_medicamento, bloquear=True)}
    plan = fefo.planificar([a_lote_fefo(l) for l in lotes_orm.values()], prestamo.id_medicamento, prestamo.cantidad, hoy)
    for asignacion in plan:
        mover_stock(db, lotes_orm[asignacion.lote.codigo_lote], tipo="PRESTAMO_SALIDA", cantidad=-asignacion.cantidad,
                    usuario=usuario, motivo=motivo, referencia_tipo="prestamos", referencia_id=prestamo.id_prestamo)
    return [a.lote.codigo_lote for a in plan]


def _entrada(db: Session, usuario: Usuarios, prestamo: Prestamos, hoy: date, motivo: str, *,
             codigo_lote: str | None, fecha_vencimiento: date | None, id_ubicacion: int | None) -> Lotes:
    if not (codigo_lote and fecha_vencimiento and id_ubicacion):
        raise ReglaNegocioError("LOTE_REQUERIDO", "Indique el lote, su vencimiento y la ubicación donde se guarda.")
    existente = db.scalar(select(Lotes).where(Lotes.id_medicamento == prestamo.id_medicamento,
                                              Lotes.codigo_lote == codigo_lote))
    if existente is not None:  # el mismo lote del fabricante que ya tenemos: se suma a ese lote
        if existente.fecha_vencimiento != fecha_vencimiento or existente.estado != "DISPONIBLE":
            raise ReglaNegocioError("LOTE_DUPLICADO", f"El lote {codigo_lote} ya existe con otro vencimiento o "
                                    "no está disponible; revise el código.")
        mover_stock(db, existente, tipo="PRESTAMO_ENTRADA", cantidad=prestamo.cantidad, usuario=usuario, motivo=motivo,
                    referencia_tipo="prestamos", referencia_id=prestamo.id_prestamo)
        return existente
    lote, _ = ingresar_lote(db, usuario, id_medicamento=prestamo.id_medicamento, codigo_lote=codigo_lote,
                            fecha_vencimiento=fecha_vencimiento, unidades=prestamo.cantidad,
                            id_ubicacion=id_ubicacion, hoy=hoy, proveedor=prestamo.establecimiento,
                            tipo_documento="PRESTAMO", numero_documento=prestamo.documento,
                            fecha_documento=hoy, tipo_movimiento="PRESTAMO_ENTRADA", motivo=motivo,
                            referencia_tipo="prestamos", referencia_id=prestamo.id_prestamo)
    return lote


def registrar_prestamo(db: Session, usuario: Usuarios, *, tipo: str, establecimiento: str, id_medicamento: int,
                       cantidad: int, fecha_compromiso: date, hoy: date, documento: str | None = None,
                       observacion: str | None = None, codigo_lote: str | None = None,
                       fecha_vencimiento: date | None = None, id_ubicacion: int | None = None) -> Prestamos:
    if tipo not in ("OTORGADO", "RECIBIDO"):
        raise ReglaNegocioError("TIPO_INVALIDO", "El préstamo es OTORGADO o RECIBIDO.")
    medicamento = db.get(Medicamentos, id_medicamento)
    if medicamento is None or not medicamento.activo:
        raise ReglaNegocioError("MEDICAMENTO_INACTIVO", "El medicamento no existe o está dado de baja.")
    if medicamento.es_controlado:
        raise ReglaNegocioError("CONTROLADO_NO_PRESTABLE", "Los controlados no se prestan: su traspaso exige "
                                "resolución sanitaria.")
    if cantidad <= 0:
        raise ReglaNegocioError("CANTIDAD_INVALIDA", "La cantidad debe ser mayor que cero.")
    if fecha_compromiso < hoy:
        raise ReglaNegocioError("FECHA_INVALIDA", "La fecha comprometida de devolución no puede ser pasada.")
    prestamo = Prestamos(tipo=tipo, establecimiento=establecimiento.strip(), id_medicamento=id_medicamento,
                         cantidad=cantidad, fecha=hoy, fecha_compromiso=fecha_compromiso,
                         documento=(documento or "").strip() or None, observacion=(observacion or "").strip() or None,
                         estado="PENDIENTE", creado_por=usuario.id_usuario)
    db.add(prestamo)
    db.flush()
    db.refresh(prestamo)
    motivo = f"Préstamo {'a' if tipo == 'OTORGADO' else 'de'} {prestamo.establecimiento}"[:250]
    if tipo == "OTORGADO":
        lotes = _salida_fefo(db, usuario, prestamo, hoy, motivo)
    else:
        lotes = [_entrada(db, usuario, prestamo, hoy, motivo, codigo_lote=codigo_lote,
                          fecha_vencimiento=fecha_vencimiento, id_ubicacion=id_ubicacion).codigo_lote]
    registrar_evento(db, tipo="PRESTAMO_REGISTRADO", entidad="prestamos", id_entidad=prestamo.id_prestamo,
                     id_usuario=usuario.id_usuario, tipo_prestamo=tipo, establecimiento=prestamo.establecimiento,
                     cantidad=cantidad, lotes=lotes)
    return prestamo


def devolver_prestamo(db: Session, usuario: Usuarios, id_prestamo: int, hoy: date, *, codigo_lote: str | None = None,
                      fecha_vencimiento: date | None = None, id_ubicacion: int | None = None) -> Prestamos:
    prestamo = db.get(Prestamos, id_prestamo, with_for_update=True)
    if prestamo is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El préstamo no existe.")
    if prestamo.estado != "PENDIENTE":
        raise ReglaNegocioError("PRESTAMO_DEVUELTO", "El préstamo ya fue devuelto.")
    motivo = f"Devolución de préstamo {'de' if prestamo.tipo == 'OTORGADO' else 'a'} {prestamo.establecimiento}"[:250]
    if prestamo.tipo == "OTORGADO":
        _entrada(db, usuario, prestamo, hoy, motivo, codigo_lote=codigo_lote, fecha_vencimiento=fecha_vencimiento,
                 id_ubicacion=id_ubicacion)
    else:
        _salida_fefo(db, usuario, prestamo, hoy, motivo)
    prestamo.estado, prestamo.fecha_devolucion, prestamo.actualizado_por = "DEVUELTO", hoy, usuario.id_usuario
    registrar_evento(db, tipo="PRESTAMO_DEVUELTO", entidad="prestamos", id_entidad=prestamo.id_prestamo,
                     id_usuario=usuario.id_usuario)
    return prestamo


def listar_prestamos(db: Session, hoy: date, solo_pendientes: bool = False) -> list[dict]:
    consulta = select(Prestamos).order_by(Prestamos.estado.desc(), Prestamos.fecha_compromiso, Prestamos.id_prestamo)
    if solo_pendientes:
        consulta = consulta.where(Prestamos.estado == "PENDIENTE")
    return [describir_prestamo(p, hoy) for p in db.scalars(consulta).unique()]
