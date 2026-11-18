"""Integración Paso B: recetas crónicas, entregas, quién retira, alergias, despacho y devoluciones."""

import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.api.deps import fecha_hoy
from app.main import app
from app.models import AsientosControlados, Dispensaciones, Lotes, MovimientosStock
from app.reloj import hoy

from ..conftest import FIRMA_QF

RUT_ROSA, RUT_LUIS, RUT_PATRICIA, RUT_JUAN, RUT_MARIA = "7654321-6", "8123456-6", "16234567-2", "9876543-3", "12345678-5"


@contextmanager
def dentro_de(dias: int):
    """Simula que la atención ocurre `dias` días después de hoy."""
    app.dependency_overrides[fecha_hoy] = lambda: hoy() + timedelta(days=dias)
    try:
        yield
    finally:
        app.dependency_overrides.pop(fecha_hoy, None)


def buscar(cliente, cabeceras, rut):
    return cliente.post("/api/pacientes/buscar", json={"rut": rut}, headers=cabeceras("TECNICO")).json()


def receta(cliente, cabeceras, rut, folio):
    return next(r for r in buscar(cliente, cabeceras, rut)["recetas"] if r["folio"] == folio)


def plan(cliente, cabeceras, id_detalle, cantidad):
    r = cliente.get(f"/api/dispensaciones/plan?id_detalle_receta={id_detalle}&cantidad={cantidad}",
                    headers=cabeceras("TECNICO"))
    assert r.status_code == 200, r.text
    return [p["codigo_lote"] for p in r.json()]


def entregar(cliente, cabeceras, rx, cantidades=None, rol="TECNICO", **extra):
    """Entrega la entrega en curso (o las cantidades indicadas) escaneando los lotes del plan FEFO."""
    lineas = []
    for i, d in enumerate(rx["detalles"]):
        cantidad = (cantidades or {}).get(i, d["saldo_entrega"])
        if cantidad:
            lineas.append({"id_detalle_receta": d["id_detalle_receta"], "cantidad": cantidad,
                           "lotes_escaneados": plan(cliente, cabeceras, d["id_detalle_receta"], cantidad)})
    return cliente.post("/api/dispensaciones", headers=cabeceras(rol), json={
        "id_receta": rx["id_receta"], "clave_idempotencia": uuid.uuid4().hex, "lineas": lineas, **extra})


# ------------------------------------------------------------ recetas crónicas
def test_it80_registrar_receta_cronica_por_entrega(cliente, cabeceras, datos):
    id_pac = buscar(cliente, cabeceras, "14141414-3")["paciente"]["id_paciente"]
    base = {"id_paciente": id_pac, "folio": "RX-8001", "fecha_emision": hoy().isoformat(),
            "tipo_receta": "CRONICA", "total_entregas": 3, "intervalo_dias": 30,
            "lineas": [{"id_medicamento": datos["medicamentos"]["LOS50"], "cant_por_entrega": 30,
                        "posologia": "1 comprimido cada 24 h"}]}
    r = cliente.post("/api/recetas", headers=cabeceras("TECNICO"), json=base)
    assert r.status_code == 201, r.text
    assert (r.json()["tipo_receta"], r.json()["total_entregas"], r.json()["entrega_actual"]) == ("CRONICA", 3, 1)
    assert (r.json()["detalles"][0]["cant_prescrita"], r.json()["detalles"][0]["saldo_entrega"]) == (90, 30)


@pytest.mark.parametrize("cambios,codigo", [
    ({"tipo_receta": "AGUDA"}, "ENTREGAS_INVALIDAS"),                       # aguda con 3 entregas
    ({"total_entregas": 1}, "ENTREGAS_INVALIDAS"),                           # crónica con 1 entrega
    ({"lineas": [{"id_medicamento": 0, "cant_por_entrega": 30, "cant_prescrita": 100,
                  "posologia": "1 al día"}]}, "CANTIDADES_INCONSISTENTES"),
])
def test_it81_estructura_de_receta_cronica_invalida(cliente, cabeceras, datos, cambios, codigo):
    id_pac = buscar(cliente, cabeceras, "14141414-3")["paciente"]["id_paciente"]
    cuerpo = {"id_paciente": id_pac, "folio": "RX-8002", "fecha_emision": hoy().isoformat(),
              "tipo_receta": "CRONICA", "total_entregas": 3,
              "lineas": [{"id_medicamento": datos["medicamentos"]["LOS50"], "cant_por_entrega": 30,
                          "posologia": "1 al día"}], **cambios}
    for linea in cuerpo["lineas"]:
        linea["id_medicamento"] = linea["id_medicamento"] or datos["medicamentos"]["LOS50"]
    assert cliente.post("/api/recetas", headers=cabeceras("QF"), json=cuerpo).json()["codigo"] == codigo


