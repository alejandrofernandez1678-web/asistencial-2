"""Integración Paso C: retiros del día, ficha, alertas, consulta pública, reportes CSV y rótulos."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.api.publico import limite_publico
from app.models import Dispensaciones, EventosPendientes
from app.reloj import hoy
from app.services.reportes import celda_segura

HOY = hoy().isoformat()


def login(cliente, rut):
    r = cliente.post("/api/auth/login", json={"rut": rut, "password": "Farmacia2026!"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ----------------------------------------------------------- retiros y ficha
def test_it100_retiros_del_dia_incluye_atrasados_y_excluye_futuros_y_vencidos(cliente, cabeceras):
    retiros = cliente.get("/api/recetas/retiros", headers=cabeceras("TECNICO")).json()
    folios = {r["folio"]: r for r in retiros}
    assert {"RX-1001", "RX-5002", "RX-5005"} <= set(folios)
    assert "RX-5001" not in folios and "RX-1002" not in folios   # próxima en 30 días / receta vencida
    assert folios["RX-1001"]["dias_atraso"] == 5 and folios["RX-5002"]["entrega_actual"] == 1
    proximos = {r["folio"] for r in cliente.get("/api/recetas/retiros?dias=30", headers=cabeceras("TECNICO")).json()}
    assert "RX-5001" in proximos
    assert [r["proxima_fecha_retiro"] for r in retiros] == sorted(r["proxima_fecha_retiro"] for r in retiros)


def test_it101_medico_ve_la_ficha_pero_no_los_retiros(cliente, cabeceras):
    medico = login(cliente, "13579246-2")
    ficha = cliente.post("/api/pacientes/buscar", json={"rut": "14141414-3"}, headers=medico)
    assert ficha.status_code == 200
    por_id = cliente.get(f"/api/pacientes/{ficha.json()['paciente']['id_paciente']}/ficha", headers=medico)
    assert por_id.json()["paciente"]["nombre"] == "Ana Torres"
    assert cliente.get("/api/recetas/retiros", headers=medico).status_code == 403
    assert cliente.post("/api/pacientes/buscar", json={"rut": "14141414-3"},
                        headers=cabeceras("BODEGUERO")).status_code == 403


# ------------------------------------------------------------------- alertas
def test_it102_alertas_de_vencimiento_y_stock_critico(cliente, cabeceras):
    alertas = cliente.get("/api/inventario/alertas", headers=cabeceras("BODEGUERO")).json()
    estados = {v["codigo_lote"]: v["estado"] for v in alertas["vencimientos"]}
    assert estados["L-2411"] == "RETIRO_OBLIGATORIO" and estados["M-2501"] == "NO_DISPENSABLE"
    assert estados["L-2502"] == "ALERTA" and "L-2507" not in estados
    criticos = [c["codigo"] for c in alertas["stock_critico"]]
    assert {"ATV20", "AML5"} <= set(criticos)
    deficits = [c["deficit"] for c in alertas["stock_critico"]]
    assert deficits == sorted(deficits, reverse=True) and alertas["resumen"]["STOCK_CRITICO"] == len(criticos)


# ---------------------------------------------------------- consulta pública
def test_it103_consulta_publica_sin_login_ni_cantidades_ni_controlados(cliente):
    limite_publico._historial.clear()
    r = cliente.get("/api/publico/disponibilidad")
    assert r.status_code == 200
    meds = {m["nombre"]: m for m in r.json()["medicamentos"]}
    assert "Clonazepam 2 mg comprimidos" not in meds
    assert meds["Atorvastatina 20 mg comprimidos"]["disponibilidad"] == "POCAS_UNIDADES"
    assert meds["Losartán 50 mg comprimidos"]["disponibilidad"] == "DISPONIBLE"
    assert all(set(m) == {"nombre", "principio_activo", "concentracion", "forma_farmaceutica", "programa", "es_ges",
                          "disponibilidad"} for m in meds.values())
    filtrado = cliente.get("/api/publico/disponibilidad?q=metfor").json()["medicamentos"]
    assert [m["principio_activo"] for m in filtrado] == ["Metformina"]


def test_it104_consulta_publica_limita_las_peticiones(cliente):
    limite_publico._historial.clear()
    try:
        for _ in range(limite_publico.maximo):
            assert cliente.get("/api/publico/disponibilidad").status_code == 200
        bloqueada = cliente.get("/api/publico/disponibilidad")
        assert bloqueada.status_code == 429 and int(bloqueada.headers["Retry-After"]) >= 1
    finally:
        limite_publico._historial.clear()


# ------------------------------------------------------------------- reportes
def test_it105_kardex_csv_con_stock_anterior_y_posterior(cliente, cabeceras, db):
    r = cliente.get(f"/api/reportes/kardex.csv?desde={HOY}&hasta={HOY}", headers=cabeceras("QF"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="kardex_' in r.headers["content-disposition"]
    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿Fecha;Medicamento;Lote;Tipo;Cantidad;Stock anterior;Stock posterior")
    assert ";L-2502;INGRESO;60;0;60;" in texto and ";DISPENSACION;-30;" in texto   # entrega del seed
    evento = db.scalars(select(EventosPendientes).where(EventosPendientes.tipo_evento == "REPORTE_EXPORTADO")).one()
    assert evento.payload["reporte"].startswith("kardex_")


def test_it106_reportes_validan_rango_y_permisos(cliente, cabeceras):
    ayer = (hoy() - timedelta(days=1)).isoformat()
    assert cliente.get(f"/api/reportes/kardex.csv?desde={HOY}&hasta={ayer}",
                       headers=cabeceras("QF")).json()["codigo"] == "RANGO_INVALIDO"
    assert cliente.get(f"/api/reportes/kardex.csv?desde={HOY}&hasta={HOY}",
                       headers=cabeceras("TECNICO")).status_code == 403
    assert cliente.get("/api/reportes/libro.csv", headers=cabeceras("BODEGUERO")).status_code == 403
    assert cliente.get("/api/reportes/libro.csv", headers=cabeceras("QF")).status_code == 200


def test_it107_vencimientos_y_entregas_por_programa_sin_datos_de_pacientes(cliente, cabeceras):
    venc = cliente.get("/api/reportes/vencimientos.csv?dias=60", headers=cabeceras("BODEGUERO")).content.decode()
    assert "L-2411" in venc and "L-2507" not in venc
    entregas = cliente.get(f"/api/reportes/entregas.csv?desde={HOY}&hasta={HOY}",
                           headers=cabeceras("ADMIN")).content.decode()
    assert "Diabetes;Glibenclamida 5 mg comprimidos;1;60" in entregas
    assert "Rosa" not in entregas and "7.654" not in entregas


@pytest.mark.parametrize("valor,esperado", [
    ("=HYPERLINK(\"http://x\")", "'=HYPERLINK(\"http://x\")"), ("+1+1", "'+1+1"), ("@SUM(A1)", "'@SUM(A1)"),
    ("-30", "-30"), ("Losartán", "Losartán"), (None, ""),
])
def test_it108_celdas_neutralizan_formulas(valor, esperado):
    assert celda_segura(valor) == esperado


def test_it109_formula_en_un_dato_no_se_ejecuta_en_el_csv(cliente, cabeceras):
    qf = cabeceras("QF")
    med = cliente.post("/api/medicamentos", headers=qf, json={
        "codigo": "XSS1", "nombre": "=HYPERLINK(\"http://malicioso\",\"clic\")", "unidades_envase": 1}).json()
    ubicacion = cliente.get("/api/catalogos", headers=qf).json()["ubicaciones"][0]["id_ubicacion"]
    cliente.post("/api/lotes", headers=qf, json={"id_medicamento": med["id_medicamento"], "codigo_lote": "X-1",
                                                "fecha_vencimiento": (hoy() + timedelta(days=400)).isoformat(),
                                                "unidades": 5, "id_ubicacion": ubicacion})
    texto = cliente.get(f"/api/reportes/kardex.csv?desde={HOY}&hasta={HOY}", headers=qf).content.decode()
    assert ";\"'=HYPERLINK" in texto            # la celda queda como texto: '=HYPERLINK(...)
    assert ";=HYPERLINK" not in texto and ';"=HYPERLINK' not in texto


# -------------------------------------------------------------------- rótulos
def test_it110_reimpresion_de_rotulos_de_una_entrega(cliente, cabeceras, db):
    disp = db.scalars(select(Dispensaciones)).first()   # entrega a domicilio del seed (RX-5001)
    r = cliente.get(f"/api/dispensaciones/{disp.id_dispensacion}/rotulos", headers=cabeceras("TECNICO")).json()
    assert r["folio"] == "RX-5001" and len(r["rotulos"]) == 3
    assert {x["entrega"] for x in r["rotulos"]} == {"1 de 6"} and r["rotulos"][0]["paciente"] == "Rosa Fuentes Muñoz"
