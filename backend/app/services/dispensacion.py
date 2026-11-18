"""Casos de uso de dispensación (HU-01, HU-02, HU-04) y su anulación.

Toda la operación es atómica: si cualquier línea falla (FEFO, stock, firma
del Q.F.) no se descuenta nada, porque la sesión se revierte completa.

Reglas de la v0.5 (docs/PLAN_v0.5.md, sección 2.2):
  * Cada visita corresponde a la entrega en curso ("Entrega X de Y"): no se
    pueden llevar unidades de la entrega siguiente.
  * Una entrega nueva no se retira más de 5 días antes de su fecha; completar
    una entrega que quedó parcial se permite siempre.
  * Quién retira: el paciente, un apoderado registrado y vigente, o un tercero
    con RUT y relación. En controlados, quien retira siempre se identifica.
  * Si el paciente tiene alergias registradas, hay que confirmarlas.
  * Pacientes postrados: la entrega puede salir como despacho a domicilio
    (nunca un controlado, que exige retiro presencial con firma).

FOFAR (v0.6): cada atención queda como solicitud de despacho; lo que no se
entrega por quiebre de stock genera un compromiso de 24 horas hábiles
(services/faltantes.py).
"""

from dataclasses import dataclass, field
from datetime import UTC, date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain import fefo
from ..domain.errores import ReglaNegocioError
from ..domain.libro import AsientoVerificable, verificar_cadena
from ..domain.recetas import (LineaEntrega, entrega_en_curso_iniciada, entregas_completas, exigir_fecha_de_retiro,
                              exigir_receta_vigente, generar_rotulo, pendiente, proxima_fecha_retiro,
                              saldo_entrega_actual)
from ..domain.rut import enmascarar_rut, normalizar_rut
from ..models import (Apoderados, AsientosControlados, DespachosDomicilio, DetallesDispensacion, DetallesReceta,
                      Devoluciones, Dispensaciones, Lotes, Recetas, Usuarios)
from ..reloj import ahora, iso_utc
from ..repositories.lotes import a_lote_fefo, lotes_de_medicamento
from ..security.claves import hmac_rut, verificar
from . import faltantes as servicio_faltantes
from .auditoria import registrar_evento
from .inventario import exigir_motivo, mover_stock, obtener_lote
from .libro import registrar_asiento


@dataclass
class LineaDispensacion:
    id_detalle_receta: int
    cantidad: int
    lotes_escaneados: list[str] = field(default_factory=list)


@dataclass
class FirmaQF:
    rut: str
    pin: str


# ----------------------------------------------------------------- consultas
def obtener_detalle(db: Session, id_detalle_receta: int) -> DetallesReceta:
    detalle = db.get(DetallesReceta, id_detalle_receta)
    if detalle is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La línea de receta no existe.")
    return detalle


def planificar_linea(db: Session, id_detalle_receta: int, cantidad: int, hoy: date) -> list[dict]:
    """Muestra al técnico qué lote y casillero debe tomar antes de escanear."""
    detalle = obtener_detalle(db, id_detalle_receta)
    lotes = [a_lote_fefo(l) for l in lotes_de_medicamento(db, detalle.id_medicamento)]
    plan = fefo.planificar(lotes, detalle.id_medicamento, cantidad, hoy)
    return [{"codigo_lote": a.lote.codigo_lote, "ubicacion": a.lote.ubicacion, "cantidad": a.cantidad,
             "fecha_vencimiento": a.lote.fecha_vencimiento.isoformat()} for a in plan]


# ----------------------------------------------------------------- auxiliares
def _fecha_local(momento) -> date:
    if momento.tzinfo is None:  # SQLite no guarda la zona horaria: el valor está en UTC
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone().date()


