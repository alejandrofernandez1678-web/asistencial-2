"""Pruebas unitarias de las reglas de negocio (UT-01 a UT-18 del plan de pruebas).

No usan base de datos ni red: prueban la capa domain de forma aislada,
con énfasis en los valores límite de cada regla.
"""

from datetime import date, timedelta

import pytest

from app.domain.errores import ReglaNegocioError
from app.domain.fefo import LoteFEFO, planificar, validar_lote_escaneado
from app.domain.libro import HASH_GENESIS, AsientoVerificable, calcular_hash, verificar_cadena
from app.domain.lotes import EstadosLote, es_dispensable, estado_lote, sumar_meses, vencimiento_corto_en_recepcion
from app.domain.recetas import exigir_receta_vigente, generar_rotulo, pendiente, receta_vigente, requiere_fraccion
from app.domain.rut import enmascarar_rut, es_rut_valido, normalizar_rut

HOY = date(2026, 11, 17)
LOS, MET = 1, 2


def lotes():
    return [
        LoteFEFO(1, "L-2411", LOS, HOY + timedelta(days=9), 40, "A-02"),     # retiro obligatorio
        LoteFEFO(2, "L-2502", LOS, HOY + timedelta(days=45), 60, "B-03"),    # alerta (FEFO)
        LoteFEFO(3, "L-2507", LOS, HOY + timedelta(days=200), 300, "A-01"),  # vigente
        LoteFEFO(4, "M-2509", MET, HOY + timedelta(days=150), 400, "A-01"),
    ]


# ------------------------------------------------------- UT-01/02: RUT (RF-04)
@pytest.mark.parametrize("rut,esperado", [
    ("12.345.678-5", "12345678-5"),
    ("12345678-5", "12345678-5"),
    ("10000013-K", "10000013-K"),   # dígito verificador K
    ("10000013-k", "10000013-K"),   # K minúscula
])
def test_ut01_rut_valido_se_normaliza(rut, esperado):
    assert normalizar_rut(rut) == esperado


@pytest.mark.parametrize("rut", [
    "12345678-9",                   # dígito verificador incorrecto
    "12345678",                     # sin guion ni DV
    "1234-5",                       # cuerpo demasiado corto
    "12345678-5' OR '1'='1",        # intento de inyección (además excede el largo)
])
def test_ut02_rut_invalido_se_rechaza(rut):
    with pytest.raises(ReglaNegocioError, match="RUT_INVALIDO"):
        normalizar_rut(rut)
    assert not es_rut_valido(rut)


def test_ut02b_rut_texto_excesivo_se_rechaza_sin_procesar():
    assert not es_rut_valido("1" * 10_000)


def test_enmascarar_rut_oculta_digitos_centrales():
    assert enmascarar_rut("12345678-5") == "12.345.***-5"


# ------------------------------------- UT-03: estados de vencimiento (RF-03)
@pytest.mark.parametrize("dias,esperado", [
    (61, EstadosLote.VIGENTE),
    (60, EstadosLote.ALERTA),               # RN-01: límite de alerta
    (31, EstadosLote.ALERTA),
    (30, EstadosLote.NO_DISPENSABLE),       # RN-02: límite de dispensación
    (15, EstadosLote.NO_DISPENSABLE),
    (14, EstadosLote.RETIRO_OBLIGATORIO),   # RN-03: límite de retiro
])
def test_ut03_estado_por_dias_al_vencimiento(dias, esperado):
    assert estado_lote(HOY + timedelta(days=dias), 10, HOY) == esperado


def test_ut03b_lote_sin_unidades_esta_agotado():
    assert estado_lote(HOY + timedelta(days=200), 0, HOY) == EstadosLote.AGOTADO


@pytest.mark.parametrize("registro", ["ALERTA_SANITARIA", "MERMA", "ANULADO"])
def test_ut03c_estado_registrado_prevalece_y_no_es_dispensable(registro):
    estado = estado_lote(HOY + timedelta(days=200), 10, HOY, registro)
    assert estado == EstadosLote(registro)
    assert not es_dispensable(estado)


# -------------------------------------------- UT-04 a UT-07: FEFO (RF-02)
def test_ut04_fefo_omite_lotes_no_dispensables():
    plan = planificar(lotes(), LOS, 20, HOY)
    assert [a.lote.codigo_lote for a in plan] == ["L-2502"]  # L-2411 vence antes pero no es dispensable


def test_ut05_fefo_reparte_entre_lotes_en_orden_de_vencimiento():
    plan = planificar(lotes(), LOS, 100, HOY)
    assert [(a.lote.codigo_lote, a.cantidad) for a in plan] == [("L-2502", 60), ("L-2507", 40)]


def test_ut06_fefo_stock_insuficiente():
    with pytest.raises(ReglaNegocioError, match="STOCK_INSUFICIENTE"):
        planificar(lotes(), LOS, 361, HOY)


@pytest.mark.parametrize("cantidad", [0, -5])
def test_ut07_fefo_cantidad_invalida(cantidad):
    with pytest.raises(ReglaNegocioError, match="CANTIDAD_INVALIDA"):
        planificar(lotes(), LOS, cantidad, HOY)