def test_it82_controlado_no_puede_ser_cronico(cliente, cabeceras, datos):
    id_pac = buscar(cliente, cabeceras, RUT_JUAN)["paciente"]["id_paciente"]
    r = cliente.post("/api/recetas", headers=cabeceras("QF"), json={
        "id_paciente": id_pac, "folio": "RX-8003", "fecha_emision": hoy().isoformat(), "tipo_receta": "CRONICA",
        "total_entregas": 3, "lineas": [{"id_medicamento": datos["medicamentos"]["CLZ2"], "cant_por_entrega": 30,
                                         "posologia": "1 en la noche"}]})
    assert r.json()["codigo"] == "RECETA_NO_RETENIDA"


# ------------------------------------------------------------------ entregas
def test_it83_no_se_adelanta_la_entrega_siguiente(cliente, cabeceras):
    rx = receta(cliente, cabeceras, RUT_LUIS, "RX-5002")
    r = entregar(cliente, cabeceras, rx, cantidades={0: 60, 1: 15})
    assert r.json()["codigo"] == "CANTIDAD_EXCEDE" and "entrega 1 de 3" in r.json()["detail"]


def test_it84_retiro_anticipado_se_bloquea_y_en_fecha_se_entrega(cliente, cabeceras):
    rx = receta(cliente, cabeceras, RUT_ROSA, "RX-5001")      # entrega 1 de 6 hecha hoy (seed)
    assert rx["retiro_desde"] == (hoy() + timedelta(days=25)).isoformat()
    r = entregar(cliente, cabeceras, rx)
    assert r.json()["codigo"] == "RETIRO_ANTICIPADO"

    with dentro_de(40):   # entrega 2: después de su fecha y a 43 días de la emisión (crónica: vigencia 180)
        rx = receta(cliente, cabeceras, RUT_ROSA, "RX-5001")
        assert rx["vigente"] and rx["entrega_actual"] == 2
        r = entregar(cliente, cabeceras, rx)
    assert r.status_code == 201, r.text
    assert (r.json()["numero_entrega"], r.json()["entregas_realizadas"]) == (2, 2)
    assert r.json()["rotulos"][0]["entrega"] == "2 de 6"


# ---------------------------------------------------------- alergias y retiro
def test_it85_alergias_deben_confirmarse(cliente, cabeceras):
    rx = receta(cliente, cabeceras, RUT_PATRICIA, "RX-5003")
    assert entregar(cliente, cabeceras, rx).json()["codigo"] == "ALERGIAS_SIN_CONFIRMAR"
    r = entregar(cliente, cabeceras, rx, confirma_alergias=True)
    assert r.status_code == 201, r.text


def test_it86_retiro_por_apoderado_registrado(cliente, cabeceras, db):
    luis = buscar(cliente, cabeceras, RUT_LUIS)
    url = f"/api/pacientes/{luis['paciente']['id_paciente']}/apoderados"
    apoderado = {"rut": "12345678-5", "nombre": "María González", "parentesco": "Cónyuge o pareja"}
    r = cliente.post(url, headers=cabeceras("TECNICO"), json=apoderado)
    assert r.status_code == 201 and r.json()["rut"] == "12.345.***-5" and r.json()["vigente"]
    assert cliente.post(url, headers=cabeceras("TECNICO"), json=apoderado).json()["codigo"] == "APODERADO_DUPLICADO"
    propio = cliente.post(url, headers=cabeceras("TECNICO"), json={**apoderado, "rut": RUT_LUIS})
    assert propio.json()["codigo"] == "APODERADO_ES_PACIENTE"

    rx = receta(cliente, cabeceras, RUT_LUIS, "RX-5002")
    entrega = entregar(cliente, cabeceras, rx, retira_tipo="APODERADO", id_apoderado=r.json()["id_apoderado"])
    assert entrega.status_code == 201, entrega.text
    disp = db.get(Dispensaciones, entrega.json()["id_dispensacion"])
    assert (disp.retira_tipo, disp.relacion, disp.rut_retira_enmascarado) == ("APODERADO", "Cónyuge o pareja",
                                                                              "12.345.***-5")


