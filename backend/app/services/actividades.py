"""Actividades farmacéuticas del Q.F. (FOFAR, indicador N.º 4; OT FOFAR 3.2.5).

  * Atención farmacéutica: revisión de la medicación, conciliación, educación y
    seguimiento farmacoterapéutico (siempre con un paciente).
  * Farmacovigilancia (Norma Técnica N.º 140 del ISP): sospecha de reacción adversa
    (RAM), falla de calidad y evento adverso. El sistema genera la ficha para
    ingresarla al Sistema de Vigilancia Integrado (SVI) del ISP y registra el folio;
    no hay integración en línea porque el ISP no ofrece una API pública.
  * Talleres de educación grupal (al menos uno por semestre).
La meta se programa por año: 50 % de cumplimiento a junio y 100 % a diciembre.
Una actividad registrada no se borra: se anula con motivo.
"""

from datetime import date, timedelta

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.rut import normalizar_rut
from ..models import ActividadesFarmaceuticas, Lotes, Medicamentos, Pacientes, ProgramacionActividades, Usuarios
from ..reloj import ahora
from ..security.claves import hmac_rut
from .auditoria import registrar_evento
from .inventario import exigir_motivo

TIPOS = {
    "REVISION_MEDICACION": "Revisión de la medicación", "CONCILIACION": "Conciliación farmacéutica",
    "EDUCACION": "Educación farmacéutica", "SEGUIMIENTO_FT": "Seguimiento farmacoterapéutico",
    "RAM": "Sospecha de reacción adversa (RAM)", "FALLA_CALIDAD": "Falla de calidad",
    "EVENTO_ADVERSO": "Evento adverso asociado a medicamentos", "TALLER": "Taller de educación grupal",
}
ATENCION = ("REVISION_MEDICACION", "CONCILIACION", "EDUCACION", "SEGUIMIENTO_FT")
FARMACOVIGILANCIA = ("RAM", "FALLA_CALIDAD", "EVENTO_ADVERSO")
CON_PACIENTE = ATENCION + ("RAM", "EVENTO_ADVERSO")
CON_MEDICAMENTO = ("RAM", "FALLA_CALIDAD")


def _edad(nacimiento: date | None, hoy: date) -> int | None:
    if nacimiento is None:
        return None
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def describir_actividad(a: ActividadesFarmaceuticas) -> dict:
    p = a.paciente
    return {
        "id_actividad": a.id_actividad, "tipo": a.tipo, "tipo_texto": TIPOS[a.tipo], "fecha": a.fecha.isoformat(),
        "categoria": "ATENCION" if a.tipo in ATENCION else "FARMACOVIGILANCIA" if a.tipo in FARMACOVIGILANCIA else "TALLER",
        "paciente": {"id_paciente": p.id_paciente, "nombre": p.nombre, "rut": p.rut_enmascarado,
                     "edad": _edad(p.fecha_nacimiento, a.fecha)} if p else None,
        "medicamento": a.medicamento.nombre if a.medicamento else None,
        "principio_activo": a.medicamento.principio_activo if a.medicamento else None,
        "lote": a.lote.codigo_lote if a.lote else None,
        "vencimiento_lote": a.lote.fecha_vencimiento.isoformat() if a.lote else None,
        "descripcion": a.descripcion, "resultado": a.resultado, "participantes": a.participantes,
        "gravedad": a.gravedad, "fecha_notificacion": a.fecha_notificacion.isoformat() if a.fecha_notificacion else None,
        "folio_isp": a.folio_isp,
        "pendiente_notificar": a.tipo in FARMACOVIGILANCIA and a.fecha_notificacion is None and a.estado == "VIGENTE",
        "estado": a.estado, "motivo_anulacion": a.motivo_anulacion,
    }