def _recalcular_estado_receta(db: Session, receta: Recetas) -> None:
    """Estado, entregas completas ("Entrega X de Y") y próxima fecha de retiro."""
    entregado = [d.cant_entregada for d in receta.detalles]
    if all(c == 0 for c in entregado):
        receta.estado = "PENDIENTE"
    elif all(d.cant_entregada == d.cant_prescrita for d in receta.detalles):
        receta.estado = "DISPENSADA"
    else:
        receta.estado = "PARCIAL"
    receta.entregas_realizadas = min(receta.total_entregas, entregas_completas(
        [(d.cant_entregada, d.cant_por_entrega) for d in receta.detalles]))
    ultima = db.scalar(select(func.max(Dispensaciones.fecha_hora)).where(
        Dispensaciones.id_receta == receta.id_receta, Dispensaciones.estado == "VIGENTE"))
    receta.proxima_fecha_retiro = proxima_fecha_retiro(
        fecha_emision=receta.fecha_emision, total_entregas=receta.total_entregas,
        entregas_realizadas=receta.entregas_realizadas,
        fecha_ultima_entrega=_fecha_local(ultima) if ultima else None, intervalo_dias=receta.intervalo_dias)


def _validar_firma_qf(db: Session, firma: FirmaQF | None) -> Usuarios:
    if firma is None:
        raise ReglaNegocioError("FIRMA_QF_REQUERIDA", "Los medicamentos controlados requieren la firma del Q.F.")
    try:
        rut = normalizar_rut(firma.rut)
    except ReglaNegocioError:
        raise ReglaNegocioError("FIRMA_QF_INVALIDA", "RUT o PIN del Q.F. incorrectos.") from None
    qf = db.scalar(select(Usuarios).where(Usuarios.rut == rut))
    if qf is None or not qf.activo or qf.rol.nombre != "QF" or not verificar(firma.pin, qf.pin_hash):
        raise ReglaNegocioError("FIRMA_QF_INVALIDA", "RUT o PIN del Q.F. incorrectos.")
    return qf


def _resumen(disp: Dispensaciones, rotulos: list[dict], repetida: bool = False, id_despacho: int | None = None,
             faltantes: list[dict] | None = None, resultado: str | None = None) -> dict:
    return {"id_dispensacion": disp.id_dispensacion, "folio": disp.receta.folio, "estado": disp.estado,
            "estado_receta": disp.receta.estado, "numero_entrega": disp.numero_entrega,
            "total_entregas": disp.receta.total_entregas, "entregas_realizadas": disp.receta.entregas_realizadas,
            "proxima_fecha_retiro": disp.receta.proxima_fecha_retiro.isoformat()
            if disp.receta.proxima_fecha_retiro else None,
            "id_despacho": id_despacho, "rotulos": rotulos, "repetida": repetida,
            "resultado": resultado, "faltantes": faltantes or []}


def _linea(detalle: DetallesReceta) -> LineaEntrega:
    return LineaEntrega(cant_prescrita=detalle.cant_prescrita, cant_por_entrega=detalle.cant_por_entrega,
                        cant_entregada=detalle.cant_entregada)


@dataclass
class Retiro:
    tipo: str
    id_apoderado: int | None = None
    rut_hmac: str | None = None
    rut_enmascarado: str | None = None
    relacion: str | None = None


def _resolver_retiro(db: Session, receta: Recetas, *, tipo: str | None, id_apoderado: int | None,
                     rut_retira: str | None, relacion: str | None, hay_controlados: bool, hoy: date) -> Retiro:
    """Quién retira: el paciente, un apoderado registrado o un tercero identificado."""
    tipo = tipo or ("TERCERO" if rut_retira or hay_controlados else "PACIENTE")
    paciente = receta.paciente
    if tipo == "APODERADO":
        if id_apoderado is None:
            raise ReglaNegocioError("APODERADO_REQUERIDO", "Seleccione el apoderado que retira.")
        apoderado = db.get(Apoderados, id_apoderado)
        if (apoderado is None or apoderado.id_paciente != paciente.id_paciente or not apoderado.activo
                or (apoderado.vigente_hasta is not None and apoderado.vigente_hasta < hoy)):
            raise ReglaNegocioError("APODERADO_INVALIDO",
                                    "El apoderado no está registrado y vigente para este paciente.")
        return Retiro("APODERADO", apoderado.id_apoderado, apoderado.rut_hmac, apoderado.rut_enmascarado,
                      apoderado.parentesco)
    if tipo == "TERCERO":
        rut = normalizar_rut(rut_retira or "")
        if not (relacion or "").strip():
            raise ReglaNegocioError("RELACION_REQUERIDA", "Indique la relación de quien retira con el paciente.")
        return Retiro("TERCERO", None, hmac_rut(rut), enmascarar_rut(rut), relacion.strip())
    if tipo != "PACIENTE":
        raise ReglaNegocioError("RETIRO_INVALIDO", "Quien retira debe ser el paciente, un apoderado o un tercero.")
    if not rut_retira:
        if hay_controlados:
            raise ReglaNegocioError("IDENTIFICACION_REQUERIDA",
                                    "En un controlado se registra el RUT de quien retira, aunque sea el paciente.")
        return Retiro("PACIENTE")
    rut = normalizar_rut(rut_retira)
    if hmac_rut(rut) != paciente.rut_hmac:
        raise ReglaNegocioError("RUT_NO_COINCIDE", "El RUT indicado no es el del paciente.")
    return Retiro("PACIENTE", None, paciente.rut_hmac, paciente.rut_enmascarado, "Titular")


