"""Validación del RUT chileno (RF-04).

Se usa en el ingreso de pacientes, en quien retira un controlado y en el
inicio de sesión. Rechaza formatos inválidos y textos excesivos antes de
calcular el dígito verificador (módulo 11).
"""

import re

from .errores import ReglaNegocioError

_LARGO_MAXIMO = 12  # "12.345.678-K"
_PATRON = re.compile(r"^(\d{7,8})-([\dK])$")


def calcular_dv(cuerpo: str) -> str:
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def normalizar_rut(rut: str) -> str:
    """Devuelve el RUT en formato 12345678-K o lanza ReglaNegocioError."""
    if not isinstance(rut, str) or len(rut) > _LARGO_MAXIMO:
        raise ReglaNegocioError("RUT_INVALIDO", "El RUT tiene un largo inválido.")
    limpio = rut.strip().replace(".", "").upper()
    coincidencia = _PATRON.match(limpio)
    if not coincidencia:
        raise ReglaNegocioError("RUT_INVALIDO", "El RUT no tiene el formato 12345678-K.")
    cuerpo, dv = coincidencia.groups()
    if calcular_dv(cuerpo) != dv:
        raise ReglaNegocioError("RUT_INVALIDO", "El dígito verificador del RUT es incorrecto.")
    return f"{cuerpo}-{dv}"


def es_rut_valido(rut: str) -> bool:
    try:
        normalizar_rut(rut)
        return True
    except ReglaNegocioError:
        return False


def enmascarar_rut(rut_normalizado: str) -> str:
    """12345678-K -> 12.345.***-K (para mostrar sin exponer el dato completo)."""
    cuerpo, dv = rut_normalizado.split("-")
    visible = f"{int(cuerpo[:-3]):,}".replace(",", ".")
    return f"{visible}.***-{dv}"
