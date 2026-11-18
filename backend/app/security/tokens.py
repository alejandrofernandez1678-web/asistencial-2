"""Emisión y validación de tokens JWT de sesión (HS256, expiración corta)."""

from datetime import timedelta

import jwt

from ..config import config
from ..reloj import ahora

_ALGORITMO = "HS256"


def emitir_token(id_usuario: int, rol: str) -> str:
    momento = ahora()
    datos = {"sub": str(id_usuario), "rol": rol, "iat": momento,
             "exp": momento + timedelta(minutes=config.jwt_minutos)}
    return jwt.encode(datos, config.jwt_secreto, algorithm=_ALGORITMO)


def leer_token(token: str) -> dict:
    """Lanza jwt.InvalidTokenError si el token es inválido, alterado o expiró."""
    return jwt.decode(token, config.jwt_secreto, algorithms=[_ALGORITMO],
                      options={"require": ["sub", "exp", "iat"]})
