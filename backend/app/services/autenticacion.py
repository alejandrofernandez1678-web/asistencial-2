"""Inicio de sesión con bloqueo por intentos fallidos (Tabla 23 del informe).

El mensaje de error es siempre el mismo, exista o no el usuario, para no
revelar qué RUT están registrados (enumeración de usuarios).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import config
from ..domain.errores import ReglaNegocioError
from ..domain.rut import normalizar_rut
from ..models import Usuarios
from ..reloj import ahora
from ..security.claves import verificar
from ..security.tokens import emitir_token
from .auditoria import registrar_evento

MENSAJE_GENERICO = "RUT o contraseña incorrectos."


def _como_utc(momento: datetime | None) -> datetime | None:
    if momento is not None and momento.tzinfo is None:  # SQLite devuelve fechas sin zona horaria
        return momento.replace(tzinfo=UTC)
    return momento


def autenticar(db: Session, rut: str, password: str) -> dict:
    """Devuelve el token o lanza ReglaNegocioError. Deja el resultado en la sesión, sin confirmar."""
    try:
        rut = normalizar_rut(rut)
    except ReglaNegocioError:
        raise ReglaNegocioError("CREDENCIALES", MENSAJE_GENERICO) from None

    usuario = db.scalar(select(Usuarios).where(Usuarios.rut == rut))
    if usuario is None or not usuario.activo:
        registrar_evento(db, tipo="LOGIN_FALLIDO", entidad="usuarios", id_entidad=None, id_usuario=None,
                         motivo="usuario inexistente o inactivo")
        raise ReglaNegocioError("CREDENCIALES", MENSAJE_GENERICO)

    momento = ahora()
    bloqueado_hasta = _como_utc(usuario.bloqueado_hasta)
    if bloqueado_hasta and bloqueado_hasta > momento:
        raise ReglaNegocioError("CUENTA_BLOQUEADA", "Cuenta bloqueada temporalmente por intentos fallidos.")

    if not verificar(password, usuario.password_hash):
        usuario.intentos_fallidos += 1
        bloquear = usuario.intentos_fallidos >= config.max_intentos_login
        if bloquear:
            usuario.bloqueado_hasta = momento + timedelta(minutes=config.minutos_bloqueo)
            usuario.intentos_fallidos = 0
        registrar_evento(db, tipo="LOGIN_FALLIDO", entidad="usuarios", id_entidad=usuario.id_usuario,
                         id_usuario=usuario.id_usuario, bloqueada=bloquear)
        raise ReglaNegocioError("CREDENCIALES", MENSAJE_GENERICO)

    usuario.intentos_fallidos, usuario.bloqueado_hasta, usuario.ultimo_acceso = 0, None, momento
    registrar_evento(db, tipo="LOGIN_OK", entidad="usuarios", id_entidad=usuario.id_usuario,
                     id_usuario=usuario.id_usuario)
    # "bearer" es el tipo de token de OAuth 2.0 (RFC 6750), no una contraseña: falso positivo de Bandit B105.
    return {"access_token": emitir_token(usuario.id_usuario, usuario.rol.nombre), "token_type": "bearer",  # nosec B105
            "usuario": {"id_usuario": usuario.id_usuario, "nombre": usuario.nombre, "rol": usuario.rol.nombre}}