def test_ut07b_fefo_desempata_por_id_de_lote():
    mismo_dia = [LoteFEFO(9, "X-9", LOS, HOY + timedelta(days=90), 5),
                 LoteFEFO(8, "X-8", LOS, HOY + timedelta(days=90), 5)]
    assert planificar(mismo_dia, LOS, 5, HOY)[0].lote.codigo_lote == "X-8"


# ------------------------------- UT-08 a UT-11: validación del escaneo (RN-06)
def _validar(codigo):
    plan = planificar(lotes(), LOS, 20, HOY)
    return validar_lote_escaneado(lotes(), LOS, codigo, plan, HOY)


def test_ut08_escaneo_lote_mas_nuevo_bloqueado():
    with pytest.raises(ReglaNegocioError, match="FEFO") as error:
        _validar("L-2507")
    assert "L-2502" in error.value.mensaje and "B-03" in error.value.mensaje


def test_ut09_escaneo_lote_por_vencer_bloqueado():
    with pytest.raises(ReglaNegocioError, match="LOTE_NO_DISPENSABLE"):
        _validar("L-2411")


def test_ut10_escaneo_lote_de_otro_medicamento_bloqueado():
    with pytest.raises(ReglaNegocioError, match="LOTE_OTRO_MEDICAMENTO"):
        _validar("M-2509")


def test_ut10b_escaneo_lote_inexistente_bloqueado():
    with pytest.raises(ReglaNegocioError, match="LOTE_DESCONOCIDO"):
        _validar("NO-EXISTE")


def test_ut11_escaneo_lote_correcto_aceptado():
    assert _validar("L-2502").cantidad == 20


# ------------------------------------------- UT-12/13: unidosis y rótulo (RF-01)
@pytest.mark.parametrize("cantidad,envase,fracciona", [(30, 30, False), (20, 30, True), (60, 30, False)])
def test_ut12_unidosis_detecta_fraccionamiento(cantidad, envase, fracciona):
    assert requiere_fraccion(cantidad, envase) is fracciona


def test_ut13_rotulo_contiene_datos_obligatorios():
    rotulo = generar_rotulo(medicamento="Losartán 50 mg", codigo_lote="L-2502",
                            fecha_vencimiento=HOY + timedelta(days=45), cantidad=20,
                            posologia="1 cada 24 h", paciente="María", programa=None)
    assert rotulo["lote"] == "L-2502" and rotulo["programa"] == "-"
    assert set(rotulo) >= {"medicamento", "lote", "vencimiento", "cantidad", "posologia", "paciente"}


# ------------------------------------- UT-14/15: receta y recepción (RF-06/07)
@pytest.mark.parametrize("dias,vigente", [(0, True), (30, True), (31, False), (-1, False)])
def test_ut14_vigencia_de_receta_30_dias(dias, vigente):
    assert receta_vigente(HOY - timedelta(days=dias), HOY) is vigente


def test_ut14b_receta_vencida_y_futura_lanzan_error_especifico():
    with pytest.raises(ReglaNegocioError, match="RECETA_VENCIDA"):
        exigir_receta_vigente(HOY - timedelta(days=31), HOY)
    with pytest.raises(ReglaNegocioError, match="RECETA_INVALIDA"):
        exigir_receta_vigente(HOY + timedelta(days=1), HOY)


def test_ut14c_pendiente_nunca_es_negativo():
    assert pendiente(30, 10) == 20 and pendiente(30, 30) == 0 and pendiente(30, 40) == 0


@pytest.mark.parametrize("meses,dias_extra,alerta", [(6, -1, True), (6, 0, False), (7, 0, False)])
def test_ut15_alerta_recepcion_menos_de_6_meses(meses, dias_extra, alerta):
    vencimiento = sumar_meses(HOY, meses) + timedelta(days=dias_extra)
    assert vencimiento_corto_en_recepcion(vencimiento, HOY) is alerta


def test_ut15b_sumar_meses_ajusta_fin_de_mes():
    assert sumar_meses(date(2026, 8, 31), 6) == date(2027, 2, 28)


# ------------------------------------------ UT-16 a UT-18: libro de controlados
def _cadena(n=3):
    asientos, previo = [], HASH_GENESIS
    for i in range(1, n + 1):
        contenido = {"nro": i, "lote": f"C-{i}", "cantidad": 10 * i}
        actual = calcular_hash(previo, contenido)
        asientos.append(AsientoVerificable(i, contenido, previo, actual))
        previo = actual
    return asientos


def test_ut16_cadena_integra_se_verifica():
    assert verificar_cadena(_cadena()) == (True, None)


def test_ut17_libro_detecta_alteracion_de_un_asiento():
    asientos = _cadena()
    alterado = AsientoVerificable(2, {**asientos[1].contenido, "cantidad": 2}, asientos[1].hash_previo,
                                  asientos[1].hash_actual)
    assert verificar_cadena([asientos[0], alterado, asientos[2]]) == (False, 2)


def test_ut18_libro_detecta_asiento_eliminado():
    asientos = _cadena()
    assert verificar_cadena([asientos[0], asientos[2]]) == (False, 3)


def test_ut18b_hash_independiente_del_orden_de_las_claves():
    assert calcular_hash("x", {"a": 1, "b": 2}) == calcular_hash("x", {"b": 2, "a": 1})
