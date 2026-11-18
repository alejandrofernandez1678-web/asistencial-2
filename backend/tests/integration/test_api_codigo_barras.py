"""Integración: código de barras EAN-13 de medicamentos."""

import pytest

NUEVO = {"codigo": "PAR500", "nombre": "Paracetamol 500 mg comprimidos", "unidades_envase": 20}


def medicamentos(cliente, cabeceras):
    return {m["codigo"]: m for m in cliente.get("/api/medicamentos", headers=cabeceras("QF")).json()}


def test_it50_todos_los_medicamentos_del_catalogo_tienen_codigo_de_barras(cliente, cabeceras):
    catalogo = medicamentos(cliente, cabeceras)
    codigos = [m["codigo_barras"] for m in catalogo.values()]
    assert all(c and len(c) == 13 and c.startswith("200") for c in codigos)
    assert len(set(codigos)) == len(codigos)


def test_it51_medicamento_nuevo_sin_codigo_recibe_uno_interno(cliente, cabeceras):
    r = cliente.post("/api/medicamentos", headers=cabeceras("QF"), json=NUEVO)
    assert r.status_code == 201, r.text
    assert r.json()["codigo_barras"] == "200" + f"{r.json()['id_medicamento']:09d}" + r.json()["codigo_barras"][-1]


def test_it52_medicamento_nuevo_con_codigo_del_fabricante(cliente, cabeceras):
    r = cliente.post("/api/medicamentos", headers=cabeceras("QF"), json={**NUEVO, "codigo_barras": "7801234567894"})
    assert r.status_code == 201, r.text
    assert r.json()["codigo_barras"] == "7801234567894"
    repetido = cliente.post("/api/medicamentos", headers=cabeceras("QF"),
                            json={**NUEVO, "codigo": "PAR1G", "codigo_barras": "7801234567894"})
    assert repetido.json()["codigo"] == "CODIGO_BARRAS_DUPLICADO"


@pytest.mark.parametrize("codigo_barras,status,codigo", [
    ("7801234567890", 422, "CODIGO_BARRAS_INVALIDO"),   # dígito verificador incorrecto
    ("2000000000992", 422, "CODIGO_BARRAS_RESERVADO"),  # rango interno con dígito válido
    ("78012345", 422, None),                            # largo inválido (lo rechaza el esquema)
])
def test_it53_codigo_de_barras_invalido_se_rechaza(cliente, cabeceras, codigo_barras, status, codigo):
    r = cliente.post("/api/medicamentos", headers=cabeceras("QF"), json={**NUEVO, "codigo_barras": codigo_barras})
    assert r.status_code == status
    if codigo:
        assert r.json()["codigo"] == codigo


def test_it54_se_puede_reemplazar_por_el_codigo_del_fabricante(cliente, cabeceras):
    los50 = medicamentos(cliente, cabeceras)["LOS50"]
    r = cliente.patch(f"/api/medicamentos/{los50['id_medicamento']}", headers=cabeceras("QF"),
                      json={"codigo_barras": "7801234567894"})
    assert r.status_code == 200, r.text
    assert medicamentos(cliente, cabeceras)["LOS50"]["codigo_barras"] == "7801234567894"
