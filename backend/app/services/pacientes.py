"""Registro de pacientes (RF-04).

El RUT nunca se guarda en claro: se guarda su huella HMAC (para buscar) y
una versión enmascarada (para mostrar). Por eso la duplicidad se revisa
comparando huellas, y el RUT tampoco va en el evento de auditoría.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.rut import enmascarar_rut, normalizar_rut
from ..models import Pacientes, PacientesProgramas, ProgramasSalud, Sectores, Usuarios
from ..security.claves import hmac_rut
from .auditoria import registrar_evento


def describir_paciente(p: Pacientes) -> dict:
    return {"id_paciente": p.id_paciente, "nombre": p.nombre, "rut": p.rut_enmascarado,
            "fecha_nacimiento": p.fecha_nacimiento.isoformat() if p.fecha_nacimiento else None,
            "tramo_fonasa": p.tramo_fonasa, "es_prais": p.es_prais, "es_postrado": p.es_postrado,
            "id_sector": p.id_sector, "sector": p.sector.nombre if p.sector else None, "alergias": p.alergias,
            "tiene_direccion": bool(p.direccion), "programas": [pr.nombre for pr in p.programas]}


def registrar_paciente(db: Session, usuario: Usuarios, *, rut: str, nombre: str, hoy: date,
                       fecha_nacimiento: date | None = None, tramo_fonasa: str | None = None,
                       programas: list[int] | None = None, id_sector: int | None = None,
                       es_prais: bool = False, es_postrado: bool = False, alergias: str | None = None,
                       direccion: str | None = None) -> Pacientes:
    rut = normalizar_rut(rut)
    huella = hmac_rut(rut)
    if db.scalar(select(Pacientes.id_paciente).where(Pacientes.rut_hmac == huella)):
        raise ReglaNegocioError("RUT_DUPLICADO", "Ya existe un paciente registrado con ese RUT.")
    if fecha_nacimiento and fecha_nacimiento > hoy:
        raise ReglaNegocioError("FECHA_INVALIDA", "La fecha de nacimiento no puede ser futura.")
    if id_sector is not None:
        sector = db.get(Sectores, id_sector)
        if sector is None or not sector.activo:
            raise ReglaNegocioError("SECTOR_INVALIDO", "El sector indicado no existe.")
    if direccion and not es_postrado:
        raise ReglaNegocioError("DIRECCION_SOLO_POSTRADO",
                                "La dirección se registra solo para pacientes postrados (despacho a domicilio).")
    ids_programas = sorted(set(programas or []))
    encontrados = list(db.scalars(select(ProgramasSalud).where(ProgramasSalud.id_programa.in_(ids_programas)))) \
        if ids_programas else []
    if len(encontrados) != len(ids_programas):
        raise ReglaNegocioError("PROGRAMA_INVALIDO", "Uno de los programas de salud indicados no existe.")

    paciente = Pacientes(rut_hmac=huella, rut_enmascarado=enmascarar_rut(rut), nombre=nombre,
                         fecha_nacimiento=fecha_nacimiento, tramo_fonasa=tramo_fonasa, id_sector=id_sector,
                         es_prais=es_prais, es_postrado=es_postrado, alergias=alergias or None,
                         direccion=direccion or None, creado_por=usuario.id_usuario)
    db.add(paciente)
    db.flush()
    for programa in encontrados:
        db.add(PacientesProgramas(id_paciente=paciente.id_paciente, id_programa=programa.id_programa,
                                  fecha_ingreso=hoy))
    db.flush()
    db.refresh(paciente)
    registrar_evento(db, tipo="PACIENTE_CREADO", entidad="pacientes", id_entidad=paciente.id_paciente,
                     id_usuario=usuario.id_usuario, programas=[p.nombre for p in encontrados])
    return paciente
