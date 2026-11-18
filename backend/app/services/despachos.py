"""Despacho a domicilio para pacientes postrados.

Estados y transiciones permitidas:
    PREPARANDO -> EN_RUTA -> ENTREGADO
                     |
                     +----> FALLIDO -> EN_RUTA (reintento)

ENTREGADO es final. Al entregar se registra quién recibió; un intento
fallido exige una observación (p. ej. "nadie en el domicilio"). Cada cambio
queda en la auditoría.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..models import DespachosDomicilio, Usuarios
from ..reloj import ahora, iso_utc
from .auditoria import registrar_evento

TRANSICIONES = {
    "PREPARANDO": {"EN_RUTA"},
    "EN_RUTA": {"ENTREGADO", "FALLIDO"},
    "FALLIDO": {"EN_RUTA"},
    "ENTREGADO": set(),
}


def describir_despacho(d: DespachosDomicilio) -> dict:
    disp = d.dispensacion
    paciente = disp.receta.paciente
    return {
        "id_despacho": d.id_despacho, "estado": d.estado, "id_dispensacion": disp.id_dispensacion,
        "folio": disp.receta.folio, "numero_entrega": disp.numero_entrega, "total_entregas": disp.receta.total_entregas,
        "paciente": paciente.nombre, "rut": paciente.rut_enmascarado,
        "sector": paciente.sector.nombre if paciente.sector else None,
        "direccion": paciente.direccion,  # solo la ven los roles que gestionan despachos
        "lineas": [{"medicamento": x.lote.medicamento.nombre, "lote": x.lote.codigo_lote, "cantidad": x.cantidad}
                   for x in disp.detalles],
        "fecha_salida": iso_utc(d.fecha_salida),
        "fecha_entrega": iso_utc(d.fecha_entrega),
        "recibe_nombre": d.recibe_nombre, "observacion": d.observacion,
        "estado_dispensacion": disp.estado,
    }


def listar_despachos(db: Session, estados: list[str] | None = None) -> list[DespachosDomicilio]:
    consulta = select(DespachosDomicilio).order_by(DespachosDomicilio.id_despacho.desc())
    if estados:
        consulta = consulta.where(DespachosDomicilio.estado.in_(estados))
    return list(db.scalars(consulta).unique())


def cambiar_estado(db: Session, usuario: Usuarios, id_despacho: int, nuevo: str, *,
                   recibe_nombre: str | None = None, observacion: str | None = None) -> DespachosDomicilio:
    despacho = db.get(DespachosDomicilio, id_despacho, with_for_update=True)
    if despacho is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El despacho no existe.")
    if despacho.dispensacion.estado == "ANULADA":
        raise ReglaNegocioError("DISPENSACION_ANULADA", "La entrega de este despacho fue anulada.")
    if nuevo not in TRANSICIONES.get(despacho.estado, set()):
        raise ReglaNegocioError("TRANSICION_INVALIDA",
                                f"Un despacho {despacho.estado.replace('_', ' ')} no puede pasar a {nuevo.replace('_', ' ')}.")
    observacion = (observacion or "").strip() or None
    if nuevo == "EN_RUTA":
        despacho.fecha_salida, despacho.id_responsable = ahora(), usuario.id_usuario
    elif nuevo == "ENTREGADO":
        if not (recibe_nombre or "").strip():
            raise ReglaNegocioError("RECEPTOR_REQUERIDO", "Indique el nombre de quien recibió en el domicilio.")
        despacho.fecha_entrega, despacho.recibe_nombre = ahora(), recibe_nombre.strip()
    elif nuevo == "FALLIDO" and not observacion:
        raise ReglaNegocioError("OBSERVACION_REQUERIDA", "Indique por qué no se pudo entregar.")
    anterior = despacho.estado
    despacho.estado = nuevo
    if observacion:
        despacho.observacion = observacion[:250]
    despacho.actualizado_por = usuario.id_usuario
    registrar_evento(db, tipo="DESPACHO_" + nuevo, entidad="despachos_domicilio", id_entidad=despacho.id_despacho,
                     id_usuario=usuario.id_usuario, anterior=anterior, observacion=observacion)
    return despacho
