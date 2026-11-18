"""Registro de recetas: asigna medicamentos a un paciente (RF-01).

La receta la emite el médico; la farmacia la transcribe para poder
dispensarla. Reglas:
  * Folio único y fecha de emisión vigente (RN-04: no futura, máximo 30 días).
  * Tipo AGUDA o RETENIDA con una entrega; CRONICA con 2 a 6 entregas cada
    `intervalo_dias`. Cada línea indica la cantidad por entrega.
  * Solo medicamentos activos y sin repetir dentro de la receta.
  * Un controlado exige receta retenida y que la registre un Q.F., con los datos que
    el libro de control exige (D.S. 404/405 art. 18): nombre y RUT del prescriptor y
    domicilio del paciente; y el N.º de receta cheque si el medicamento la requiere
    (estupefacientes y psicotrópicos de las listas II y III).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.rut import normalizar_rut
from ..domain.recetas import (TOLERANCIA_RETIRO_DIAS, LineaEntrega, entrega_en_curso_iniciada,
                              exigir_receta_vigente, pendiente, receta_vigente, saldo_entrega_actual,
                              validar_estructura)
from ..models import DetallesReceta, Medicamentos, Pacientes, Recetas, Usuarios
from ..security.rbac import Permisos, tiene_permiso
from .auditoria import registrar_evento


@dataclass(frozen=True)
class LineaReceta:
    id_medicamento: int
    posologia: str
    cant_por_entrega: int | None = None   # unidades mínimas en cada entrega
    cant_prescrita: int | None = None     # total; si se omite, = por entrega × entregas


def _cantidades(linea: LineaReceta, total_entregas: int) -> tuple[int, int]:
    """(cantidad por entrega, total prescrito), coherentes entre sí."""
    if linea.cant_por_entrega:
        total = linea.cant_por_entrega * total_entregas
        if linea.cant_prescrita and linea.cant_prescrita != total:
            raise ReglaNegocioError("CANTIDADES_INCONSISTENTES",
                                    f"{linea.cant_por_entrega} por entrega × {total_entregas} entregas = {total}, "
                                    f"no {linea.cant_prescrita}.")
        return linea.cant_por_entrega, total
    if not linea.cant_prescrita or linea.cant_prescrita % total_entregas:
        raise ReglaNegocioError("CANTIDADES_INCONSISTENTES",
                                "Indique la cantidad por entrega (el total debe repartirse en partes iguales).")
    return linea.cant_prescrita // total_entregas, linea.cant_prescrita


def describir_receta(r: Recetas, hoy: date) -> dict:
    return {
        "id_receta": r.id_receta, "folio": r.folio, "fecha_emision": r.fecha_emision.isoformat(),
        "estado": r.estado, "tipo_receta": r.tipo_receta, "es_retenida": r.es_retenida,
        "vigente": receta_vigente(r.fecha_emision, hoy, r.tipo_receta, r.entregas_realizadas),
        "total_entregas": r.total_entregas, "entregas_realizadas": r.entregas_realizadas,
        "entrega_actual": min(r.entregas_realizadas + 1, r.total_entregas),
        "intervalo_dias": r.intervalo_dias,
        "proxima_fecha_retiro": r.proxima_fecha_retiro.isoformat() if r.proxima_fecha_retiro else None,
        "retiro_desde": _retiro_desde(r),
        "prescriptor": r.prescriptor_nombre, "numero_receta_cheque": r.numero_receta_cheque,
        "detalles": [{"id_detalle_receta": d.id_detalle_receta, "id_medicamento": d.id_medicamento,
                      "medicamento": d.medicamento.nombre, "unidad": d.medicamento.unidad_dispensacion,
                      "es_controlado": d.medicamento.es_controlado, "posologia": d.posologia,
                      "cant_prescrita": d.cant_prescrita, "cant_por_entrega": d.cant_por_entrega,
                      "cant_entregada": d.cant_entregada,
                      "pendiente": pendiente(d.cant_prescrita, d.cant_entregada),
                      "saldo_entrega": saldo_entrega_actual(_linea(d), r.entregas_realizadas)} for d in r.detalles],
    }


def _linea(d) -> LineaEntrega:
    return LineaEntrega(cant_prescrita=d.cant_prescrita, cant_por_entrega=d.cant_por_entrega,
                        cant_entregada=d.cant_entregada)


def _retiro_desde(r: Recetas) -> str | None:
    """Primer día en que se puede retirar la entrega en curso (None si no quedan entregas)."""
    if r.proxima_fecha_retiro is None or entrega_en_curso_iniciada([_linea(d) for d in r.detalles],
                                                                  r.entregas_realizadas):
        return None
    return (r.proxima_fecha_retiro - timedelta(days=TOLERANCIA_RETIRO_DIAS)).isoformat()


def registrar_receta(db: Session, usuario: Usuarios, *, id_paciente: int, folio: str, fecha_emision: date,
                     lineas: list[LineaReceta], hoy: date, es_retenida: bool = False,
                     tipo_receta: str | None = None, total_entregas: int = 1, intervalo_dias: int = 30,
                     prescriptor_nombre: str | None = None, prescriptor_rut: str | None = None,
                     domicilio_paciente: str | None = None, numero_receta_cheque: str | None = None) -> Recetas:
    if db.get(Pacientes, id_paciente) is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El paciente no existe.")
    if db.scalar(select(Recetas.id_receta).where(Recetas.folio == folio)):
        raise ReglaNegocioError("FOLIO_DUPLICADO", f"Ya existe una receta con folio {folio}.")
    exigir_receta_vigente(fecha_emision, hoy)
    if not lineas:
        raise ReglaNegocioError("RECETA_VACIA", "La receta debe tener al menos un medicamento.")
    ids = [l.id_medicamento for l in lineas]
    if len(set(ids)) != len(ids):
        raise ReglaNegocioError("LINEA_REPETIDA", "Un medicamento aparece dos veces en la receta.")

    medicamentos = {m.id_medicamento: m for m in db.scalars(
        select(Medicamentos).where(Medicamentos.id_medicamento.in_(ids)))}
    for id_med in ids:
        med = medicamentos.get(id_med)
        if med is None:
            raise ReglaNegocioError("NO_ENCONTRADO", "Uno de los medicamentos indicados no existe.")
        if not med.activo:
            raise ReglaNegocioError("MEDICAMENTO_INACTIVO", f"{med.nombre} está dado de baja.")
    controlados = [m.nombre for m in medicamentos.values() if m.es_controlado]
    tipo = tipo_receta or ("RETENIDA" if es_retenida else "AGUDA")
    if es_retenida and tipo != "RETENIDA":
        raise ReglaNegocioError("TIPO_RECETA_INVALIDO", "Una receta retenida debe ser de tipo RETENIDA.")
    try:
        validar_estructura(tipo, total_entregas, intervalo_dias, bool(controlados))
    except ReglaNegocioError as error:
        if error.codigo == "RECETA_NO_RETENIDA":
            raise ReglaNegocioError("RECETA_NO_RETENIDA",
                                    f"{', '.join(controlados)} es controlado: la receta debe quedar retenida.") from None
        raise
    cantidades = {l.id_medicamento: _cantidades(l, total_entregas) for l in lineas}
    if controlados:
        if not tiene_permiso(usuario.rol.nombre, Permisos.FIRMAR_CONTROLADOS):
            raise ReglaNegocioError("REQUIERE_QF", "Solo un Q.F. puede registrar recetas de medicamentos controlados.")
    prescriptor_nombre = (prescriptor_nombre or "").strip() or None
    domicilio_paciente = (domicilio_paciente or "").strip() or None
    numero_receta_cheque = (numero_receta_cheque or "").strip() or None
    if prescriptor_rut:
        prescriptor_rut = normalizar_rut(prescriptor_rut)
    if usuario.rol.nombre == "MEDICO":
        prescriptor_nombre, prescriptor_rut = usuario.nombre, usuario.rut
    if controlados:
        faltan = [nombre for nombre, valor in (("nombre del prescriptor", prescriptor_nombre),
                                               ("RUT del prescriptor", prescriptor_rut),
                                               ("domicilio del paciente", domicilio_paciente)) if not valor]
        if faltan:
            raise ReglaNegocioError("DATOS_LIBRO_REQUERIDOS", "El libro de controlados exige " + ", ".join(faltan)
                                    + " (D.S. 404/405 art. 18).")
        con_cheque = [m.nombre for m in medicamentos.values() if m.requiere_receta_cheque]
        if con_cheque and not numero_receta_cheque:
            raise ReglaNegocioError("RECETA_CHEQUE_REQUERIDA",
                                    f"{', '.join(con_cheque)} exige receta cheque: indique su número.")

    receta = Recetas(folio=folio, id_paciente=id_paciente, fecha_emision=fecha_emision,
                     tipo_receta=tipo, total_entregas=total_entregas, entregas_realizadas=0,
                     intervalo_dias=intervalo_dias, proxima_fecha_retiro=fecha_emision,
                     id_medico=usuario.id_usuario if usuario.rol.nombre == "MEDICO" else None,
                     prescriptor_nombre=prescriptor_nombre, prescriptor_rut=prescriptor_rut,
                     domicilio_paciente=domicilio_paciente, numero_receta_cheque=numero_receta_cheque,
                     creado_por=usuario.id_usuario)
    db.add(receta)
    db.flush()
    for linea in lineas:
        por_entrega, total = cantidades[linea.id_medicamento]
        db.add(DetallesReceta(id_receta=receta.id_receta, id_medicamento=linea.id_medicamento,
                              cant_prescrita=total, cant_por_entrega=por_entrega, posologia=linea.posologia,
                              creado_por=usuario.id_usuario))
    db.flush()
    db.refresh(receta)
    registrar_evento(db, tipo="RECETA_REGISTRADA", entidad="recetas", id_entidad=receta.id_receta,
                     id_usuario=usuario.id_usuario, folio=folio, id_paciente=id_paciente,
                     medicamentos=[medicamentos[i].codigo for i in ids], con_controlados=bool(controlados),
                     tipo_receta=tipo, total_entregas=total_entregas)
    return receta


def retiros_pendientes(db: Session, hoy: date, dias: int = 0) -> list[dict]:
    """Recetas con una entrega para retirar hasta `hoy + dias` (incluye las atrasadas), por fecha.

    Sirve para preparar con anticipación las entregas del día y llamar a quien no vino.
    """
    limite = hoy + timedelta(days=dias)
    filas = db.scalars(select(Recetas).where(Recetas.estado.in_(["PENDIENTE", "PARCIAL"]),
                                             Recetas.proxima_fecha_retiro.is_not(None),
                                             Recetas.proxima_fecha_retiro <= limite)
                       .order_by(Recetas.proxima_fecha_retiro, Recetas.id_receta)).unique()
    resultado = []
    for r in filas:
        if not receta_vigente(r.fecha_emision, hoy, r.tipo_receta, r.entregas_realizadas):
            continue
        p = r.paciente
        resultado.append({
            "id_receta": r.id_receta, "folio": r.folio, "tipo_receta": r.tipo_receta,
            "entrega_actual": min(r.entregas_realizadas + 1, r.total_entregas), "total_entregas": r.total_entregas,
            "proxima_fecha_retiro": r.proxima_fecha_retiro.isoformat(),
            "dias_atraso": max((hoy - r.proxima_fecha_retiro).days, 0),
            "medicamentos": [d.medicamento.nombre for d in r.detalles if d.cant_entregada < d.cant_prescrita],
            "paciente": {"id_paciente": p.id_paciente, "nombre": p.nombre, "rut": p.rut_enmascarado,
                         "sector": p.sector.nombre if p.sector else None, "es_postrado": p.es_postrado},
        })
    return resultado
