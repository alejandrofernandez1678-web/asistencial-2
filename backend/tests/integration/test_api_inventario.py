"""Integración: lotes (ingreso, ajuste, anulación, merma) y baja lógica de medicamentos."""

from datetime import timedelta

from app.reloj import hoy


def ingresar(cliente, cabeceras, datos, **cambios):
    cuerpo = {"id_medicamento": datos["medicamentos"]["LOS50"], "codigo_lote": "L-NUEVO",
              "fecha_vencimiento": (hoy() + timedelta(days=400)).isoformat(), "unidades": 100,
              "id_ubicacion": datos["ubicaciones"]["A-01"], **cambios}
    return cliente.post("/api/lotes", json=cuerpo, headers=cabeceras("BODEGUERO"))


def lote_por_codigo(cliente, cabeceras, codigo):
    lotes = cliente.get("/api/lotes?incluir_cerrados=true", headers=cabeceras("QF")).json()
    return next(l for l in lotes if l["codigo_lote"] == codigo)


# ------------------------------------------------------------------- ingreso
def test_it30_ingreso_de_lote_registra_kardex(cliente, cabeceras, datos):
    r = ingresar(cliente, cabeceras, datos)
    assert r.status_code == 201 and r.json()["alertas"] == []
    kardex = cliente.get(f"/api/lotes/{r.json()['lote']['id_lote']}/kardex", headers=cabeceras("QF")).json()
    assert [(m["tipo"], m["cantidad"], m["saldo_resultante"]) for m in kardex] == [("INGRESO", 100, 100)]


def test_it31_ingreso_alerta_vencimiento_menor_a_6_meses(cliente, cabeceras, datos):
    r = ingresar(cliente, cabeceras, datos, fecha_vencimiento=(hoy() + timedelta(days=132)).isoformat())
    assert r.status_code == 201 and "menos de 6 meses" in r.json()["alertas"][0]


def test_it32_ingreso_rechaza_duplicado_vencido_y_controlado_fuera_de_caja(cliente, cabeceras, datos):
    assert ingresar(cliente, cabeceras, datos, codigo_lote="L-2502").json()["codigo"] == "LOTE_DUPLICADO"
    assert ingresar(cliente, cabeceras, datos, fecha_vencimiento=hoy().isoformat()).json()["codigo"] == "LOTE_VENCIDO"
    r = ingresar(cliente, cabeceras, datos, id_medicamento=datos["medicamentos"]["CLZ2"])
    assert r.json()["codigo"] == "UBICACION_CONTROLADO"


# -------------------------------------------- lote mal ingresado (retro MER)
def test_it33_ajuste_corrige_cantidad_mal_ingresada(cliente, cabeceras, datos):
    id_lote = ingresar(cliente, cabeceras, datos).json()["lote"]["id_lote"]
    r = cliente.post(f"/api/lotes/{id_lote}/ajuste",
                     json={"unidades_correctas": 90, "motivo": "Guía decía 90, se digitó 100"},
                     headers=cabeceras("BODEGUERO"))
    assert r.status_code == 200 and r.json()["unidades_disp"] == 90
    kardex = cliente.get(f"/api/lotes/{id_lote}/kardex", headers=cabeceras("QF")).json()
    assert [(m["tipo"], m["cantidad"]) for m in kardex] == [("INGRESO", 100), ("AJUSTE", -10)]


def test_it34_anular_lote_mal_ingresado_lo_da_de_baja_sin_borrarlo(cliente, cabeceras, datos):
    id_lote = ingresar(cliente, cabeceras, datos).json()["lote"]["id_lote"]
    r = cliente.post(f"/api/lotes/{id_lote}/anular", json={"motivo": "Lote ingresado al medicamento equivocado"},
                     headers=cabeceras("QF"))
    assert r.status_code == 200
    assert (r.json()["estado"], r.json()["unidades_disp"]) == ("ANULADO", 0)
    assert r.json()["motivo_anulacion"] == "Lote ingresado al medicamento equivocado"
    activos = cliente.get("/api/lotes", headers=cabeceras("QF")).json()
    assert all(l["id_lote"] != id_lote for l in activos)  # no aparece en la operación diaria...
    assert lote_por_codigo(cliente, cabeceras, "L-NUEVO")["estado"] == "ANULADO"  # ...pero sigue en el historial


