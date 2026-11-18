"""Dependencias comunes de la API: sesión, usuario autenticado y permisos."""

from collections.abc import Callable
from datetime import date

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import obtener_sesion
from ..models import Usuarios
from ..reloj import hoy
from ..security.rbac import Permisos, tiene_permiso
from ..security.tokens import leer_token
from ..services.auditoria import registrar_evento

_bearer = HTTPBearer(auto_error=False)
_NO_AUTENTICADO = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada.",
                                headers={"WWW-Authenticate": "Bearer"})


def sesion(db: Session = Depends(obtener_sesion)) -> Session:
    return db


def fecha_hoy() -> date:
    return hoy()


def usuario_actual(credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
                   db: Session = Depends(sesion)) -> Usuarios:
    if credenciales is None:
        raise _NO_AUTENTICADO
    try:
        datos = leer_token(credenciales.credentials)
        usuario = db.get(Usuarios, int(datos["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        raise _NO_AUTENTICADO from None
    if usuario is None or not usuario.activo:  # un usuario dado de baja pierde el acceso de inmediato
        raise _NO_AUTENTICADO
    return usuario


def requiere(*permisos: Permisos) -> Callable[..., Usuarios]:
    """Exige al menos uno de los permisos indicados (p. ej. dispensar o recetar para ver la ficha)."""
    def _verificar(request: Request, usuario: Usuarios = Depends(usuario_actual),
                   db: Session = Depends(sesion)) -> Usuarios:
        if not any(tiene_permiso(usuario.rol.nombre, p) for p in permisos):
            registrar_evento(db, tipo="ACCESO_DENEGADO", entidad="permisos", id_entidad=None,
                             id_usuario=usuario.id_usuario, permiso="|".join(p.value for p in permisos),
                             ruta=request.url.path)
            db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene permiso para esta acción.")
        return usuario
    return _verificar
