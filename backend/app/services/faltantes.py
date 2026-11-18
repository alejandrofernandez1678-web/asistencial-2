"""Faltantes, compromisos de entrega y reclamos (Programa Fondo de Farmacia, FOFAR).

Indicador FOFAR N.º 1: recetas con despacho total y oportuno = la entrega completa
el mismo día en que se pide en ventanilla. Por eso cada atención queda como una
"solicitud de despacho" con su resultado:
  * COMPLETA: se entregó todo lo que correspondía.
  * SIN_STOCK: algo faltó por quiebre de stock. Se crea un compromiso de entrega
    (faltante PENDIENTE) con plazo de 24 horas hábiles.
  * RECHAZO: el paciente no quiso llevar parte de la entrega (no es incumplimiento
    de la farmacia; el FOFAR lo informa aparte como "rechazo del paciente").
Si no se indica el motivo de lo que falta, se deduce: si el stock dispensable no
alcanzaba, es SIN_STOCK; si alcanzaba, es RECHAZO_PACIENTE.

Indicador FOFAR N.º 2: reclamos con solución (entrega del fármaco) dentro de 24
horas hábiles. El reclamo se cierra con el acta de recepción firmada.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.horas_habiles import horas_habiles_entre, sumar_horas_habiles
from ..domain.lotes import es_dispensable, estado_lote
from ..domain.recetas import (LineaEntrega, entrega_en_curso_iniciada, exigir_fecha_de_retiro, exigir_receta_vigente,
                              saldo_entrega_actual)
from ..domain.rut import normalizar_rut
from ..models import (DetallesReceta, Dispensaciones, Faltantes, Pacientes, Reclamos, Recetas, SolicitudesDespacho,
                      Usuarios)
from ..reloj import ahora
from ..repositories.lotes import lotes_de_medicamento
from ..security.claves import hmac_rut
from .auditoria import registrar_evento
from .inventario import exigir_motivo

MOTIVOS_FALTANTE = ("SIN_STOCK", "RECHAZO_PACIENTE")
CANALES_RECLAMO = {"OIRS": "OIRS", "SALUD_RESPONDE": "Salud Responde", "PRESENCIAL": "Presencial en farmacia"}


# ----------------------------------------------------------------- auxiliares
def _utc(momento: datetime) -> datetime:
    return momento.replace(tzinfo=UTC) if momento.tzinfo is None else momento  # SQLite devuelve fechas sin zona


def plazo_fofar(desde: datetime) -> datetime:
    """24 horas hábiles contadas en la hora local del CESFAM."""
    return sumar_horas_habiles(_utc(desde).astimezone()).astimezone(UTC)


def stock_dispensable(db: Session, id_medicamento: int, hoy: date) -> int:
    return sum(l.unidades_disp for l in lotes_de_medicamento(db, id_medicamento)
               if es_dispensable(estado_lote(l.fecha_vencimiento, l.unidades_disp, hoy, l.estado)))


def _linea(d: DetallesReceta) -> LineaEntrega:
    return LineaEntrega(cant_prescrita=d.cant_prescrita, cant_por_entrega=d.cant_por_entrega,
                        cant_entregada=d.cant_entregada)


@dataclass
class LineaSolicitada:
    detalle: DetallesReceta
    corresponde: int     # saldo de la entrega en curso al momento de pedirla
    stock: int           # stock dispensable en ese momento


def lineas_solicitadas(db: Session, receta: Recetas, hoy: date) -> list[LineaSolicitada]:
    """Lo que el paciente viene a buscar: el saldo de la entrega en curso de cada línea."""
    lineas = []
    for d in receta.detalles:
        saldo = saldo_entrega_actual(_linea(d), receta.entregas_realizadas)
        if saldo > 0:
            lineas.append(LineaSolicitada(d, saldo, stock_dispensable(db, d.id_medicamento, hoy)))
    return lineas


# ------------------------------------------------------- solicitudes y faltantes
def registrar_solicitud(db: Session, usuario: Usuarios, *, receta: Recetas, numero_entrega: int,
                        solicitadas: list[LineaSolicitada], entregadas: dict[int, int],
                        motivos: dict[int, str] | None = None, id_dispensacion: int | None = None
                        ) -> tuple[SolicitudesDespacho, list[Faltantes]]:
    motivos = motivos or {}
    for id_detalle, motivo in motivos.items():
        if motivo not in MOTIVOS_FALTANTE:
            raise ReglaNegocioError("MOTIVO_INVALIDO", "El motivo de lo no entregado debe ser SIN_STOCK o RECHAZO_PACIENTE.")
    momento = ahora()
    detalle_json, pendientes = [], []
    for s in solicitadas:
        entregada = entregadas.get(s.detalle.id_detalle_receta, 0)
        falta = s.corresponde - entregada
        motivo = None
        if falta > 0:
            motivo = motivos.get(s.detalle.id_detalle_receta) or ("SIN_STOCK" if s.stock < s.corresponde
                                                                  else "RECHAZO_PACIENTE")
            pendientes.append((s, falta, motivo))
        med = s.detalle.medicamento
        detalle_json.append({"id_detalle_receta": s.detalle.id_detalle_receta, "id_medicamento": med.id_medicamento,
                             "medicamento": med.nombre, "programa": med.programa.nombre if med.programa else None,
                             "corresponde": s.corresponde, "entregada": entregada, "motivo": motivo})
    resultado = ("SIN_STOCK" if any(m == "SIN_STOCK" for *_, m in pendientes)
                 else "RECHAZO" if pendientes else "COMPLETA")
    solicitud = SolicitudesDespacho(id_receta=receta.id_receta, id_dispensacion=id_dispensacion,
                                    numero_entrega=numero_entrega, fecha_hora=momento, id_usuario=usuario.id_usuario,
                                    resultado=resultado, detalle=detalle_json, creado_por=usuario.id_usuario)
    db.add(solicitud)
    db.flush()

    creados = []
    for s, falta, motivo in pendientes:
        if motivo == "SIN_STOCK" and db.scalar(select(Faltantes.id_faltante).where(
                Faltantes.id_detalle_receta == s.detalle.id_detalle_receta, Faltantes.numero_entrega == numero_entrega,
                Faltantes.estado == "PENDIENTE")):
            continue  # ya hay un compromiso abierto para esta línea y entrega: conserva su plazo original
        faltante = Faltantes(id_solicitud=solicitud.id_solicitud, id_detalle_receta=s.detalle.id_detalle_receta,
                             numero_entrega=numero_entrega, cantidad=falta, motivo=motivo,
                             estado="PENDIENTE" if motivo == "SIN_STOCK" else "RECHAZO", fecha_registro=momento,
                             plazo=plazo_fofar(momento) if motivo == "SIN_STOCK" else None,
                             creado_por=usuario.id_usuario)
        db.add(faltante)
        creados.append(faltante)
    db.flush()
    return solicitud, creados


def resolver_con_entrega(db: Session, receta: Recetas, disp: Dispensaciones) -> list[Faltantes]:
    """Una entrega que completa la línea cumple los compromisos pendientes de esa entrega."""
    resueltos = []
    detalles = {d.id_detalle_receta: d for d in receta.detalles}
    for faltante in db.scalars(select(Faltantes).where(Faltantes.id_detalle_receta.in_(detalles),
                                                       Faltantes.estado == "PENDIENTE")).unique():
        d = detalles[faltante.id_detalle_receta]
        if d.cant_entregada >= min(faltante.numero_entrega * d.cant_por_entrega, d.cant_prescrita):
            faltante.estado, faltante.fecha_solucion = "ENTREGADO", ahora()
            faltante.id_dispensacion_solucion = disp.id_dispensacion
            resueltos.append(faltante)
    return resueltos


def anular_por_dispensacion(db: Session, disp: Dispensaciones) -> None:
    """Al anular una entrega (error de registro) se anulan su solicitud y sus faltantes, y los
    compromisos que esa entrega había cumplido vuelven a quedar pendientes."""
    solicitud = db.scalar(select(SolicitudesDespacho).where(SolicitudesDespacho.id_dispensacion == disp.id_dispensacion))
    if solicitud is not None:
        solicitud.estado = "ANULADA"
        for f in db.scalars(select(Faltantes).where(Faltantes.id_solicitud == solicitud.id_solicitud)).unique():
            if f.estado in ("PENDIENTE", "RECHAZO"):
                f.estado = "ANULADO"
    for f in db.scalars(select(Faltantes).where(Faltantes.id_dispensacion_solucion == disp.id_dispensacion)).unique():
        f.estado, f.fecha_solucion, f.id_dispensacion_solucion = "PENDIENTE", None, None


def registrar_sin_stock(db: Session, usuario: Usuarios, id_receta: int, hoy: date) -> dict:
    """El paciente vino a retirar y no hay nada que entregarle: queda la solicitud y el compromiso."""
    receta = db.get(Recetas, id_receta, with_for_update=True)
    if receta is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La receta no existe.")
    if receta.estado in ("ANULADA", "DISPENSADA"):
        raise ReglaNegocioError("RECETA_CERRADA", f"La receta está {receta.estado}.")
    exigir_receta_vigente(receta.fecha_emision, hoy, receta.tipo_receta, receta.entregas_realizadas)
    exigir_fecha_de_retiro(receta.proxima_fecha_retiro, hoy,
                           entrega_en_curso_iniciada([_linea(d) for d in receta.detalles], receta.entregas_realizadas))
    solicitadas = lineas_solicitadas(db, receta, hoy)
    con_stock = [s.detalle.medicamento.nombre for s in solicitadas if s.stock > 0]
    if con_stock:
        raise ReglaNegocioError("HAY_STOCK", f"Hay stock de {', '.join(con_stock)}: entregue lo disponible desde "
                                "«Atender receta»; lo que falte queda como compromiso automáticamente.")
    numero = min(receta.entregas_realizadas + 1, receta.total_entregas)
    solicitud, creados = registrar_solicitud(db, usuario, receta=receta, numero_entrega=numero,
                                             solicitadas=solicitadas, entregadas={},
                                             motivos={s.detalle.id_detalle_receta: "SIN_STOCK" for s in solicitadas})
    registrar_evento(db, tipo="SOLICITUD_SIN_STOCK", entidad="solicitudes_despacho", id_entidad=solicitud.id_solicitud,
                     id_usuario=usuario.id_usuario, folio=receta.folio, faltantes=len(creados))
    return {"id_solicitud": solicitud.id_solicitud, "folio": receta.folio, "resultado": solicitud.resultado,
            "faltantes": [describir_faltante(f, ahora()) for f in creados]}


def describir_faltante(f: Faltantes, momento: datetime) -> dict:
    receta = f.solicitud.receta
    plazo = _utc(f.plazo) if f.plazo else None
    return {
        "id_faltante": f.id_faltante, "id_receta": receta.id_receta, "folio": receta.folio,
        "numero_entrega": f.numero_entrega, "total_entregas": receta.total_entregas,
        "medicamento": f.detalle_receta.medicamento.nombre, "cantidad": f.cantidad, "motivo": f.motivo,
        "estado": f.estado, "fecha_registro": _utc(f.fecha_registro).isoformat(),
        "plazo": plazo.isoformat() if plazo else None,
        "vencido": bool(plazo and f.estado == "PENDIENTE" and momento > plazo),
        "horas_habiles_restantes": round(max(horas_habiles_entre(momento.astimezone(), plazo.astimezone()), 0), 1)
        if plazo and f.estado == "PENDIENTE" else None,
        "fecha_solucion": _utc(f.fecha_solucion).isoformat() if f.fecha_solucion else None,
        "a_tiempo": (_utc(f.fecha_solucion) <= plazo) if f.fecha_solucion and plazo else None,
        "paciente": {"id_paciente": receta.paciente.id_paciente, "nombre": receta.paciente.nombre,
                     "rut": receta.paciente.rut_enmascarado},
    }


def listar_faltantes(db: Session, estados: list[str] | None = None, limite: int = 200) -> list[dict]:
    consulta = select(Faltantes).where(Faltantes.motivo == "SIN_STOCK").order_by(Faltantes.plazo, Faltantes.id_faltante)
    if estados:
        consulta = consulta.where(Faltantes.estado.in_(estados))
    momento = ahora()
    return [describir_faltante(f, momento) for f in db.scalars(consulta.limit(limite)).unique()]


# -------------------------------------------------------------------- reclamos
def describir_reclamo(r: Reclamos, momento: datetime) -> dict:
    plazo = _utc(r.plazo)
    solucion = _utc(r.fecha_solucion) if r.fecha_solucion else None
    faltante = describir_faltante(r.faltante, momento) if r.faltante is not None else None
    return {
        "id_reclamo": r.id_reclamo, "canal": r.canal, "canal_texto": CANALES_RECLAMO[r.canal],
        "folio_externo": r.folio_externo, "descripcion": r.descripcion, "estado": r.estado,
        "fecha_reclamo": _utc(r.fecha_reclamo).isoformat(), "plazo": plazo.isoformat(),
        "fecha_solucion": solucion.isoformat() if solucion else None, "solucion": r.solucion,
        "recibe_nombre": r.recibe_nombre,
        "dentro_de_plazo": (solucion <= plazo) if solucion and r.estado == "RESUELTO"
        else (None if r.estado != "ABIERTO" else (False if momento > plazo else None)),
        "vencido": r.estado == "ABIERTO" and momento > plazo,
        "horas_habiles_restantes": round(max(horas_habiles_entre(momento.astimezone(), plazo.astimezone()), 0), 1)
        if r.estado == "ABIERTO" else None,
        "paciente": {"id_paciente": r.paciente.id_paciente, "nombre": r.paciente.nombre,
                     "rut": r.paciente.rut_enmascarado},
        "faltante": faltante,
    }


def registrar_reclamo(db: Session, usuario: Usuarios, *, canal: str, descripcion: str,
                      folio_externo: str | None = None, id_faltante: int | None = None, rut: str | None = None) -> Reclamos:
    if canal not in CANALES_RECLAMO:
        raise ReglaNegocioError("CANAL_INVALIDO", "El canal debe ser OIRS, Salud Responde o presencial.")
    descripcion = exigir_motivo(descripcion)
    faltante = None
    if id_faltante is not None:
        faltante = db.get(Faltantes, id_faltante)
        if faltante is None or faltante.motivo != "SIN_STOCK":
            raise ReglaNegocioError("NO_ENCONTRADO", "El compromiso de entrega no existe.")
        paciente = faltante.solicitud.receta.paciente
    elif rut:
        paciente = db.scalar(select(Pacientes).where(Pacientes.rut_hmac == hmac_rut(normalizar_rut(rut))))
        if paciente is None:
            raise ReglaNegocioError("NO_ENCONTRADO", "No hay un paciente registrado con ese RUT.")
    else:
        raise ReglaNegocioError("PACIENTE_REQUERIDO", "Indique el RUT del paciente o el compromiso reclamado.")
    momento = ahora()
    reclamo = Reclamos(id_paciente=paciente.id_paciente, id_faltante=faltante.id_faltante if faltante else None,
                       canal=canal, folio_externo=(folio_externo or "").strip() or None, descripcion=descripcion,
                       fecha_reclamo=momento, plazo=plazo_fofar(momento), estado="ABIERTO",
                       creado_por=usuario.id_usuario)
    db.add(reclamo)
    db.flush()
    registrar_evento(db, tipo="RECLAMO_REGISTRADO", entidad="reclamos", id_entidad=reclamo.id_reclamo,
                     id_usuario=usuario.id_usuario, canal=canal, id_faltante=reclamo.id_faltante)
    return reclamo


def _reclamo_abierto(db: Session, id_reclamo: int) -> Reclamos:
    reclamo = db.get(Reclamos, id_reclamo, with_for_update=True)
    if reclamo is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El reclamo no existe.")
    if reclamo.estado != "ABIERTO":
        raise ReglaNegocioError("RECLAMO_CERRADO", "El reclamo ya está cerrado.")
    return reclamo


def cerrar_reclamo(db: Session, usuario: Usuarios, id_reclamo: int, *, solucion: str, recibe_nombre: str) -> Reclamos:
    """Cierre con acta de recepción: el FOFAR cuenta el plazo hasta la firma del acta."""
    reclamo = _reclamo_abierto(db, id_reclamo)
    solucion = exigir_motivo(solucion)
    if len((recibe_nombre or "").strip()) < 3:
        raise ReglaNegocioError("RECEPTOR_REQUERIDO", "Indique el nombre de quien recibe y firma el acta.")
    if reclamo.faltante is not None and reclamo.faltante.estado == "PENDIENTE":
        raise ReglaNegocioError("FALTANTE_PENDIENTE", "Primero entregue el medicamento comprometido desde Dispensar; "
                                "luego cierre el reclamo con el acta.")
    reclamo.estado, reclamo.solucion, reclamo.recibe_nombre = "RESUELTO", solucion, recibe_nombre.strip()
    reclamo.fecha_solucion, reclamo.resuelto_por, reclamo.actualizado_por = ahora(), usuario.id_usuario, usuario.id_usuario
    registrar_evento(db, tipo="RECLAMO_RESUELTO", entidad="reclamos", id_entidad=reclamo.id_reclamo,
                     id_usuario=usuario.id_usuario, dentro_de_plazo=_utc(reclamo.fecha_solucion) <= _utc(reclamo.plazo))
    return reclamo


def marcar_no_atingente(db: Session, usuario: Usuarios, id_reclamo: int, motivo: str) -> Reclamos:
    """Reclamo que no corresponde al programa (p. ej. trato, horario): sale del indicador con su motivo."""
    reclamo = _reclamo_abierto(db, id_reclamo)
    reclamo.estado, reclamo.solucion = "NO_ATINGENTE", exigir_motivo(motivo)
    reclamo.fecha_solucion, reclamo.resuelto_por, reclamo.actualizado_por = ahora(), usuario.id_usuario, usuario.id_usuario
    registrar_evento(db, tipo="RECLAMO_NO_ATINGENTE", entidad="reclamos", id_entidad=reclamo.id_reclamo,
                     id_usuario=usuario.id_usuario, motivo=reclamo.solucion)
    return reclamo


def listar_reclamos(db: Session, estados: list[str] | None = None, limite: int = 200) -> list[dict]:
    consulta = select(Reclamos).order_by(Reclamos.fecha_reclamo.desc(), Reclamos.id_reclamo.desc())
    if estados:
        consulta = consulta.where(Reclamos.estado.in_(estados))
    momento = ahora()
    return [describir_reclamo(r, momento) for r in db.scalars(consulta.limit(limite)).unique()]


def acta_reclamo(db: Session, id_reclamo: int) -> dict:
    reclamo = db.get(Reclamos, id_reclamo)
    if reclamo is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El reclamo no existe.")
    if reclamo.estado != "RESUELTO":
        raise ReglaNegocioError("RECLAMO_ABIERTO", "El acta se emite al resolver el reclamo.")
    return describir_reclamo(reclamo, ahora())
