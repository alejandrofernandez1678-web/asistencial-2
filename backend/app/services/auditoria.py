"""Registro de eventos de auditoría en la bandeja de salida (outbox).

El evento se agrega a la misma sesión que la operación de negocio, por lo
que se guarda en la misma transacción: si la operación falla, el evento
tampoco existe; si DynamoDB no está disponible, el evento espera aquí.
"""

from sqlalchemy.orm import Session

from ..models import EventosPendientes


def registrar_evento(db: Session, *, tipo: str, entidad: str, id_entidad: int | None,
                     id_usuario: int | None, **payload) -> None:
    db.add(EventosPendientes(tipo_evento=tipo, entidad=entidad, id_entidad=id_entidad,
                             id_usuario=id_usuario, payload=payload))
