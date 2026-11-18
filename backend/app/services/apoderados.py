"""Apoderados: terceros autorizados a retirar en nombre del paciente.

Como el RUT del paciente, el del apoderado se guarda como huella HMAC y en
forma enmascarada. Dar de baja es lógico (queda la historia de sus retiros).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.rut import enmascarar_rut, normalizar_rut
from ..models import Apoderados, Pacientes, Usuarios
from ..reloj import ahora
from ..security.claves import hmac_rut
from .auditoria import registrar_evento
from .inventario import exigir_motivo


def describir_apoderado(a: Apoderados, hoy: date) -> dict:
    return {"id_apoderado": a.id_apoderado, "nombre": a.nombre, "rut": a.rut_enmascarado, "parentesco": a.parentesco,
            "telefono": a.telefono, "vigente_hasta": a.vigente_hasta.isoformat() if a.vigente_hasta else None,
            "activo": a.activo, "vigente": a.activo and (a.vigente_hasta is None or a.vigente_hasta >= hoy)}


def listar_apoderados(db: Session, id_paciente: int, incluir_inactivos: bool = False) -> list[Apoderados]:
    consulta = select(Apoderados).where(Apoderados.id_paciente == id_paciente).order_by(Apoderados.nombre)
    if not incluir_inactivos:
        consulta = consulta.where(Apoderados.activo.is_(True))
    return list(db.scalars(consulta))


def registrar_apoderado(db: Session, usuario: Usuarios, *, id_paciente: int, rut: str, nombre: str, parentesco: str,
                        hoy: date, telefono: str | None = None, vigente_hasta: date | None = None) -> Apoderados:
    paciente = db.get(Pacientes, id_paciente)
    if paciente is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El paciente no existe.")
    rut = normalizar_rut(rut)
    huella = hmac_rut(rut)
    if huella == paciente.rut_hmac:
        raise ReglaNegocioError("APODERADO_ES_PACIENTE", "El paciente no puede ser su propio apoderado.")
    existente = db.scalar(select(Apoderados).where(Apoderados.id_paciente == id_paciente,
                                                   Apoderados.rut_hmac == huella))
    if existente is not None:
        raise ReglaNegocioError("APODERADO_DUPLICADO", "Esa persona ya está registrada como apoderado del paciente.")
    if vigente_hasta is not None and vigente_hasta < hoy:
        raise ReglaNegocioError("FECHA_INVALIDA", "La vigencia del poder no puede estar vencida al registrarlo.")
    apoderado = Apoderados(id_paciente=id_paciente, rut_hmac=huella, rut_enmascarado=enmascarar_rut(rut),
                           nombre=nombre, parentesco=parentesco, telefono=telefono or None,
                           vigente_hasta=vigente_hasta, creado_por=usuario.id_usuario)
    db.add(apoderado)
    db.flush()
    registrar_evento(db, tipo="APODERADO_REGISTRADO", entidad="apoderados", id_entidad=apoderado.id_apoderado,
                     id_usuario=usuario.id_usuario, id_paciente=id_paciente, parentesco=parentesco)
    return apoderado


def dar_de_baja_apoderado(db: Session, usuario: Usuarios, id_apoderado: int, motivo: str) -> Apoderados:
    motivo = exigir_motivo(motivo)
    apoderado = db.get(Apoderados, id_apoderado)
    if apoderado is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El apoderado no existe.")
    if not apoderado.activo:
        raise ReglaNegocioError("YA_DADO_DE_BAJA", "El apoderado ya está dado de baja.")
    apoderado.activo, apoderado.fecha_baja, apoderado.baja_por, apoderado.motivo_baja = (
        False, ahora(), usuario.id_usuario, motivo)
    registrar_evento(db, tipo="APODERADO_DADO_DE_BAJA", entidad="apoderados", id_entidad=apoderado.id_apoderado,
                     id_usuario=usuario.id_usuario, motivo=motivo)
    return apoderado
