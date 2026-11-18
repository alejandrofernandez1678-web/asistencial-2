"""Integración: registro de recetas (asignar medicamentos a un paciente)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import EventosPendientes
from app.reloj import hoy

from ..conftest import FIRMA_QF


def id_paciente(cliente, cabeceras, rut="14141414-3"):
    return cliente.post("/api/pacientes/buscar", json={"rut": rut}, headers=cabeceras("TECNICO")).json()["paciente"]["id_paciente"]


DATOS_LIBRO = {"prescriptor_nombre": "Dr. Andrés Molina Soto", "prescriptor_rut": "10203040-0",
               "domicilio_paciente": "Av. Los Carrera 1550, depto. 32"}


def receta(datos, id_pac, *lineas, **extra):
    return {"id_paciente": id_pac, "folio": extra.pop("folio", "RX-2001"), "fecha_emision": hoy().isoformat(),
            "lineas": [{"id_medicamento": datos["medicamentos"][c], "cant_prescrita": n, "posologia": p}
                       for c, n, p in lineas], **extra}


def test_it40_tecnico_asigna_medicamentos_y_la_receta_queda_lista_para_dispensar(cliente, cabeceras, datos, db):
    id_pac = id_paciente(cliente, cabeceras)
    r = cliente.post("/api/recetas", headers=cabeceras("TECNICO"), json=receta(
        datos, id_pac, ("MET850", 60, "1 comprimido cada 12 h"), ("LOS50", 30, "1 comprimido cada 24 h")))
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["folio"] == "RX-2001" and cuerpo["estado"] == "PENDIENTE" and cuerpo["vigente"]
    assert [(d["medicamento"], d["pendiente"]) for d in cuerpo["detalles"]] == [
        ("Metformina 850 mg comprimidos", 60), ("Losartán 50 mg comprimidos", 30)]

    paciente = cliente.post("/api/pacientes/buscar", json={"rut": "14141414-3"}, headers=cabeceras("TECNICO")).json()
    assert paciente["recetas"][0]["folio"] == "RX-2001"
    evento = db.scalars(select(EventosPendientes).where(EventosPendientes.tipo_evento == "RECETA_REGISTRADA")).one()
    assert evento.payload["medicamentos"] == ["MET850", "LOS50"]

    # La receta nueva se dispensa con el flujo FEFO de siempre.
    disp = cliente.post("/api/dispensaciones", headers=cabeceras("TECNICO"), json={
        "id_receta": cuerpo["id_receta"], "clave_idempotencia": uuid.uuid4().hex,
        "lineas": [{"id_detalle_receta": cuerpo["detalles"][1]["id_detalle_receta"], "cantidad": 30,
                    "lotes_escaneados": ["L-2502"]}]})
    assert disp.status_code == 201, disp.text
    assert disp.json()["estado_receta"] == "PARCIAL"


def test_it41_qf_registra_receta_de_controlado_retenida_y_se_dispensa(cliente, cabeceras, datos):
    id_pac = id_paciente(cliente, cabeceras)
    r = cliente.post("/api/recetas", headers=cabeceras("QF"), json=receta(
        datos, id_pac, ("CLZ2", 30, "1 comprimido en la noche"), es_retenida=True, **DATOS_LIBRO))
    assert r.status_code == 201, r.text
    disp = cliente.post("/api/dispensaciones", headers=cabeceras("QF"), json={
        "id_receta": r.json()["id_receta"], "clave_idempotencia": uuid.uuid4().hex,
        "lineas": [{"id_detalle_receta": r.json()["detalles"][0]["id_detalle_receta"], "cantidad": 30,
                    "lotes_escaneados": ["C-2504"]}],
        "rut_retira": "14141414-3", "relacion": "Titular", "firma_qf": FIRMA_QF})
    assert disp.status_code == 201, disp.text


@pytest.mark.parametrize("rol,extra,codigo", [
    ("QF", {}, "RECETA_NO_RETENIDA"),                     # controlado sin retener
    ("TECNICO", {"es_retenida": True}, "REQUIERE_QF"),    # el técnico no registra controlados
])
def test_it42_reglas_de_controlados(cliente, cabeceras, datos, rol, extra, codigo):
    id_pac = id_paciente(cliente, cabeceras)
    r = cliente.post("/api/recetas", headers=cabeceras(rol),
                     json=receta(datos, id_pac, ("CLZ2", 30, "1 comprimido en la noche"), **extra))
    assert r.status_code == 422 and r.json()["codigo"] == codigo


@pytest.mark.parametrize("cambios,codigo", [
    ({"folio": "RX-1001"}, "FOLIO_DUPLICADO"),
    ({"fecha_emision": (hoy() + timedelta(days=1)).isoformat()}, "RECETA_INVALIDA"),
    ({"fecha_emision": (hoy() - timedelta(days=31)).isoformat()}, "RECETA_VENCIDA"),
    ({"id_paciente": 9999}, "NO_ENCONTRADO"),
])
def test_it43_datos_de_receta_invalidos_se_rechazan(cliente, cabeceras, datos, cambios, codigo):
    id_pac = id_paciente(cliente, cabeceras)
    cuerpo = {**receta(datos, id_pac, ("LOS50", 30, "1 comprimido cada 24 h")), **cambios}
    r = cliente.post("/api/recetas", headers=cabeceras("TECNICO"), json=cuerpo)
    assert r.json()["codigo"] == codigo


def test_it44_medicamento_repetido_o_dado_de_baja_se_rechaza(cliente, cabeceras, datos):
    id_pac = id_paciente(cliente, cabeceras)
    repetido = receta(datos, id_pac, ("LOS50", 30, "1 cada 24 h"), ("LOS50", 10, "1 cada 12 h"))
    r = cliente.post("/api/recetas", headers=cabeceras("TECNICO"), json=repetido)
    assert r.json()["codigo"] == "LINEA_REPETIDA"

    # ATV20 tiene stock: se retira a merma para poder darlo de baja.
    lote = next(l for l in cliente.get("/api/lotes", headers=cabeceras("QF")).json() if l["codigo_lote"] == "A-2601")
    cliente.post(f"/api/lotes/{lote['id_lote']}/merma", headers=cabeceras("QF"),
                 json={"cantidad": lote["unidades_disp"], "motivo": "DANO"})
    baja = cliente.post(f"/api/medicamentos/{datos['medicamentos']['ATV20']}/baja", headers=cabeceras("QF"),
                        json={"motivo": "Discontinuado por el proveedor"})
    assert baja.status_code == 200, baja.text
    r = cliente.post("/api/recetas", headers=cabeceras("TECNICO"),
                     json=receta(datos, id_pac, ("ATV20", 30, "1 comprimido en la noche")))
    assert r.json()["codigo"] == "MEDICAMENTO_INACTIVO"


@pytest.mark.parametrize("cuerpo_extra", [
    {"lineas": []},                                                    # sin medicamentos
    {"folio": "RX 2001"},                                              # folio con espacio
    {"lineas": [{"id_medicamento": 1, "cant_prescrita": 0, "posologia": "1 al día"}]},
    {"medico": "Dr. House"},                                           # campo desconocido
])
def test_it45_entrada_mal_formada_se_rechaza(cliente, cabeceras, datos, cuerpo_extra):
    cuerpo = {**receta(datos, id_paciente(cliente, cabeceras), ("LOS50", 30, "1 cada 24 h")), **cuerpo_extra}
    assert cliente.post("/api/recetas", headers=cabeceras("TECNICO"), json=cuerpo).status_code == 422


@pytest.mark.parametrize("rol", ["BODEGUERO", "ADMIN"])
def test_it46_roles_sin_permiso_no_registran_recetas(cliente, cabeceras, datos, rol):
    cuerpo = receta(datos, id_paciente(cliente, cabeceras), ("LOS50", 30, "1 cada 24 h"))
    assert cliente.post("/api/recetas", headers=cabeceras(rol), json=cuerpo).status_code == 403