def test_it35_no_se_anula_un_lote_ya_dispensado(cliente, cabeceras, datos):
    cliente.post("/api/dispensaciones", headers=cabeceras("TECNICO"), json={
        "id_receta": datos["recetas"]["RX-1001"], "clave_idempotencia": "clave-it35-0001",
        "lineas": [{"id_detalle_receta": datos["detalles"]["RX-1001"][0], "cantidad": 10,
                    "lotes_escaneados": ["L-2502"]}]})
    id_lote = lote_por_codigo(cliente, cabeceras, "L-2502")["id_lote"]
    r = cliente.post(f"/api/lotes/{id_lote}/anular", json={"motivo": "Intento de anular lote con salidas"},
                     headers=cabeceras("QF"))
    assert r.json()["codigo"] == "LOTE_CON_MOVIMIENTOS"


def test_it36_merma_total_cierra_el_lote(cliente, cabeceras, datos):
    id_lote = lote_por_codigo(cliente, cabeceras, "L-2411")["id_lote"]
    r = cliente.post(f"/api/lotes/{id_lote}/merma", json={"cantidad": 40, "motivo": "VENCIMIENTO"},
                     headers=cabeceras("BODEGUERO"))
    assert r.status_code == 201 and r.json()["lote"]["estado"] == "MERMA"
    exceso = cliente.post(f"/api/lotes/{id_lote}/merma", json={"cantidad": 1, "motivo": "VENCIMIENTO"},
                          headers=cabeceras("BODEGUERO"))
    assert exceso.json()["codigo"] == "LOTE_NO_EDITABLE"


# --------------------------------------- baja lógica de producto (retro MER)
def test_it37_medicamento_con_stock_no_se_puede_dar_de_baja(cliente, cabeceras, datos):
    r = cliente.post(f"/api/medicamentos/{datos['medicamentos']['LOS50']}/baja",
                     json={"motivo": "Descontinuado por el proveedor"}, headers=cabeceras("QF"))
    assert r.json()["codigo"] == "CON_STOCK" and "L-2502" in r.json()["detail"]


def test_it38_baja_y_reactivacion_de_medicamento(cliente, cabeceras, datos):
    qf = cabeceras("QF")
    nuevo = cliente.post("/api/medicamentos", headers=qf, json={
        "codigo": "ENA10", "nombre": "Enalapril 10 mg", "unidades_envase": 30}).json()
    url = f"/api/medicamentos/{nuevo['id_medicamento']}"
    baja = cliente.post(f"{url}/baja", json={"motivo": "Reemplazado por losartán en el arsenal"}, headers=qf)
    assert baja.status_code == 200 and baja.json()["activo"] is False and baja.json()["fecha_baja"]

    activos = [m["codigo"] for m in cliente.get("/api/medicamentos", headers=qf).json()]
    todos = [m["codigo"] for m in cliente.get("/api/medicamentos?incluir_inactivos=true", headers=qf).json()]
    assert "ENA10" not in activos and "ENA10" in todos
    r = ingresar(cliente, cabeceras, datos, id_medicamento=nuevo["id_medicamento"], codigo_lote="E-1")
    assert r.json()["codigo"] == "MEDICAMENTO_INACTIVO"

    assert cliente.post(f"{url}/reactivar", headers=qf).json()["activo"] is True


def test_it39_panel_de_stock_marca_quiebre_y_estados(cliente, cabeceras):
    panel = {f["codigo"]: f for f in cliente.get("/api/stock", headers=cabeceras("TECNICO")).json()}
    assert panel["ATV20"]["critico"] is True                         # 80 < umbral 100
    assert panel["LOS50"]["stock_dispensable"] == 360                # L-2411 (9 días) no cuenta
    assert panel["LOS50"]["unidades_por_estado"]["RETIRO_OBLIGATORIO"] == 40
