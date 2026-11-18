"""Configuración leída desde variables de entorno (archivo .env en desarrollo).

Ningún secreto se escribe en el código: en producción los valores vienen de
AWS Secrets Manager inyectados como variables de entorno.
"""

import os
import secrets
import warnings
from dataclasses import dataclass
from pathlib import Path


def _cargar_env(ruta: Path) -> None:
    if not ruta.exists():
        return
    # utf-8-sig: el Bloc de notas de Windows puede guardar el archivo con BOM
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip())


_cargar_env(Path(__file__).resolve().parents[1] / ".env")


def _secreto(nombre: str, entorno: str) -> str:
    valor = os.getenv(nombre)
    if valor:
        return valor
    if entorno == "produccion":
        raise RuntimeError(f"Falta la variable de entorno obligatoria {nombre}.")
    warnings.warn(f"{nombre} no está definida: se usa un valor aleatorio solo para desarrollo.", stacklevel=2)
    return secrets.token_urlsafe(48)


@dataclass(frozen=True)
class Config:
    entorno: str
    database_url: str
    jwt_secreto: str
    jwt_minutos: int
    hmac_secreto: str
    pbkdf2_iteraciones: int
    max_intentos_login: int
    minutos_bloqueo: int


def cargar_config() -> Config:
    entorno = os.getenv("SISGEF_ENTORNO", "desarrollo")
    return Config(
        entorno=entorno,
        database_url=os.getenv("SISGEF_DATABASE_URL", "sqlite:///./sisgef.db"),
        jwt_secreto=_secreto("SISGEF_JWT_SECRETO", entorno),
        jwt_minutos=int(os.getenv("SISGEF_JWT_MINUTOS", "30")),
        hmac_secreto=_secreto("SISGEF_HMAC_SECRETO", entorno),
        pbkdf2_iteraciones=int(os.getenv("SISGEF_PBKDF2_ITERACIONES", "600000")),
        max_intentos_login=int(os.getenv("SISGEF_MAX_INTENTOS_LOGIN", "5")),
        minutos_bloqueo=int(os.getenv("SISGEF_MINUTOS_BLOQUEO", "15")),
    )


config = cargar_config()
