"""Pruebas unitarias de seguridad: hash de credenciales, JWT y matriz RBAC."""

from datetime import timedelta

import jwt
import pytest

from app.config import config
from app.reloj import ahora
from app.security.claves import hashear, hmac_rut, verificar
from app.security.rbac import MATRIZ_RBAC, Permisos, tiene_permiso
from app.security.tokens import emitir_token, leer_token


def test_hash_de_contrasena_verifica_y_usa_sal_aleatoria():
    h1, h2 = hashear("Clave-Segura-123"), hashear("Clave-Segura-123")
    assert h1 != h2  # sal distinta
    assert verificar("Clave-Segura-123", h1) and verificar("Clave-Segura-123", h2)
    assert not verificar("clave-segura-123", h1)


@pytest.mark.parametrize("almacenado", [None, "", "texto-plano", "md5$1$a$b"])
def test_hash_malformado_nunca_verifica(almacenado):
    assert not verificar("cualquiera", almacenado)


def test_hmac_rut_es_determinista_y_no_revela_el_rut():
    assert hmac_rut("12345678-5") == hmac_rut("12345678-5")
    assert "12345678" not in hmac_rut("12345678-5")


def test_token_valido_se_lee():
    datos = leer_token(emitir_token(7, "QF"))
    assert datos["sub"] == "7" and datos["rol"] == "QF"


def test_token_alterado_se_rechaza():
    token = emitir_token(7, "TECNICO")
    cabecera, cuerpo, firma = token.split(".")
    falso = jwt.encode({"sub": "7", "rol": "ADMIN", "iat": ahora(), "exp": ahora() + timedelta(minutes=5)},
                       "otro-secreto-cualquiera-de-32-bytes!!", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        leer_token(falso)
    with pytest.raises(jwt.InvalidTokenError):
        leer_token(f"{cabecera}.{cuerpo}.{firma[:-2]}xx")


def test_token_expirado_se_rechaza():
    expirado = jwt.encode({"sub": "1", "rol": "QF", "iat": ahora() - timedelta(hours=2),
                           "exp": ahora() - timedelta(hours=1)}, config.jwt_secreto, algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        leer_token(expirado)


def test_token_con_algoritmo_none_se_rechaza():
    sin_firma = jwt.encode({"sub": "1", "rol": "ADMIN", "iat": ahora(), "exp": ahora() + timedelta(minutes=5)},
                           None, algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        leer_token(sin_firma)


@pytest.mark.parametrize("rol,permiso,esperado", [
    ("TECNICO", Permisos.DISPENSAR, True),
    ("TECNICO", Permisos.VER_LIBRO, False),
    ("TECNICO", Permisos.ANULAR_DISPENSACION, False),
    ("BODEGUERO", Permisos.DISPENSAR, False),
    ("BODEGUERO", Permisos.GESTIONAR_LOTES, True),
    ("ADMIN", Permisos.DISPENSAR, False),          # separación de funciones
    ("QF", Permisos.GESTIONAR_USUARIOS, False),
    ("MEDICO", Permisos.REGISTRAR_RECETA, True),
    ("MEDICO", Permisos.DISPENSAR, False),          # quien prescribe no dispensa
    ("DESCONOCIDO", Permisos.VER_STOCK, False),    # rol inexistente: se deniega
])
def test_matriz_rbac(rol, permiso, esperado):
    assert tiene_permiso(rol, permiso) is esperado


def test_solo_el_qf_firma_controlados():
    assert [r for r, p in MATRIZ_RBAC.items() if Permisos.FIRMAR_CONTROLADOS in p] == ["QF"]
