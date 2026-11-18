"""Casos de uso de inventario: ingreso, ajuste, anulación y merma de lotes.

Todo cambio de stock pasa por mover_stock, que actualiza el lote y escribe
el movimiento en el kardex en la misma transacción. En un medicamento
controlado, además, cada ingreso, merma o ajuste agrega su asiento al libro
(D.S. 404/405 art. 18) y solo lo puede registrar un Q.F.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.lotes import (EstadosRegistroLote, dias_para_vencer, es_dispensable, estado_lote,
                            vencimiento_corto_en_recepcion)
from ..models import Lotes, Medicamentos, Mermas, MovimientosStock, Ubicaciones, Usuarios
from ..reloj import ahora
from .auditoria import registrar_evento
from .libro import asiento_de_lote, exigir_qf

LARGO_MINIMO_MOTIVO = 10
MOTIVOS_MERMA = {"VENCIMIENTO", "DANO", "ALERTA_SANITARIA"}
TIPOS_DOCUMENTO = {"FACTURA": "Factura", "GUIA": "Guía de despacho", "PRESTAMO": "Préstamo", "DONACION": "Donación"}


def costo_unitario(lote: Lotes) -> float | None:
    """Costo por unidad mínima: costo de la factura / unidades ingresadas (None si no se registró)."""
    if lote.costo_total is None:
        return None
    return lote.costo_total / lote.unidades_ingresadas


def exigir_motivo(motivo: str | None) -> str:
    motivo = (motivo or "").strip()
    if len(motivo) < LARGO_MINIMO_MOTIVO:
        raise ReglaNegocioError("MOTIVO_REQUERIDO",
                                f"Debe indicar un motivo de al menos {LARGO_MINIMO_MOTIVO} caracteres.")
    return motivo


def obtener_lote(db: Session, id_lote: int) -> Lotes:
    lote = db.get(Lotes, id_lote, with_for_update=True)
    if lote is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El lote no existe.")
    return lote


def mover_stock(db: Session, lote: Lotes, *, tipo: str, cantidad: int, usuario: Usuarios,
                motivo: str | None = None, referencia_tipo: str | None = None,
                referencia_id: int | None = None) -> MovimientosStock:
    saldo = lote.unidades_disp + cantidad
    if saldo < 0:
        raise ReglaNegocioError("STOCK_INSUFICIENTE", f"El lote {lote.codigo_lote} quedaría con stock negativo.")
    lote.unidades_disp = saldo
    lote.actualizado_por = usuario.id_usuario
    movimiento = MovimientosStock(id_lote=lote.id_lote, tipo=tipo, cantidad=cantidad, saldo_resultante=saldo,
                                  motivo=motivo, referencia_tipo=referencia_tipo, referencia_id=referencia_id,
                                  id_usuario=usuario.id_usuario)
    db.add(movimiento)
    return movimiento


def ingresar_lote(db: Session, usuario: Usuarios, *, id_medicamento: int, codigo_lote: str,
                  fecha_vencimiento: date, unidades: int, id_ubicacion: int, hoy: date,
                  proveedor: str | None = None, tipo_documento: str | None = None,
                  numero_documento: str | None = None, fecha_documento: date | None = None,
                  costo_total: int | None = None, tipo_movimiento: str = "INGRESO",
                  motivo: str = "Ingreso de lote", referencia_tipo: str | None = None,
                  referencia_id: int | None = None) -> tuple[Lotes, list[str]]:
    medicamento = db.get(Medicamentos, id_medicamento)
    if medicamento is None or not medicamento.activo:
        raise ReglaNegocioError("MEDICAMENTO_INACTIVO", "El medicamento no existe o está dado de baja.")
    ubicacion = db.get(Ubicaciones, id_ubicacion)
    if ubicacion is None or not ubicacion.activo:
        raise ReglaNegocioError("UBICACION_INACTIVA", "La ubicación no existe o está dada de baja.")
    if medicamento.es_controlado and ubicacion.tipo != "CAJA_SEGURIDAD":
        raise ReglaNegocioError("UBICACION_CONTROLADO", "Un medicamento controlado solo se guarda en caja de seguridad.")
    if unidades <= 0:
        raise ReglaNegocioError("CANTIDAD_INVALIDA", "Las unidades deben ser mayores que cero.")
    if fecha_vencimiento <= hoy:
        raise ReglaNegocioError("LOTE_VENCIDO", "No se puede ingresar un lote vencido.")
    duplicado = db.scalar(select(Lotes.id_lote).where(Lotes.id_medicamento == id_medicamento,
                                                      Lotes.codigo_lote == codigo_lote))
    if duplicado:
        raise ReglaNegocioError("LOTE_DUPLICADO", f"El lote {codigo_lote} ya existe para este medicamento.")
    if tipo_documento is not None and tipo_documento not in TIPOS_DOCUMENTO:
        raise ReglaNegocioError("DOCUMENTO_INVALIDO", "El documento debe ser factura, guía, préstamo o donación.")
    if fecha_documento is not None and fecha_documento > hoy:
        raise ReglaNegocioError("FECHA_INVALIDA", "La fecha del documento no puede ser futura.")
    if costo_total is not None and costo_total < 0:
        raise ReglaNegocioError("COSTO_INVALIDO", "El costo no puede ser negativo.")
    if medicamento.es_controlado:
        exigir_qf(usuario, "recibir medicamentos controlados")
        if not ((proveedor or "").strip() and tipo_documento and (numero_documento or "").strip() and fecha_documento):
            raise ReglaNegocioError("DOCUMENTO_REQUERIDO", "En un controlado el libro exige proveedor, tipo, número "
                                    "y fecha del documento de recepción (D.S. 404/405 art. 18).")

    lote = Lotes(id_medicamento=id_medicamento, codigo_lote=codigo_lote, fecha_vencimiento=fecha_vencimiento,
                 unidades_ingresadas=unidades, unidades_disp=0, id_ubicacion=id_ubicacion,
                 proveedor=(proveedor or "").strip() or None, tipo_documento=tipo_documento,
                 numero_documento=(numero_documento or "").strip() or None, fecha_documento=fecha_documento,
                 costo_total=costo_total, creado_por=usuario.id_usuario)
    db.add(lote)
    db.flush()
    mover_stock(db, lote, tipo=tipo_movimiento, cantidad=unidades, usuario=usuario, motivo=motivo,
                referencia_tipo=referencia_tipo, referencia_id=referencia_id)
    if medicamento.es_controlado:
        asiento_de_lote(db, tipo="INGRESO", lote=lote, cantidad=unidades, qf=usuario, proveedor=lote.proveedor,
                        documento=f"{TIPOS_DOCUMENTO[tipo_documento]} N.º {lote.numero_documento}",
                        fecha_documento=fecha_documento.isoformat())

    alertas = []
    if vencimiento_corto_en_recepcion(fecha_vencimiento, hoy):
        alertas.append(f"Vence en {dias_para_vencer(fecha_vencimiento, hoy)} días (menos de 6 meses).")
    if not es_dispensable(estado_lote(fecha_vencimiento, unidades, hoy)):
        alertas.append("El lote no es dispensable por su fecha de vencimiento (RN-02).")
    registrar_evento(db, tipo="LOTE_INGRESADO", entidad="lotes", id_entidad=lote.id_lote,
                     id_usuario=usuario.id_usuario, codigo_lote=codigo_lote, unidades=unidades, alertas=alertas)
    return lote, alertas


def ajustar_lote(db: Session, usuario: Usuarios, id_lote: int, unidades_correctas: int, motivo: str) -> Lotes:
    """Corrige una cantidad mal ingresada sin borrar nada: queda un movimiento AJUSTE."""
    motivo = exigir_motivo(motivo)
    lote = obtener_lote(db, id_lote)
    if lote.estado != EstadosRegistroLote.DISPONIBLE:
        raise ReglaNegocioError("LOTE_NO_EDITABLE", f"El lote está {lote.estado} y no admite ajustes.")
    if lote.medicamento.es_controlado:
        exigir_qf(usuario, "ajustar el stock de un controlado")
    diferencia = unidades_correctas - lote.unidades_disp
    if diferencia == 0:
        raise ReglaNegocioError("SIN_CAMBIOS", "La cantidad indicada es igual al stock actual.")
    mover_stock(db, lote, tipo="AJUSTE", cantidad=diferencia, usuario=usuario, motivo=motivo)
    if lote.medicamento.es_controlado:
        asiento_de_lote(db, tipo="AJUSTE", lote=lote, cantidad=diferencia, qf=usuario, motivo=motivo)
    registrar_evento(db, tipo="LOTE_AJUSTADO", entidad="lotes", id_entidad=lote.id_lote,
                     id_usuario=usuario.id_usuario, diferencia=diferencia, motivo=motivo)
    return lote


def anular_lote(db: Session, usuario: Usuarios, id_lote: int, motivo: str) -> Lotes:
    """Da de baja un lote mal ingresado. Solo si nunca se dispensó: si ya se usó, se corrige con ajuste o merma."""
    motivo = exigir_motivo(motivo)
    lote = obtener_lote(db, id_lote)
    if lote.estado != EstadosRegistroLote.DISPONIBLE:
        raise ReglaNegocioError("LOTE_NO_EDITABLE", f"El lote ya está {lote.estado}.")
    con_salidas = db.scalar(select(MovimientosStock.id_movimiento).where(
        MovimientosStock.id_lote == id_lote,
        MovimientosStock.tipo.in_(["DISPENSACION", "MERMA"])).limit(1))
    if con_salidas:
        raise ReglaNegocioError("LOTE_CON_MOVIMIENTOS",
                                "El lote ya tiene dispensaciones o mermas; corrija con un ajuste o una merma.")
    if lote.medicamento.es_controlado:
        exigir_qf(usuario, "anular un lote de controlado")
    if lote.unidades_disp > 0:
        cantidad = lote.unidades_disp
        mover_stock(db, lote, tipo="ANULACION_LOTE", cantidad=-cantidad, usuario=usuario, motivo=motivo)
        if lote.medicamento.es_controlado:
            asiento_de_lote(db, tipo="AJUSTE", lote=lote, cantidad=-cantidad, qf=usuario,
                            motivo=f"Anulación del lote: {motivo}")
    lote.estado = EstadosRegistroLote.ANULADO
    lote.fecha_anulacion, lote.anulado_por, lote.motivo_anulacion = ahora(), usuario.id_usuario, motivo
    registrar_evento(db, tipo="LOTE_ANULADO", entidad="lotes", id_entidad=lote.id_lote,
                     id_usuario=usuario.id_usuario, motivo=motivo)
    return lote


def registrar_merma(db: Session, usuario: Usuarios, id_lote: int, cantidad: int, motivo: str,
                    observacion: str | None = None) -> Mermas:
    if motivo not in MOTIVOS_MERMA:
        raise ReglaNegocioError("MOTIVO_INVALIDO", f"El motivo debe ser uno de: {', '.join(sorted(MOTIVOS_MERMA))}.")
    lote = obtener_lote(db, id_lote)
    if lote.estado not in (EstadosRegistroLote.DISPONIBLE, EstadosRegistroLote.ALERTA_SANITARIA):
        raise ReglaNegocioError("LOTE_NO_EDITABLE", f"El lote está {lote.estado}.")
    if cantidad <= 0 or cantidad > lote.unidades_disp:
        raise ReglaNegocioError("CANTIDAD_INVALIDA", f"La cantidad debe estar entre 1 y {lote.unidades_disp}.")
    if lote.medicamento.es_controlado:
        exigir_qf(usuario, "registrar la merma de un controlado")
    merma = Mermas(id_lote=id_lote, id_usuario=usuario.id_usuario, cantidad=cantidad, motivo=motivo,
                   observacion=observacion, creado_por=usuario.id_usuario)
    db.add(merma)
    db.flush()
    mover_stock(db, lote, tipo="MERMA", cantidad=-cantidad, usuario=usuario, motivo=motivo,
                referencia_tipo="mermas", referencia_id=merma.id_merma)
    if lote.medicamento.es_controlado:
        asiento_de_lote(db, tipo="MERMA", lote=lote, cantidad=cantidad, qf=usuario,
                        motivo=motivo + (f": {observacion}" if observacion else ""))
    if lote.unidades_disp == 0:
        lote.estado = EstadosRegistroLote.MERMA
    registrar_evento(db, tipo="MERMA_REGISTRADA", entidad="lotes", id_entidad=id_lote,
                     id_usuario=usuario.id_usuario, cantidad=cantidad, motivo=motivo)
    return merma


def describir_lote(lote: Lotes, hoy: date) -> dict:
    estado = estado_lote(lote.fecha_vencimiento, lote.unidades_disp, hoy, lote.estado)
    return {
        "id_lote": lote.id_lote, "codigo_lote": lote.codigo_lote,
        "id_medicamento": lote.id_medicamento, "medicamento": lote.medicamento.nombre,
        "fecha_vencimiento": lote.fecha_vencimiento.isoformat(),
        "dias_para_vencer": dias_para_vencer(lote.fecha_vencimiento, hoy),
        "unidades_ingresadas": lote.unidades_ingresadas, "unidades_disp": lote.unidades_disp,
        "ubicacion": lote.ubicacion.codigo, "estado": estado.value, "dispensable": es_dispensable(estado),
        "motivo_anulacion": lote.motivo_anulacion, "es_controlado": lote.medicamento.es_controlado,
        "proveedor": lote.proveedor, "tipo_documento": lote.tipo_documento, "numero_documento": lote.numero_documento,
        "fecha_documento": lote.fecha_documento.isoformat() if lote.fecha_documento else None,
        "costo_total": lote.costo_total,
        "costo_unitario": round(costo_unitario(lote), 2) if lote.costo_total is not None else None,
    }


def panel_stock(db: Session, hoy: date) -> list[dict]:
    """HU-05: stock dispensable por medicamento y programa, con alerta de quiebre.

    Lee todos los lotes con stock en una sola consulta (antes era una por medicamento).
    """
    medicamentos = db.scalars(select(Medicamentos).where(Medicamentos.activo.is_(True))
                              .order_by(Medicamentos.nombre)).all()
    lotes_por_medicamento: dict[int, list[Lotes]] = {}
    for lote in db.scalars(select(Lotes).where(Lotes.unidades_disp > 0)).unique():
        lotes_por_medicamento.setdefault(lote.id_medicamento, []).append(lote)
    filas = []
    for med in medicamentos:
        por_estado: dict[str, int] = {}
        dispensable = 0
        for lote in lotes_por_medicamento.get(med.id_medicamento, []):
            estado = estado_lote(lote.fecha_vencimiento, lote.unidades_disp, hoy, lote.estado)
            por_estado[estado.value] = por_estado.get(estado.value, 0) + lote.unidades_disp
            if es_dispensable(estado):
                dispensable += lote.unidades_disp
        filas.append({
            "id_medicamento": med.id_medicamento, "codigo": med.codigo, "nombre": med.nombre,
            "principio_activo": med.principio_activo, "concentracion": med.concentracion,
            "forma_farmaceutica": med.forma_farmaceutica, "unidad_dispensacion": med.unidad_dispensacion,
            "programa": med.programa.nombre if med.programa else None, "es_controlado": med.es_controlado,
            "es_ges": med.es_ges, "stock_dispensable": dispensable, "umbral_critico": med.umbral_critico,
            "critico": dispensable < med.umbral_critico, "unidades_por_estado": por_estado,
        })
    return filas


ESTADOS_CON_ALERTA = ("ALERTA", "NO_DISPENSABLE", "RETIRO_OBLIGATORIO", "ALERTA_SANITARIA")


def alertas_inventario(db: Session, hoy: date) -> dict:
    """Lotes que vencen pronto o están bloqueados, y medicamentos bajo su umbral crítico."""
    lotes = db.scalars(select(Lotes).where(Lotes.unidades_disp > 0,
                                           Lotes.estado.in_(["DISPONIBLE", "ALERTA_SANITARIA"]))
                       .order_by(Lotes.fecha_vencimiento, Lotes.id_lote)).unique()
    vencimientos = [d for d in (describir_lote(l, hoy) for l in lotes) if d["estado"] in ESTADOS_CON_ALERTA]
    criticos = [{**f, "deficit": f["umbral_critico"] - f["stock_dispensable"]} for f in panel_stock(db, hoy)
                if f["critico"]]
    resumen = {estado: sum(1 for v in vencimientos if v["estado"] == estado) for estado in ESTADOS_CON_ALERTA}
    return {"vencimientos": vencimientos, "stock_critico": sorted(criticos, key=lambda f: -f["deficit"]),
            "resumen": {**resumen, "STOCK_CRITICO": len(criticos)}}


def disponibilidad_publica(db: Session, hoy: date, texto: str | None = None) -> list[dict]:
    """Consulta pública: solo disponible / pocas unidades / sin stock, nunca cantidades.

    Los medicamentos controlados no se publican (riesgo de robo y desvío).
    """
    texto = (texto or "").strip().lower()
    filas = []
    for f in panel_stock(db, hoy):
        if f["es_controlado"]:
            continue
        if texto and texto not in f["nombre"].lower() and texto not in (f["principio_activo"] or "").lower():
            continue
        if f["stock_dispensable"] == 0:
            disponibilidad = "SIN_STOCK"
        elif f["stock_dispensable"] < f["umbral_critico"]:
            disponibilidad = "POCAS_UNIDADES"
        else:
            disponibilidad = "DISPONIBLE"
        filas.append({"nombre": f["nombre"], "principio_activo": f["principio_activo"],
                      "concentracion": f["concentracion"], "forma_farmaceutica": f["forma_farmaceutica"],
                      "programa": f["programa"], "es_ges": f["es_ges"], "disponibilidad": disponibilidad})
    return filas
