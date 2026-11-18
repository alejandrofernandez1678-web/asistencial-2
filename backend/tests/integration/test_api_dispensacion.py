"""Integración: dispensación con FEFO, controlados, anulación y libro digital."""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import AsientosControlados, Lotes, MovimientosStock

from ..conftest import FIRMA_QF


def clave():
    return uuid.uuid4().hex


def stock_lote(db, codigo):
    db.expire_all()
    return db.scalar(select(Lotes.unidades_disp).where(Lotes.codigo_lote == codigo))


def dispensar(cliente, cabeceras, datos, folio, lineas, rol="TECNICO", **extra):
    detalles = datos["detalles"][folio]
    cuerpo = {"id_receta": datos["recetas"][folio], "clave_idempotencia": extra.pop("clave", clave()),
              "lineas": [{"id_detalle_receta": detalles[i], "cantidad": c, "lotes_escaneados": l}
                         for i, c, l in lineas], **extra}
    return cliente.post("/api/dispensaciones", json=cuerpo, headers=cabeceras(rol))


# ----------------------------------------------------------- flujo normal
def test_it10_plan_fefo_indica_lote_y_casillero(cliente, cabeceras, datos):
    r = cliente.get(f"/api/dispensaciones/plan?id_detalle_receta={datos['detalles']['RX-1001'][0]}&cantidad=30",
                    headers=cabeceras("TECNICO"))
    assert r.json() == [{"codigo_lote": "L-2502", "ubicacion": "B-03", "cantidad": 30,
                         "fecha_vencimiento": r.json()[0]["fecha_vencimiento"]}]


def test_it11_dispensacion_correcta_descuenta_genera_rotulo_y_kardex(cliente, cabeceras, datos, db):
    r = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 30, ["L-2502"])])
    assert r.status_code == 201, r.text
    assert r.json()["rotulos"][0]["lote"] == "L-2502" and r.json()["estado_receta"] == "PARCIAL"
    assert stock_lote(db, "L-2502") == 30
    mov = db.scalars(select(MovimientosStock).where(MovimientosStock.tipo == "DISPENSACION",
                                                    MovimientosStock.referencia_id == r.json()["id_dispensacion"])).one()
    assert (mov.cantidad, mov.saldo_resultante) == (-30, 30)


def test_it12_dispensacion_reparte_entre_dos_lotes(cliente, cabeceras, datos, db):
    # Se pide más de lo que tiene el primer lote FEFO: 60 de L-2502 y 10 de L-2507 (receta de 30 + receta nueva no aplica)
    r = dispensar(cliente, cabeceras, datos, "RX-1001", [(1, 60, ["M-2509"])])
    assert r.status_code == 201  # M-2501 no es dispensable (25 días), FEFO salta a M-2509
    assert stock_lote(db, "M-2501") == 50 and stock_lote(db, "M-2509") == 340


# --------------------------------------------------------- reglas que bloquean
@pytest.mark.parametrize("escaneado,codigo", [
    (["L-2507"], "FEFO"),                    # lote más nuevo
    (["L-2411"], "LOTE_NO_DISPENSABLE"),     # vence en 9 días (RN-02)
    (["M-2509"], "LOTE_OTRO_MEDICAMENTO"),
    ([], "ESCANEO_INCOMPLETO"),
])
def test_it13_escaneo_incorrecto_bloquea_y_no_descuenta(cliente, cabeceras, datos, db, escaneado, codigo):
    r = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 30, escaneado)])
    assert r.status_code == 422 and r.json()["codigo"] == codigo
    assert stock_lote(db, "L-2502") == 60


def test_it14_receta_vencida_se_rechaza(cliente, cabeceras, datos):
    r = dispensar(cliente, cabeceras, datos, "RX-1002", [(0, 30, ["L-2502"])])
    assert r.json()["codigo"] == "RECETA_VENCIDA"


def test_it15_no_se_entrega_mas_de_lo_prescrito(cliente, cabeceras, datos):
    r = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 31, ["L-2502"])])
    assert r.json()["codigo"] == "CANTIDAD_EXCEDE"


def test_it16_atomicidad_si_una_linea_falla_no_se_descuenta_ninguna(cliente, cabeceras, datos, db):
    r = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 30, ["L-2502"]), (1, 60, ["M-2501"])])
    assert r.status_code == 422
    assert stock_lote(db, "L-2502") == 60  # la primera línea, válida, tampoco se descontó


def test_it17_reintento_con_misma_clave_no_descuenta_dos_veces(cliente, cabeceras, datos, db):
    k = clave()
    primera = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 10, ["L-2502"])], clave=k)
    segunda = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 10, ["L-2502"])], clave=k)
    assert primera.status_code == segunda.status_code == 201
    assert segunda.json()["repetida"] is True
    assert stock_lote(db, "L-2502") == 50


# --------------------------------------------------------------- controlados
def test_it18_controlado_sin_firma_o_con_pin_incorrecto_se_rechaza(cliente, cabeceras, datos):
    base = {"rut_retira": "12345678-5", "relacion": "Hija"}
    sin_firma = dispensar(cliente, cabeceras, datos, "RX-1003", [(0, 30, ["C-2504"])], **base)
    pin_malo = dispensar(cliente, cabeceras, datos, "RX-1003", [(0, 30, ["C-2504"])], **base,
                         firma_qf={**FIRMA_QF, "pin": "0000"})
    assert sin_firma.json()["codigo"] == "FIRMA_QF_REQUERIDA"
    assert pin_malo.json()["codigo"] == "FIRMA_QF_INVALIDA"


