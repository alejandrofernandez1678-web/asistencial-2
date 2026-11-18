"""Hash de contraseñas y PIN con PBKDF2-HMAC-SHA256 (biblioteca estándar).

En producción la autenticación la hace Amazon Cognito (ADR del informe);
este módulo cubre el entorno local y la firma con PIN del Q.F.
"""

import base64
import hashlib
import hmac
import secrets

from ..config import config

_ALGORITMO = "pbkdf2_sha256"


def hashear(secreto: str, iteraciones: int | None = None) -> str:
    iteraciones = iteraciones or config.pbkdf2_iteraciones
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", secreto.encode(), sal, iteraciones)
    return "$".join([_ALGORITMO, str(iteraciones),
                     base64.b64encode(sal).decode(), base64.b64encode(derivada).decode()])


def verificar(secreto: str, almacenado: str | None) -> bool:
    if not almacenado:
        return False
    try:
        algoritmo, iteraciones, sal, esperado = almacenado.split("$")
    except ValueError:
        return False
    if algoritmo != _ALGORITMO:
        return False
    derivada = hashlib.pbkdf2_hmac("sha256", secreto.encode(), base64.b64decode(sal), int(iteraciones))
    return hmac.compare_digest(derivada, base64.b64decode(esperado))  # comparación en tiempo constante


def hmac_rut(rut_normalizado: str) -> str:
    """Huella del RUT para buscar pacientes sin guardar el RUT en claro."""
    return hmac.new(config.hmac_secreto.encode(), rut_normalizado.encode(), hashlib.sha256).hexdigest()