def test_it87_apoderado_ajeno_o_dado_de_baja_no_retira(cliente, cabeceras):
    rosa = buscar(cliente, cabeceras, RUT_ROSA)
    id_carmen = rosa["apoderados"][0]["id_apoderado"]
    rx = receta(cliente, cabeceras, RUT_LUIS, "RX-5002")
    ajeno = entregar(cliente, cabeceras, rx, retira_tipo="APODERADO", id_apoderado=id_carmen)
    assert ajeno.json()["codigo"] == "APODERADO_INVALIDO"
    baja = cliente.post(f"/api/apoderados/{id_carmen}/baja", headers=cabeceras("TECNICO"),
                        json={"motivo": "La hija dejó de ser cuidadora"})
    assert baja.status_code == 200 and baja.json()["activo"] is False
    assert buscar(cliente, cabeceras, RUT_ROSA)["apoderados"] == []


def test_it88_controlado_retirado_por_el_titular(cliente, cabeceras):
    rx = receta(cliente, cabeceras, RUT_JUAN, "RX-1003")
    sin_rut = entregar(cliente, cabeceras, rx, rol="QF", retira_tipo="PACIENTE", firma_qf=FIRMA_QF)
    assert sin_rut.json()["codigo"] == "IDENTIFICACION_REQUERIDA"
    otro_rut = entregar(cliente, cabeceras, rx, rol="QF", retira_tipo="PACIENTE", rut_retira=RUT_MARIA,
                        firma_qf=FIRMA_QF)
    assert otro_rut.json()["codigo"] == "RUT_NO_COINCIDE"
    r = entregar(cliente, cabeceras, rx, rol="QF", retira_tipo="PACIENTE", rut_retira=RUT_JUAN, firma_qf=FIRMA_QF)
    assert r.status_code == 201, r.text
    libro = cliente.get("/api/controlados/libro", headers=cabeceras("QF")).json()
    assert [a for a in libro if a["tipo"] == "SALIDA"][0]["contenido"]["relacion"] == "Titular"


# ---------------------------------------------------------------- despachos
def test_it89_despacho_a_domicilio_y_sus_transiciones(cliente, cabeceras):
    luis = receta(cliente, cabeceras, RUT_LUIS, "RX-5002")
    assert entregar(cliente, cabeceras, luis, a_domicilio=True).json()["codigo"] == "DOMICILIO_SOLO_POSTRADO"

    with dentro_de(26):
        rx = receta(cliente, cabeceras, RUT_ROSA, "RX-5001")
        r = entregar(cliente, cabeceras, rx, a_domicilio=True)
    assert r.status_code == 201, r.text
    url = f"/api/despachos/{r.json()['id_despacho']}/estado"
    tens = cabeceras("TECNICO")
    assert cliente.post(url, headers=tens, json={"estado": "ENTREGADO", "recibe_nombre": "Rosa"}).json()["codigo"] \
        == "TRANSICION_INVALIDA"
    assert cliente.post(url, headers=tens, json={"estado": "EN_RUTA"}).json()["estado"] == "EN_RUTA"
    assert cliente.post(url, headers=tens, json={"estado": "FALLIDO"}).json()["codigo"] == "OBSERVACION_REQUERIDA"
    assert cliente.post(url, headers=tens, json={"estado": "FALLIDO",
                                                 "observacion": "Nadie en el domicilio"}).json()["estado"] == "FALLIDO"
    cliente.post(url, headers=tens, json={"estado": "EN_RUTA"})
    assert cliente.post(url, headers=tens, json={"estado": "ENTREGADO"}).json()["codigo"] == "RECEPTOR_REQUERIDO"
    entregado = cliente.post(url, headers=tens, json={"estado": "ENTREGADO", "recibe_nombre": "Carmen Fuentes"})
    assert entregado.json()["estado"] == "ENTREGADO" and entregado.json()["fecha_entrega"]

    anular = cliente.post(f"/api/dispensaciones/{r.json()['id_dispensacion']}/anular", headers=cabeceras("QF"),
                          json={"motivo": "Se despachó la receta equivocada"})
    assert anular.json()["codigo"] == "DESPACHO_EN_CURSO"


def test_it90_listado_de_despachos_solo_para_quien_los_gestiona(cliente, cabeceras):
    lista = cliente.get("/api/despachos?estado=EN_RUTA", headers=cabeceras("TECNICO")).json()
    assert len(lista) == 1 and lista[0]["paciente"] == "Rosa Fuentes Muñoz" and lista[0]["direccion"]
    assert cliente.get("/api/despachos", headers=cabeceras("BODEGUERO")).status_code == 403


