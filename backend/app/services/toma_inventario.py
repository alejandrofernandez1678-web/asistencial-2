"""Toma de inventario físico (FOFAR: inventario semestral valorizado; arqueo de controlados).

1. El Q.F. abre la toma (total o de una ubicación): se listan los lotes con stock.
2. Bodega y TENS cuentan a ciegas: la pantalla de conteo no muestra el stock del sistema.
   Al registrar cada conteo se guarda el stock que tenía el sistema en ese momento,
   así las entregas hechas durante la toma no se confunden con diferencias.
3. El Q.F. revisa las diferencias y cierra: cada diferencia se aplica con un
   movimiento AJUSTE en el kardex (y un asiento AJUSTE en el libro si es controlado).
Una toma cerrada no se modifica.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..models import ConteosInventario, Lotes, TomasInventario, Ubicaciones, Usuarios
from ..reloj import ahora, iso_utc
from .auditoria import registrar_evento
from .inventario import costo_unitario, mover_stock, obtener_lote
from .libro import asiento_de_lote, exigir_qf


def abrir_toma(db: Session, usuario: Usuarios, *, id_ubicacion: int | None = None,
               observacion: str | None = None) -> TomasInventario:
    abiertas = db.scalars(select(TomasInventario).where(TomasInventario.estado == "ABIERTA")).all()
    if any(t.id_ubicacion is None or id_ubicacion is None or t.id_ubicacion == id_ubicacion for t in abiertas):
        raise ReglaNegocioError("TOMA_ABIERTA", "Ya hay una toma de inventario abierta que incluye esa ubicación; "
                                "ciérrela antes de abrir otra.")
    if id_ubicacion is not None:
        ubicacion = db.get(Ubicaciones, id_ubicacion)
        if ubicacion is None or not ubicacion.activo:
            raise ReglaNegocioError("UBICACION_INACTIVA", "La ubicación no existe o está dada de baja.")
    consulta = select(Lotes).where(Lotes.unidades_disp > 0, Lotes.estado.in_(["DISPONIBLE", "ALERTA_SANITARIA"]))
    if id_ubicacion is not None:
        consulta = consulta.where(Lotes.id_ubicacion == id_ubicacion)
    lotes = list(db.scalars(consulta.order_by(Lotes.id_ubicacion, Lotes.id_medicamento, Lotes.fecha_vencimiento)).unique())
    if not lotes:
        raise ReglaNegocioError("SIN_LOTES", "No hay lotes con stock para contar en esa ubicación.")
    toma = TomasInventario(id_ubicacion=id_ubicacion, estado="ABIERTA", fecha_apertura=ahora(),
                           observacion=(observacion or "").strip() or None, creado_por=usuario.id_usuario)
    db.add(toma)
    db.flush()
    for lote in lotes:
        db.add(ConteosInventario(id_toma=toma.id_toma, id_lote=lote.id_lote, creado_por=usuario.id_usuario))
    db.flush()
    db.refresh(toma)
    registrar_evento(db, tipo="TOMA_INVENTARIO_ABIERTA", entidad="tomas_inventario", id_entidad=toma.id_toma,
                     id_usuario=usuario.id_usuario, id_ubicacion=id_ubicacion, lotes=len(lotes))
    return toma


def obtener_toma(db: Session, id_toma: int) -> TomasInventario:
    toma = db.get(TomasInventario, id_toma)
    if toma is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La toma de inventario no existe.")
    return toma


def registrar_conteo(db: Session, usuario: Usuarios, id_toma: int, id_conteo: int, cantidad: int) -> ConteosInventario:
    toma = obtener_toma(db, id_toma)
    if toma.estado != "ABIERTA":
        raise ReglaNegocioError("TOMA_CERRADA", "La toma de inventario ya está cerrada.")
    conteo = db.get(ConteosInventario, id_conteo)
    if conteo is None or conteo.id_toma != id_toma:
        raise ReglaNegocioError("NO_ENCONTRADO", "El conteo no pertenece a esta toma.")
    if cantidad < 0:
        raise ReglaNegocioError("CANTIDAD_INVALIDA", "La cantidad contada no puede ser negativa.")
    lote = obtener_lote(db, conteo.id_lote)
    conteo.cantidad_contada, conteo.stock_al_contar = cantidad, lote.unidades_disp
    conteo.contado_por, conteo.fecha_conteo, conteo.actualizado_por = usuario.id_usuario, ahora(), usuario.id_usuario
    return conteo


def cerrar_toma(db: Session, qf: Usuarios, id_toma: int, observacion: str | None = None) -> TomasInventario:
    exigir_qf(qf, "cerrar una toma de inventario")
    toma = obtener_toma(db, id_toma)
    if toma.estado != "ABIERTA":
        raise ReglaNegocioError("TOMA_CERRADA", "La toma de inventario ya está cerrada.")
    sin_contar = [c.lote.codigo_lote for c in toma.conteos if c.cantidad_contada is None]
    if sin_contar:
        raise ReglaNegocioError("CONTEO_INCOMPLETO", f"Faltan {len(sin_contar)} lote(s) por contar: "
                                f"{', '.join(sin_contar[:5])}{'…' if len(sin_contar) > 5 else ''}.")
    motivo = f"Toma de inventario N.º {toma.id_toma}" + (f": {observacion.strip()}" if (observacion or "").strip() else "")
    ajustes = 0
    for conteo in toma.conteos:
        diferencia = conteo.cantidad_contada - conteo.stock_al_contar
        conteo.ajuste_aplicado = diferencia
        if diferencia == 0:
            continue
        lote = obtener_lote(db, conteo.id_lote)
        if lote.unidades_disp + diferencia < 0:
            raise ReglaNegocioError("AJUSTE_INVALIDO", f"El lote {lote.codigo_lote} quedaría con stock negativo; "
                                    "vuelva a contarlo.")
        mover_stock(db, lote, tipo="AJUSTE", cantidad=diferencia, usuario=qf, motivo=motivo[:250],
                    referencia_tipo="tomas_inventario", referencia_id=toma.id_toma)
        if lote.medicamento.es_controlado:
            asiento_de_lote(db, tipo="AJUSTE", lote=lote, cantidad=diferencia, qf=qf, motivo=motivo[:250])
        ajustes += 1
    toma.estado, toma.fecha_cierre, toma.cerrada_por = "CERRADA", ahora(), qf.id_usuario
    if (observacion or "").strip():
        toma.observacion = ((toma.observacion + " · ") if toma.observacion else "") + observacion.strip()
        toma.observacion = toma.observacion[:250]
    toma.actualizado_por = qf.id_usuario
    registrar_evento(db, tipo="TOMA_INVENTARIO_CERRADA", entidad="tomas_inventario", id_entidad=toma.id_toma,
                     id_usuario=qf.id_usuario, ajustes=ajustes)
    return toma


def _valor(conteo: ConteosInventario, unidades: int | None) -> int | None:
    costo = costo_unitario(conteo.lote)
    return round(costo * unidades) if costo is not None and unidades is not None else None


def describir_toma(toma: TomasInventario, ver_sistema: bool) -> dict:
    """ver_sistema=False es el conteo a ciegas: sin stock del sistema ni diferencias."""
    filas = []
    for c in toma.conteos:
        fila = {"id_conteo": c.id_conteo, "id_lote": c.id_lote, "codigo_lote": c.lote.codigo_lote,
                "medicamento": c.lote.medicamento.nombre, "es_controlado": c.lote.medicamento.es_controlado,
                "ubicacion": c.lote.ubicacion.codigo, "fecha_vencimiento": c.lote.fecha_vencimiento.isoformat(),
                "cantidad_contada": c.cantidad_contada, "contado": c.cantidad_contada is not None}
        if ver_sistema:
            diferencia = (c.cantidad_contada - c.stock_al_contar) if c.cantidad_contada is not None else None
            fila.update(stock_al_contar=c.stock_al_contar, diferencia=diferencia,
                        valor_diferencia=_valor(c, diferencia), ajuste_aplicado=c.ajuste_aplicado)
        filas.append(fila)
    contados = sum(1 for f in filas if f["contado"])
    resumen = {"lotes": len(filas), "contados": contados}
    if ver_sistema:
        con_diferencia = [f for f in filas if f.get("diferencia")]
        resumen.update(con_diferencia=len(con_diferencia),
                       valor_diferencias=sum(f["valor_diferencia"] or 0 for f in con_diferencia))
    return {"id_toma": toma.id_toma, "estado": toma.estado,
            "ubicacion": toma.ubicacion.codigo if toma.ubicacion else "Toda la farmacia",
            "fecha_apertura": iso_utc(toma.fecha_apertura),
            "fecha_cierre": iso_utc(toma.fecha_cierre),
            "observacion": toma.observacion, "resumen": resumen, "conteos": filas}


def listar_tomas(db: Session, limite: int = 30) -> list[dict]:
    tomas = db.scalars(select(TomasInventario).order_by(TomasInventario.id_toma.desc()).limit(limite)).all()
    return [{"id_toma": t.id_toma, "estado": t.estado, "ubicacion": t.ubicacion.codigo if t.ubicacion else "Toda la farmacia",
             "fecha_apertura": iso_utc(t.fecha_apertura),
             "fecha_cierre": iso_utc(t.fecha_cierre),
             "lotes": len(t.conteos), "contados": sum(1 for c in t.conteos if c.cantidad_contada is not None)}
            for t in tomas]
