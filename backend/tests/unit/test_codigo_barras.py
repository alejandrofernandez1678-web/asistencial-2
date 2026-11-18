"""Reglas del código de barras EAN-13 de medicamentos (sin base de datos)."""

import pytest

from app.domain.codigo_barras import (codigo_interno, digito_verificador, es_codigo_interno, modulos_ean13,
                                      normalizar_ean13)
from app.domain.errores import ReglaNegocioError


@pytest.mark.parametrize("doce,dv", [("400638133393", "1"), ("780123456789", "4"), ("978030640615", "7"),
                                     ("200000000001", "5")])
def test_digito_verificador_ean13(doce, dv):
    assert digito_verificador(doce) == dv


def test_codigo_interno_usa_prefijo_reservado_y_es_valido():
    assert codigo_interno(1) == "2000000000015"
    assert codigo_interno(123) == "2000000001234"[:12] + digito_verificador("200000000123")
    assert es_codigo_interno(codigo_interno(42)) and normalizar_ean13(codigo_interno(42))


@pytest.mark.parametrize("codigo", ["4006381333932", "400638133393", "40063813339311", "ABCDEFGHIJKLM", ""])
def test_codigo_invalido_se_rechaza(codigo):
    with pytest.raises(ReglaNegocioError) as error:
        normalizar_ean13(codigo)
    assert error.value.codigo == "CODIGO_BARRAS_INVALIDO"


def test_modulos_ean13_coinciden_con_la_norma():
    # Referencia: símbolo de 4006381333931 generado con python-barcode 0.15.1.
    esperado = ("10100011010100111010111101111010001001011001101010100001010000101000010111010010000101100110101")
    assert modulos_ean13("4006381333931") == esperado
    assert len(modulos_ean13(codigo_interno(7))) == 95