def registrar_actividad(db: Session, qf: Usuarios, *, tipo: str, fecha: date, descripcion: str, hoy: date,
                        rut_paciente: str | None = None, id_medicamento: int | None = None,
                        id_lote: int | None = None, resultado: str | None = None,
                        participantes: int | None = None, gravedad: str | None = None) -> ActividadesFarmaceuticas:
    if tipo not in TIPOS:
        raise ReglaNegocioError("TIPO_INVALIDO", "Tipo de actividad desconocido.")
    if fecha > hoy or fecha < hoy - timedelta(days=365):
        raise ReglaNegocioError("FECHA_INVALIDA", "La fecha no puede ser futura ni de hace más de un año.")
    descripcion = exigir_motivo(descripcion)
    paciente = None
    if tipo in CON_PACIENTE:
        if not rut_paciente:
            raise ReglaNegocioError("PACIENTE_REQUERIDO", f"{TIPOS[tipo]}: indique el RUT del paciente.")
        paciente = db.scalar(select(Pacientes).where(Pacientes.rut_hmac == hmac_rut(normalizar_rut(rut_paciente))))
        if paciente is None:
            raise ReglaNegocioError("NO_ENCONTRADO", "No hay un paciente registrado con ese RUT.")
    elif rut_paciente:
        raise ReglaNegocioError("PACIENTE_NO_CORRESPONDE", f"{TIPOS[tipo]} no se registra a nombre de un paciente.")
    if tipo in CON_MEDICAMENTO and id_medicamento is None:
        raise ReglaNegocioError("MEDICAMENTO_REQUERIDO", f"{TIPOS[tipo]}: indique el medicamento sospechoso.")
    if id_medicamento is not None and db.get(Medicamentos, id_medicamento) is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El medicamento no existe.")
    if id_lote is not None:
        lote = db.get(Lotes, id_lote)
        if lote is None or lote.id_medicamento != id_medicamento:
            raise ReglaNegocioError("LOTE_INVALIDO", "El lote no corresponde al medicamento indicado.")
    if tipo == "RAM" and not gravedad:
        raise ReglaNegocioError("GRAVEDAD_REQUERIDA", "Indique la gravedad de la reacción adversa.")
    if tipo != "RAM":
        gravedad = None
    if tipo == "TALLER":
        if not participantes:
            raise ReglaNegocioError("PARTICIPANTES_REQUERIDOS", "Indique cuántas personas asistieron al taller.")
    else:
        participantes = None

    actividad = ActividadesFarmaceuticas(
        tipo=tipo, fecha=fecha, id_paciente=paciente.id_paciente if paciente else None, id_medicamento=id_medicamento,
        id_lote=id_lote, descripcion=descripcion, resultado=(resultado or "").strip() or None,
        participantes=participantes, gravedad=gravedad, id_usuario=qf.id_usuario, estado="VIGENTE",
        creado_por=qf.id_usuario)
    db.add(actividad)
    db.flush()
    db.refresh(actividad)
    registrar_evento(db, tipo="ACTIVIDAD_FARMACEUTICA", entidad="actividades_farmaceuticas",
                     id_entidad=actividad.id_actividad, id_usuario=qf.id_usuario, tipo_actividad=tipo)
    return actividad


def obtener_actividad(db: Session, id_actividad: int) -> ActividadesFarmaceuticas:
    actividad = db.get(ActividadesFarmaceuticas, id_actividad)
    if actividad is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "La actividad no existe.")
    return actividad


def anular_actividad(db: Session, qf: Usuarios, id_actividad: int, motivo: str) -> ActividadesFarmaceuticas:
    actividad = obtener_actividad(db, id_actividad)
    if actividad.estado == "ANULADA":
        raise ReglaNegocioError("YA_ANULADA", "La actividad ya está anulada.")
    actividad.estado, actividad.motivo_anulacion = "ANULADA", exigir_motivo(motivo)
    actividad.fecha_anulacion, actividad.anulada_por, actividad.actualizado_por = ahora(), qf.id_usuario, qf.id_usuario
    registrar_evento(db, tipo="ACTIVIDAD_ANULADA", entidad="actividades_farmaceuticas", id_entidad=id_actividad,
                     id_usuario=qf.id_usuario, motivo=actividad.motivo_anulacion)
    return actividad


def registrar_notificacion(db: Session, qf: Usuarios, id_actividad: int, *, fecha_notificacion: date, folio_isp: str,
                           hoy: date) -> ActividadesFarmaceuticas:
    actividad = obtener_actividad(db, id_actividad)
    if actividad.tipo not in FARMACOVIGILANCIA:
        raise ReglaNegocioError("NO_NOTIFICABLE", "Solo las actividades de farmacovigilancia se notifican al ISP.")
    if actividad.estado != "VIGENTE":
        raise ReglaNegocioError("YA_ANULADA", "La actividad está anulada.")
    if not actividad.fecha <= fecha_notificacion <= hoy:
        raise ReglaNegocioError("FECHA_INVALIDA", "La notificación es posterior a la detección y no puede ser futura.")
    actividad.fecha_notificacion, actividad.folio_isp = fecha_notificacion, folio_isp.strip()
    actividad.actualizado_por = qf.id_usuario
    registrar_evento(db, tipo="NOTIFICACION_ISP", entidad="actividades_farmaceuticas", id_entidad=id_actividad,
                     id_usuario=qf.id_usuario, folio_isp=actividad.folio_isp)
    return actividad


def listar_actividades(db: Session, anio: int, tipo: str | None = None) -> list[dict]:
    consulta = (select(ActividadesFarmaceuticas).where(extract("year", ActividadesFarmaceuticas.fecha) == anio)
                .order_by(ActividadesFarmaceuticas.fecha.desc(), ActividadesFarmaceuticas.id_actividad.desc()))
    if tipo:
        consulta = consulta.where(ActividadesFarmaceuticas.tipo == tipo)
    return [describir_actividad(a) for a in db.scalars(consulta)]


def programar(db: Session, usuario: Usuarios, anio: int, cantidad: int) -> ProgramacionActividades:
    if cantidad <= 0:
        raise ReglaNegocioError("CANTIDAD_INVALIDA", "La programación debe ser mayor que cero.")
    programacion = db.get(ProgramacionActividades, anio)
    anterior = programacion.cantidad if programacion else None
    if programacion is None:
        programacion = ProgramacionActividades(anio=anio, cantidad=cantidad, creado_por=usuario.id_usuario)
        db.add(programacion)
    else:
        programacion.cantidad, programacion.actualizado_por = cantidad, usuario.id_usuario
    registrar_evento(db, tipo="ACTIVIDADES_PROGRAMADAS", entidad="programacion_actividades", id_entidad=anio,
                     id_usuario=usuario.id_usuario, cantidad=cantidad, anterior=anterior)
    return programacion
