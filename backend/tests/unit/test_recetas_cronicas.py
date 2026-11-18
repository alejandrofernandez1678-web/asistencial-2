"""Reglas de entregas de recetas crónicas y separación del nombre del medicamento (sin base de datos)."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from app.domain.recetas import entregas_completas, proxima_fecha_retiro

HOY = date(2026, 11, 17)


@pytest.mark.parametrize("lineas,esperado", [
    ([(0, 30)], 0),
    ([(30, 30)], 1),
    ([(90, 30), (45, 15)], 3),
    ([(60, 30), (15, 15)], 1),      # a una línea le faltó stock: manda la más atrasada
    ([(29, 30)], 0),                 # entrega parcial: no cuenta como completa
    ([], 0),
])
def test_entregas_completas(lineas, esperado):
    assert entregas_completas(lineas) == esperado


@pytest.mark.parametrize("total,realizadas,ultima,esperado", [
    (6, 0, None, date(2026, 11, 10)),               # aún no retira: desde la emisión
    (6, 1, date(2026, 11, 17), date(2026, 12, 17)),  # siguiente entrega: 30 días después
    (6, 6, date(2026, 11, 17), None),                # receta completa
    (1, 1, date(2026, 11, 17), None),                # aguda ya entregada
])
def test_proxima_fecha_de_retiro(total, realizadas, ultima, esperado):
    assert proxima_fecha_retiro(fecha_emision=date(2026, 11, 10), total_entregas=total,
                                entregas_realizadas=realizadas, fecha_ultima_entrega=ultima,
                                intervalo_dias=30) == esperado


def _migracion_0002():
    ruta = Path(__file__).resolve().parents[2] / "migraciones" / "versions" / "0002_esquema_cesfam_v0_5.py"
    spec = importlib.util.spec_from_file_location("migracion_0002", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("nombre,esperado", [
    ("Losartán 50 mg comprimidos", ("Losartán", "50 mg", "COMPRIMIDO", "COMPRIMIDO")),
    ("Salbutamol 100 mcg inhalador", ("Salbutamol", "100 mcg", "INHALADOR", "INHALADOR")),
    ("Amoxicilina 250 mg/5 ml suspensión", ("Amoxicilina", "250 mg/5 ml", "SUSPENSION", "FRASCO")),
    ("Omeprazol 20 mg cápsulas", ("Omeprazol", "20 mg", "CAPSULA", "CAPSULA")),
    ("Vaselina", ("Vaselina", None, "OTRO", "UNIDAD")),
])
def test_migracion_separa_el_nombre_del_medicamento(nombre, esperado):
    assert _migracion_0002().separar_nombre(nombre) == esperado


# ------------------------------------------------------------- Paso B: reglas
from app.domain.errores import ReglaNegocioError  # noqa: E402
from app.domain.recetas import (LineaEntrega, entrega_en_curso_iniciada, exigir_fecha_de_retiro,  # noqa: E402
                                receta_vigente, saldo_entrega_actual, validar_estructura)


@pytest.mark.parametrize("tipo,realizadas,dias,vigente", [
    ("AGUDA", 0, 30, True), ("AGUDA", 0, 31, False),
    ("RETENIDA", 0, 31, False),
    ("CRONICA", 0, 31, False),            # la primera entrega también se retira dentro de 30 días
    ("CRONICA", 1, 120, True), ("CRONICA", 3, 181, False),
])
def test_vigencia_segun_tipo_de_receta(tipo, realizadas, dias, vigente):
    emision = date(2026, 1, 1)
    hoy = date.fromordinal(emision.toordinal() + dias)
    assert receta_vigente(emision, hoy, tipo, realizadas) is vigente


@pytest.mark.parametrize("tipo,total,controlados,codigo", [
    ("AGUDA", 3, False, "ENTREGAS_INVALIDAS"),
    ("CRONICA", 1, False, "ENTREGAS_INVALIDAS"),
    ("CRONICA", 7, False, "ENTREGAS_INVALIDAS"),
    ("CRONICA", 3, True, "RECETA_NO_RETENIDA"),   # D.S. 466: controlado = retenida y una entrega
    ("RETENIDA", 2, True, "ENTREGAS_INVALIDAS"),
])
def test_estructura_de_receta_invalida(tipo, total, controlados, codigo):
    with pytest.raises(ReglaNegocioError) as error:
        validar_estructura(tipo, total, 30, controlados)
    assert error.value.codigo == codigo


def test_saldo_de_la_entrega_en_curso_no_permite_adelantar():
    linea = LineaEntrega(cant_prescrita=90, cant_por_entrega=30, cant_entregada=30)
    assert saldo_entrega_actual(linea, entregas_realizadas=1) == 30
    parcial = LineaEntrega(cant_prescrita=90, cant_por_entrega=30, cant_entregada=40)
    assert saldo_entrega_actual(parcial, entregas_realizadas=1) == 20
    assert entrega_en_curso_iniciada([parcial], entregas_realizadas=1) is True
    assert entrega_en_curso_iniciada([linea], entregas_realizadas=1) is False


@pytest.mark.parametrize("hoy,iniciada,permitido", [
    (date(2026, 12, 11), False, False),   # 6 días antes de la fecha
    (date(2026, 12, 12), False, True),    # 5 días antes: tolerancia
    (date(2026, 12, 1), True, True),      # completar una entrega parcial: siempre
])
def test_retiro_anticipado(hoy, iniciada, permitido):
    if permitido:
        exigir_fecha_de_retiro(date(2026, 12, 17), hoy, iniciada)
    else:
        with pytest.raises(ReglaNegocioError, match="desde el 12-12-2026"):
            exigir_fecha_de_retiro(date(2026, 12, 17), hoy, iniciada)