# ----------------------------------------------------------------- dispensar
def dispensar(db: Session, usuario: Usuarios, *, id_receta: int, lineas: list[LineaDispensacion],
              clave_idempotencia: str, hoy: date, rut_retira: str | None = None, relacion: str | None = None,
              firma_qf: FirmaQF | None = None, retira_tipo: str | None = None, id_apoderado: int | None = None,
              confirma_alergias: bool = False, a_domicilio: bool = False,
              motivos_incompletos: dict[int, str] | None = None) -> dict:
    previa = db.scalar(select(Dispensaciones).where(Dispensaciones.clave_idempotencia == clave_idempotencia))
    if previa is not None:  # reintento por red intermitente: no se descuenta dos veces
        if previa.id_receta != id_receta:
            raise ReglaNegocioError("IDEMPOTENCIA", "La clave de idempotencia ya se usó en otra receta.")
        return _resumen(previa, [], repetida=True)

    receta = db.get(Recetas, id_receta, with_for_update=True)
    if receta is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La receta no existe.")
    if receta.estado in ("ANULADA", "DISPENSADA"):
        raise ReglaNegocioError("RECETA_CERRADA", f"La receta está {receta.estado}.")
    exigir_receta_vigente(receta.fecha_emision, hoy, receta.tipo_receta, receta.entregas_realizadas)
    exigir_fecha_de_retiro(receta.proxima_fecha_retiro, hoy,
                           entrega_en_curso_iniciada([_linea(d) for d in receta.detalles], receta.entregas_realizadas))
    if receta.paciente.alergias and not confirma_alergias:
        raise ReglaNegocioError("ALERGIAS_SIN_CONFIRMAR",
                                f"El paciente tiene alergias registradas ({receta.paciente.alergias}). "
                                "Confírmelas antes de entregar.")

    if not lineas:
        raise ReglaNegocioError("SIN_LINEAS", "Debe indicar al menos un medicamento a entregar.")
    detalles = {d.id_detalle_receta: d for d in receta.detalles}
    if len({l.id_detalle_receta for l in lineas}) != len(lineas):
        raise ReglaNegocioError("LINEA_REPETIDA", "Una línea de la receta aparece dos veces.")
    for linea in lineas:
        detalle = detalles.get(linea.id_detalle_receta)
        if detalle is None:
            raise ReglaNegocioError("LINEA_AJENA", "La línea indicada no pertenece a esta receta.")
        falta = pendiente(detalle.cant_prescrita, detalle.cant_entregada)
        saldo = saldo_entrega_actual(_linea(detalle), receta.entregas_realizadas)
        if linea.cantidad > saldo:
            if saldo == falta:
                raise ReglaNegocioError("CANTIDAD_EXCEDE",
                                        f"Para {detalle.medicamento.nombre} quedan {falta} por entregar.")
            raise ReglaNegocioError("CANTIDAD_EXCEDE",
                                    f"En la entrega {receta.entregas_realizadas + 1} de {receta.total_entregas} "
                                    f"corresponden {detalle.cant_por_entrega} de {detalle.medicamento.nombre}; "
                                    f"quedan {saldo}. La siguiente entrega se retira en su fecha.")
        if not detalle.medicamento.activo:
            raise ReglaNegocioError("MEDICAMENTO_INACTIVO", f"{detalle.medicamento.nombre} está dado de baja.")

    hay_controlados = any(detalles[l.id_detalle_receta].medicamento.es_controlado for l in lineas)
    qf = None
    if hay_controlados and not receta.es_retenida:
        raise ReglaNegocioError("RECETA_NO_RETENIDA", "Un controlado exige receta retenida.")
    if a_domicilio:
        if hay_controlados:
            raise ReglaNegocioError("CONTROLADO_PRESENCIAL",
                                    "Un medicamento controlado se entrega en farmacia, con firma del Q.F.")
        if not receta.paciente.es_postrado:
            raise ReglaNegocioError("DOMICILIO_SOLO_POSTRADO", "El despacho a domicilio es para pacientes postrados.")
        if not receta.paciente.direccion:
            raise ReglaNegocioError("DIRECCION_REQUERIDA", "El paciente no tiene dirección registrada para el despacho.")
        if retira_tipo not in (None, "PACIENTE"):
            raise ReglaNegocioError("RETIRO_INVALIDO", "En un despacho a domicilio recibe el paciente o su cuidador.")
    retiro = _resolver_retiro(db, receta, tipo=retira_tipo, id_apoderado=id_apoderado, rut_retira=rut_retira,
                              relacion=relacion, hay_controlados=hay_controlados, hoy=hoy)
    if hay_controlados:
        qf = _validar_firma_qf(db, firma_qf)
    solicitadas = servicio_faltantes.lineas_solicitadas(db, receta, hoy)  # antes de descontar: lo que había

    disp = Dispensaciones(id_receta=receta.id_receta, id_usuario=usuario.id_usuario,
                          id_usuario_autoriza=qf.id_usuario if qf else None,
                          rut_retira_hmac=retiro.rut_hmac, rut_retira_enmascarado=retiro.rut_enmascarado,
                          relacion=retiro.relacion, retira_tipo=retiro.tipo, id_apoderado=retiro.id_apoderado,
                          numero_entrega=min(receta.entregas_realizadas + 1, receta.total_entregas),
                          clave_idempotencia=clave_idempotencia, creado_por=usuario.id_usuario)
    disp.receta = receta
    db.add(disp)
    db.flush()
    despacho = None
    if a_domicilio:
        despacho = DespachosDomicilio(id_dispensacion=disp.id_dispensacion, estado="PREPARANDO",
                                      creado_por=usuario.id_usuario)
        db.add(despacho)
        db.flush()

    rotulos = []
    for linea in lineas:
        detalle = detalles[linea.id_detalle_receta]
        med = detalle.medicamento
        lotes_orm = {l.codigo_lote: l for l in lotes_de_medicamento(db, med.id_medicamento, bloquear=True)}
        lotes = [a_lote_fefo(l) for l in lotes_orm.values()]
        plan = fefo.planificar(lotes, med.id_medicamento, linea.cantidad, hoy)

        # RN-06: cada lote escaneado debe estar en el plan. Si es de otro medicamento se busca
        # para dar un mensaje preciso ("es de otro medicamento" en vez de "no existe").
        ajenos = [c for c in linea.lotes_escaneados if c not in lotes_orm]
        referencia = lotes + [a_lote_fefo(l) for l in db.scalars(
            select(Lotes).where(Lotes.codigo_lote.in_(ajenos))).unique()] if ajenos else lotes
        for codigo in linea.lotes_escaneados:
            fefo.validar_lote_escaneado(referencia, med.id_medicamento, codigo, plan, hoy)
        faltantes = [a.lote.codigo_lote for a in plan if a.lote.codigo_lote not in linea.lotes_escaneados]
        if faltantes:
            raise ReglaNegocioError("ESCANEO_INCOMPLETO",
                                    f"Falta escanear el lote {faltantes[0]} ({plan[0].lote.ubicacion}).")

        for asignacion in plan:
            lote = lotes_orm[asignacion.lote.codigo_lote]
            detalle_disp = DetallesDispensacion(id_dispensacion=disp.id_dispensacion,
                                                id_detalle_receta=detalle.id_detalle_receta, id_lote=lote.id_lote,
                                                cantidad=asignacion.cantidad, creado_por=usuario.id_usuario)
            db.add(detalle_disp)
            db.flush()
            mover_stock(db, lote, tipo="DISPENSACION", cantidad=-asignacion.cantidad, usuario=usuario,
                        referencia_tipo="dispensaciones", referencia_id=disp.id_dispensacion)
            if med.es_controlado:
                registrar_asiento(db, tipo="SALIDA", detalle=detalle_disp, qf=qf, contenido={
                    "folio": receta.folio, "receta_cheque": receta.numero_receta_cheque,
                    "prescriptor": receta.prescriptor_nombre, "rut_prescriptor": receta.prescriptor_rut,
                    "paciente": receta.paciente.nombre, "domicilio": receta.domicilio_paciente,
                    "medicamento": med.codigo, "nombre": med.nombre, "lote": lote.codigo_lote,
                    "cantidad": asignacion.cantidad, "rut_retira": disp.rut_retira_enmascarado,
                    "relacion": disp.relacion})
            rotulos.append(generar_rotulo(
                medicamento=med.nombre, codigo_lote=lote.codigo_lote, fecha_vencimiento=lote.fecha_vencimiento,
                cantidad=asignacion.cantidad, posologia=detalle.posologia, paciente=receta.paciente.nombre,
                programa=med.programa.nombre if med.programa else None,
                entrega=f"{disp.numero_entrega} de {receta.total_entregas}" if receta.total_entregas > 1 else None))
        detalle.cant_entregada += linea.cantidad

    db.flush()
    servicio_faltantes.resolver_con_entrega(db, receta, disp)
    solicitud, faltantes = servicio_faltantes.registrar_solicitud(
        db, usuario, receta=receta, numero_entrega=disp.numero_entrega, solicitadas=solicitadas,
        entregadas={l.id_detalle_receta: l.cantidad for l in lineas}, motivos=motivos_incompletos,
        id_dispensacion=disp.id_dispensacion)
    _recalcular_estado_receta(db, receta)
    registrar_evento(db, tipo="DISPENSACION", entidad="dispensaciones", id_entidad=disp.id_dispensacion,
                     id_usuario=usuario.id_usuario, folio=receta.folio, controlado=hay_controlados,
                     numero_entrega=disp.numero_entrega, retira=disp.retira_tipo, a_domicilio=a_domicilio,
                     resultado=solicitud.resultado,
                     lineas=[{"id_detalle_receta": l.id_detalle_receta, "cantidad": l.cantidad} for l in lineas])
    momento = ahora()
    return _resumen(disp, rotulos, id_despacho=despacho.id_despacho if despacho else None,
                    resultado=solicitud.resultado,
                    faltantes=[servicio_faltantes.describir_faltante(f, momento) for f in faltantes])