def test_it19_controlado_con_firma_crea_asiento_integro(cliente, cabeceras, datos, db):
    r = dispensar(cliente, cabeceras, datos, "RX-1003", [(0, 30, ["C-2504"])],
                  rut_retira="12345678-5", relacion="Hija", firma_qf=FIRMA_QF)
    assert r.status_code == 201, r.text
    libro = cliente.get("/api/controlados/libro", headers=cabeceras("QF")).json()
    assert [a["tipo"] for a in libro] == ["INGRESO", "INGRESO", "INGRESO", "SALIDA"]   # recepciones del seed
    salida = libro[-1]["contenido"]
    assert salida["rut_retira"] == "12.345.***-5" and salida["cantidad"] == 30
    # D.S. 404/405 art. 18: prescriptor, paciente y domicilio, y el saldo del producto tras el egreso
    assert salida["prescriptor"] == "Dr. Andrés Molina Soto" and salida["domicilio"].startswith("Av. Los Carrera")
    assert salida["paciente"] == "Juan Pérez" and salida["saldo"] == 160 - 30
    assert cliente.get("/api/controlados/verificar", headers=cabeceras("QF")).json() == {
        "integra": True, "asientos_verificados": 4, "primer_asiento_alterado": None}


def test_it20_libro_y_kardex_son_de_solo_insercion(cliente, cabeceras, datos, db):
    dispensar(cliente, cabeceras, datos, "RX-1003", [(0, 30, ["C-2504"])],
              rut_retira="12345678-5", relacion="Hija", firma_qf=FIRMA_QF)
    for sentencia in ("UPDATE asientos_controlados SET contenido = '{}'",
                      "DELETE FROM asientos_controlados",
                      "UPDATE movimientos_stock SET cantidad = 1",
                      "DELETE FROM movimientos_stock"):
        with pytest.raises(IntegrityError, match="solo insercion"):
            db.execute(text(sentencia))
        db.rollback()


def test_it21_stock_negativo_imposible_a_nivel_de_base(db):
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE lotes SET unidades_disp = -1 WHERE codigo_lote = 'L-2502'"))
        db.flush()
    db.rollback()


# ------------------------------------------------------------------ anulación
def test_it22_anular_dispensacion_repone_stock_y_libera_receta(cliente, cabeceras, datos, db):
    id_disp = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 30, ["L-2502"])]).json()["id_dispensacion"]
    r = cliente.post(f"/api/dispensaciones/{id_disp}/anular",
                     json={"motivo": "Se registró al paciente equivocado"}, headers=cabeceras("QF"))
    assert r.status_code == 200 and r.json() == {"id_dispensacion": id_disp, "estado": "ANULADA",
                                                 "estado_receta": "PENDIENTE"}
    assert stock_lote(db, "L-2502") == 60
    tipos = db.scalars(select(MovimientosStock.tipo).join(Lotes).where(Lotes.codigo_lote == "L-2502")
                       .order_by(MovimientosStock.id_movimiento)).all()
    assert tipos == ["INGRESO", "DISPENSACION", "ANULACION_DISPENSACION"]


def test_it23_anulacion_exige_motivo_rol_y_no_se_repite(cliente, cabeceras, datos):
    id_disp = dispensar(cliente, cabeceras, datos, "RX-1001", [(0, 30, ["L-2502"])]).json()["id_dispensacion"]
    url = f"/api/dispensaciones/{id_disp}/anular"
    motivo = {"motivo": "Error de digitación en la cantidad"}
    assert cliente.post(url, json={"motivo": "error"}, headers=cabeceras("QF")).status_code == 422
    assert cliente.post(url, json=motivo, headers=cabeceras("TECNICO")).status_code == 403
    assert cliente.post(url, json=motivo, headers=cabeceras("QF")).status_code == 200
    assert cliente.post(url, json=motivo, headers=cabeceras("QF")).json()["codigo"] == "YA_ANULADA"


def test_it24_anular_controlado_crea_rectificacion_y_cadena_sigue_integra(cliente, cabeceras, datos, db):
    id_disp = dispensar(cliente, cabeceras, datos, "RX-1003", [(0, 30, ["C-2504"])], rut_retira="12345678-5",
                        relacion="Hija", firma_qf=FIRMA_QF).json()["id_dispensacion"]
    cliente.post(f"/api/dispensaciones/{id_disp}/anular", json={"motivo": "El paciente no retiró el medicamento"},
                 headers=cabeceras("QF"))
    asientos = db.scalars(select(AsientosControlados).order_by(AsientosControlados.nro_asiento)).all()
    assert [a.tipo for a in asientos][-2:] == ["SALIDA", "RECTIFICACION"]
    assert asientos[-1].id_asiento_origen == asientos[-2].id_asiento
    assert asientos[-1].contenido["saldo"] == 160   # el stock repuesto vuelve al saldo
    assert cliente.get("/api/controlados/verificar", headers=cabeceras("QF")).json()["integra"] is True
