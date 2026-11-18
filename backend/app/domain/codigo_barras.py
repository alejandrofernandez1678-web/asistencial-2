"""Código de barras EAN-13 de cada medicamento.

Si el medicamento trae el código del fabricante (GTIN/EAN-13 impreso en la
caja) se valida su dígito verificador. Si no, se genera un código interno
con prefijo 200: GS1 reserva los prefijos 200-299 para uso interno, por lo
que nunca coincide con el código real de un producto.
"""

import re

from .errores import ReglaNegocioError

PREFIJO_INTERNO = "200"
_PATRON = re.compile(r"^\d{13}$")

# Tablas de codificación EAN-13 (conjuntos L, G y R) y paridad según el primer dígito.
_L = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
_G = ("0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111")
_R = ("1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100")
_PARIDAD = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")


def digito_verificador(doce_digitos: str) -> str:
    suma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(doce_digitos))
    return str((10 - suma % 10) % 10)


def normalizar_ean13(codigo: str) -> str:
    """Devuelve el código limpio o lanza ReglaNegocioError si no es un EAN-13 válido."""
    limpio = (codigo or "").strip().replace(" ", "")
    if not _PATRON.match(limpio):
        raise ReglaNegocioError("CODIGO_BARRAS_INVALIDO", "El código de barras debe tener 13 dígitos (EAN-13).")
    if digito_verificador(limpio[:12]) != limpio[12]:
        raise ReglaNegocioError("CODIGO_BARRAS_INVALIDO", "El dígito verificador del código de barras es incorrecto.")
    return limpio


def es_codigo_interno(codigo: str) -> bool:
    return codigo.startswith(PREFIJO_INTERNO)


def codigo_interno(id_medicamento: int) -> str:
    """200 + identificador con 9 dígitos + dígito verificador = 13 dígitos."""
    if not 0 < id_medicamento < 10**9:
        raise ValueError("Identificador fuera de rango para un código interno.")
    doce = f"{PREFIJO_INTERNO}{id_medicamento:09d}"
    return doce + digito_verificador(doce)


def modulos_ean13(codigo: str) -> str:
    """Las 95 barras del símbolo como texto de 0 y 1 (1 = barra negra).

    La interfaz dibuja el mismo patrón (frontend/codigo-barras.js); las pruebas
    comparan ambos para asegurar que lo impreso se puede escanear.
    """
    codigo = normalizar_ean13(codigo)
    paridad = _PARIDAD[int(codigo[0])]
    izquierda = "".join((_L if p == "L" else _G)[int(d)] for p, d in zip(paridad, codigo[1:7]))
    derecha = "".join(_R[int(d)] for d in codigo[7:])
    return "101" + izquierda + "01010" + derecha + "101"