def rotulos_de(db: Session, id_dispensacion: int) -> dict:
    disp = db.get(Dispensaciones, id_dispensacion)
    if disp is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La dispensación no existe.")
    receta = disp.receta
    entrega = f"{disp.numero_entrega} de {receta.total_entregas}" if receta.total_entregas > 1 else None
    return {"id_dispensacion": disp.id_dispensacion, "folio": receta.folio, "estado": disp.estado,
            "rotulos": [generar_rotulo(medicamento=x.lote.medicamento.nombre, codigo_lote=x.lote.codigo_lote,
                                       fecha_vencimiento=x.lote.fecha_vencimiento, cantidad=x.cantidad,
                                       posologia=x.detalle_receta.posologia, paciente=receta.paciente.nombre,
                                       programa=x.lote.medicamento.programa.nombre if x.lote.medicamento.programa else None,
                                       entrega=entrega) for x in disp.detalles]}


# ------------------------------------------------------------------- anular
def anular_dispensacion(db: Session, usuario: Usuarios, id_dispensacion: int, motivo: str) -> dict:
    """Anula una entrega mal registrada: repone el stock, libera la receta y rectifica el libro."""
    motivo = exigir_motivo(motivo)
    disp = db.get(Dispensaciones, id_dispensacion, with_for_update=True)
    if disp is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La dispensación no existe.")
    if disp.estado == "ANULADA":
        raise ReglaNegocioError("YA_ANULADA", "La dispensación ya fue anulada.")
    if db.scalar(select(Devoluciones.id_devolucion).join(DetallesDispensacion).where(
            DetallesDispensacion.id_dispensacion == disp.id_dispensacion).limit(1)):
        raise ReglaNegocioError("TIENE_DEVOLUCIONES", "La entrega tiene devoluciones registradas; no se puede anular.")
    despacho = db.scalar(select(DespachosDomicilio).where(DespachosDomicilio.id_dispensacion == disp.id_dispensacion))
    if despacho is not None and despacho.estado in ("EN_RUTA", "ENTREGADO"):
        raise ReglaNegocioError("DESPACHO_EN_CURSO", f"El despacho a domicilio está {despacho.estado.replace('_', ' ')}; "
                                "si el paciente lo recibió, registre una devolución.")
    if despacho is not None:
        despacho.estado, despacho.observacion = "FALLIDO", f"Dispensación anulada: {motivo}"[:250]
        despacho.actualizado_por = usuario.id_usuario

    for detalle in disp.detalles:
        lote = obtener_lote(db, detalle.id_lote)
        if lote.estado != "DISPONIBLE":
            raise ReglaNegocioError("LOTE_NO_EDITABLE",
                                    f"El lote {lote.codigo_lote} está {lote.estado}; registre la devolución aparte.")
        mover_stock(db, lote, tipo="ANULACION_DISPENSACION", cantidad=detalle.cantidad, usuario=usuario,
                    motivo=motivo, referencia_tipo="dispensaciones", referencia_id=disp.id_dispensacion)
        detalle.detalle_receta.cant_entregada -= detalle.cantidad
        original = db.scalar(select(AsientosControlados).where(
            AsientosControlados.id_detalle_disp == detalle.id_detalle_disp, AsientosControlados.tipo == "SALIDA"))
        if original is not None:
            registrar_asiento(db, tipo="RECTIFICACION", detalle=detalle, qf=usuario,
                              id_asiento_origen=original.id_asiento,
                              contenido={"anula_asiento": original.nro_asiento, "motivo": motivo,
                                         "medicamento": detalle.lote.medicamento.codigo,
                                         "nombre": detalle.lote.medicamento.nombre, "lote": detalle.lote.codigo_lote,
                                         "cantidad": detalle.cantidad, "cantidad_repuesta": detalle.cantidad})

    servicio_faltantes.anular_por_dispensacion(db, disp)
    disp.estado = "ANULADA"
    disp.fecha_anulacion, disp.anulada_por, disp.motivo_anulacion = ahora(), usuario.id_usuario, motivo
    disp.actualizado_por = usuario.id_usuario
    db.flush()
    _recalcular_estado_receta(db, disp.receta)
    registrar_evento(db, tipo="DISPENSACION_ANULADA", entidad="dispensaciones", id_entidad=disp.id_dispensacion,
                     id_usuario=usuario.id_usuario, motivo=motivo)
    return {"id_dispensacion": disp.id_dispensacion, "estado": disp.estado, "estado_receta": disp.receta.estado}


# ------------------------------------------------------------ libro digital
def listar_libro(db: Session) -> list[dict]:
    asientos = db.scalars(select(AsientosControlados).order_by(AsientosControlados.nro_asiento)).all()
    return [{"nro_asiento": a.nro_asiento, "tipo": a.tipo, "fecha_hora": iso_utc(a.fecha_hora),
             "contenido": a.contenido, "saldo": a.contenido.get("saldo"), "hash_actual": a.hash_actual}
            for a in asientos]


def verificar_libro(db: Session) -> dict:
    asientos = db.scalars(select(AsientosControlados)).all()
    integra, nro = verificar_cadena([AsientoVerificable(a.nro_asiento, a.contenido, a.hash_previo, a.hash_actual)
                                     for a in asientos])
    return {"integra": integra, "asientos_verificados": len(asientos), "primer_asiento_alterado": nro}