# -------------------------------------------------------------- devoluciones
def _stock(db, codigo):
    db.expire_all()
    return db.scalar(select(Lotes.unidades_disp).where(Lotes.codigo_lote == codigo))


def test_it91_devolucion_con_reingreso_y_descarte(cliente, cabeceras, db):
    rx = receta(cliente, cabeceras, RUT_MARIA, "RX-1001")
    r = entregar(cliente, cabeceras, rx, cantidades={0: 30, 1: 0})
    assert r.status_code == 201, r.text
    linea = cliente.get("/api/dispensaciones", headers=cabeceras("QF")).json()[0]["lineas"][0]
    assert _stock(db, "L-2502") == 30

    base = {"id_detalle_disp": linea["id_detalle_disp"], "motivo": "Cambio de tratamiento indicado por el médico"}
    assert cliente.post("/api/devoluciones", headers=cabeceras("TECNICO"),
                        json={**base, "cantidad": 10, "destino": "REINGRESO"}).status_code == 403
    reingreso = cliente.post("/api/devoluciones", headers=cabeceras("QF"),
                             json={**base, "cantidad": 10, "destino": "REINGRESO"})
    assert reingreso.status_code == 201, reingreso.text
    assert _stock(db, "L-2502") == 40
    mov = db.scalars(select(MovimientosStock).where(MovimientosStock.tipo == "DEVOLUCION")).one()
    assert (mov.cantidad, mov.saldo_resultante) == (10, 40)

    exceso = cliente.post("/api/devoluciones", headers=cabeceras("QF"), json={**base, "cantidad": 25, "destino": "DESCARTE"})
    assert exceso.json()["codigo"] == "CANTIDAD_INVALIDA"
    descarte = cliente.post("/api/devoluciones", headers=cabeceras("QF"), json={**base, "cantidad": 5, "destino": "DESCARTE"})
    assert descarte.status_code == 201 and _stock(db, "L-2502") == 40

    anular = cliente.post(f"/api/dispensaciones/{r.json()['id_dispensacion']}/anular", headers=cabeceras("QF"),
                          json={"motivo": "Intento de anular tras la devolución"})
    assert anular.json()["codigo"] == "TIENE_DEVOLUCIONES"


def test_it92_reingreso_a_lote_en_merma_no_se_permite(cliente, cabeceras, db):
    rx = receta(cliente, cabeceras, RUT_MARIA, "RX-1001")
    entregar(cliente, cabeceras, rx, cantidades={0: 30, 1: 0})
    linea = cliente.get("/api/dispensaciones", headers=cabeceras("QF")).json()[0]["lineas"][0]
    lote = next(l for l in cliente.get("/api/lotes", headers=cabeceras("QF")).json() if l["codigo_lote"] == "L-2502")
    cliente.post(f"/api/lotes/{lote['id_lote']}/merma", headers=cabeceras("QF"),
                 json={"cantidad": lote["unidades_disp"], "motivo": "DANO"})
    r = cliente.post("/api/devoluciones", headers=cabeceras("QF"), json={
        "id_detalle_disp": linea["id_detalle_disp"], "cantidad": 5, "destino": "REINGRESO",
        "motivo": "El paciente devolvió el envase sin abrir"})
    assert r.json()["codigo"] == "REINGRESO_NO_PERMITIDO"


def test_it93_devolucion_de_controlado_queda_en_el_libro(cliente, cabeceras, db):
    rx = receta(cliente, cabeceras, RUT_JUAN, "RX-1003")
    entregar(cliente, cabeceras, rx, rol="QF", rut_retira=RUT_MARIA, relacion="Hija", firma_qf=FIRMA_QF)
    linea = cliente.get("/api/dispensaciones", headers=cabeceras("QF")).json()[0]["lineas"][0]
    base = {"id_detalle_disp": linea["id_detalle_disp"], "cantidad": 10, "destino": "DESCARTE",
            "motivo": "Fallecimiento del paciente: entrega de la familia"}
    assert cliente.post("/api/devoluciones", headers=cabeceras("QF"), json=base).status_code == 201
    tipos = db.scalars(select(AsientosControlados.tipo).order_by(AsientosControlados.nro_asiento)).all()
    assert tipos[-2:] == ["SALIDA", "DEVOLUCION"]
    assert cliente.get("/api/controlados/verificar", headers=cabeceras("QF")).json()["integra"] is True
    segunda = cliente.post("/api/devoluciones", headers=cabeceras("QF"), json={**base, "cantidad": 5})
    assert segunda.json()["codigo"] == "DEVOLUCION_CONTROLADO_REGISTRADA"
