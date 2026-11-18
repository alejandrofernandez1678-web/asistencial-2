"""Integración del esquema v0.5: datos CESFAM, entregas crónicas, paciente, catálogo y rol médico."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Apoderados, DespachosDomicilio, Dispensaciones, Recetas
from app.reloj import hoy


def buscar(cliente, cabeceras, rut):
    return cliente.post("/api/pacientes/buscar", json={"rut": rut}, headers=cabeceras("TECNICO")).json()


def receta(paciente, folio):
    return next(r for r in paciente["recetas"] if r["folio"] == folio)


# ------------------------------------------------------------- datos CESFAM
def test_it70_paciente_postrada_tiene_entrega_1_de_6_y_despacho_en_ruta(cliente, cabeceras, db):
    rosa = buscar(cliente, cabeceras, "7654321-6")
    assert rosa["paciente"]["es_postrado"] and rosa["paciente"]["sector"] == "Sector Rural"
    assert rosa["paciente"]["tiene_direccion"] and "direccion" not in rosa["paciente"]  # la dirección no se expone
    rx = receta(rosa, "RX-5001")
    assert (rx["tipo_receta"], rx["entregas_realizadas"], rx["total_entregas"]) == ("CRONICA", 1, 6)
    assert rx["proxima_fecha_retiro"] == (hoy() + timedelta(days=30)).isoformat()
    assert [d["pendiente"] for d in rx["detalles"]] == [150, 150, 300]

    despacho = db.scalars(select(DespachosDomicilio)).one()
    assert despacho.estado == "EN_RUTA" and despacho.dispensacion.numero_entrega == 1
    assert db.scalars(select(Apoderados)).one().parentesco == "Hija"


def test_it71_paciente_con_alergias_y_prais_se_informa_al_buscar(cliente, cabeceras):
    patricia = buscar(cliente, cabeceras, "16234567-2")["paciente"]
    assert "Penicilina" in patricia["alergias"]
    elena = buscar(cliente, cabeceras, "19876543-0")["paciente"]
    assert elena["es_prais"] and elena["tramo_fonasa"] == "A"


# ---------------------------------------------------------- entregas crónicas
def test_it72_entrega_cronica_completa_avanza_la_proxima_fecha(cliente, cabeceras):
    luis = buscar(cliente, cabeceras, "8123456-6")
    rx = receta(luis, "RX-5002")
    assert rx["proxima_fecha_retiro"] == (hoy() - timedelta(days=1)).isoformat()   # retiro atrasado un día
    cuerpo = {"id_receta": rx["id_receta"], "clave_idempotencia": uuid.uuid4().hex,
              "lineas": [{"id_detalle_receta": rx["detalles"][0]["id_detalle_receta"], "cantidad": 30,
                          "lotes_escaneados": ["AM-2605"]},
                         {"id_detalle_receta": rx["detalles"][1]["id_detalle_receta"], "cantidad": 15,
                          "lotes_escaneados": ["HC-2604"]}]}
    r = cliente.post("/api/dispensaciones", json=cuerpo, headers=cabeceras("TECNICO"))
    assert r.status_code == 201, r.text
    rx = receta(buscar(cliente, cabeceras, "8123456-6"), "RX-5002")
    assert (rx["entregas_realizadas"], rx["estado"]) == (1, "PARCIAL")
    assert rx["proxima_fecha_retiro"] == (hoy() + timedelta(days=30)).isoformat()


def test_it73_entrega_incompleta_por_quiebre_no_avanza_y_la_anulacion_revierte(cliente, cabeceras, db):
    rx = receta(buscar(cliente, cabeceras, "8123456-6"), "RX-5002")
    cuerpo = {"id_receta": rx["id_receta"], "clave_idempotencia": uuid.uuid4().hex,
              "lineas": [{"id_detalle_receta": rx["detalles"][0]["id_detalle_receta"], "cantidad": 30,
                          "lotes_escaneados": ["AM-2605"]}]}   # falta la hidroclorotiazida
    r = cliente.post("/api/dispensaciones", json=cuerpo, headers=cabeceras("TECNICO"))
    assert r.status_code == 201, r.text
    rx = receta(buscar(cliente, cabeceras, "8123456-6"), "RX-5002")
    assert rx["entregas_realizadas"] == 0 and rx["proxima_fecha_retiro"] == (hoy() - timedelta(days=1)).isoformat()
    assert db.get(Dispensaciones, r.json()["id_dispensacion"]).numero_entrega == 1

    anular = cliente.post(f"/api/dispensaciones/{r.json()['id_dispensacion']}/anular",
                          json={"motivo": "Se registró en la receta equivocada"}, headers=cabeceras("QF"))
    assert anular.status_code == 200 and anular.json()["estado_receta"] == "PENDIENTE"


def test_it74_la_base_impide_una_receta_retenida_con_varias_entregas(db):
    rx = db.scalars(select(Recetas).where(Recetas.folio == "RX-1003")).one()
    rx.total_entregas = 2
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_it75_retiro_por_apoderado_exige_el_apoderado_en_la_base(db):
    disp = db.scalars(select(Dispensaciones)).first()
    disp.retira_tipo = "APODERADO"   # sin id_apoderado
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --------------------------------------------------------- paciente y catálogo
def test_it76_registro_de_paciente_con_sector_prais_postrado_y_alergias(cliente, cabeceras):
    sectores = {s["nombre"]: s["id_sector"] for s in
                cliente.get("/api/catalogos", headers=cabeceras("TECNICO")).json()["sectores"]}
    base = {"rut": "11222333-9", "nombre": "Hugo Morales", "id_sector": sectores["Sector Azul"]}
    r = cliente.post("/api/pacientes", headers=cabeceras("TECNICO"),
                     json={**base, "direccion": "Calle Uno 123"})
    assert r.json()["codigo"] == "DIRECCION_SOLO_POSTRADO"
    r = cliente.post("/api/pacientes", headers=cabeceras("TECNICO"), json={
        **base, "es_postrado": True, "es_prais": True, "alergias": "Látex", "direccion": "Calle Uno 123"})
    assert r.status_code == 201, r.text
    assert (r.json()["sector"], r.json()["es_postrado"], r.json()["es_prais"], r.json()["alergias"]) == (
        "Sector Azul", True, True, "Látex")
    otro = cliente.post("/api/pacientes", headers=cabeceras("TECNICO"),
                        json={"rut": "22222222-2", "nombre": "Ida Paz", "id_sector": 999})
    assert otro.json()["codigo"] == "SECTOR_INVALIDO"


def test_it77_medicamento_con_datos_farmaceuticos(cliente, cabeceras):
    qf = cabeceras("QF")
    r = cliente.post("/api/medicamentos", headers=qf, json={
        "codigo": "AMX500", "nombre": "Amoxicilina 500 mg cápsulas", "principio_activo": "Amoxicilina",
        "concentracion": "500 mg", "forma_farmaceutica": "CAPSULA", "unidad_dispensacion": "CAPSULA",
        "unidades_envase": 21})
    assert r.status_code == 201, r.text
    assert (r.json()["principio_activo"], r.json()["forma_farmaceutica"]) == ("Amoxicilina", "CAPSULA")
    malo = cliente.post("/api/medicamentos", headers=qf, json={
        "codigo": "AMX250", "nombre": "Amoxicilina 250 mg", "forma_farmaceutica": "POLVO_MAGICO", "unidades_envase": 1})
    assert malo.json()["codigo"] == "FORMA_INVALIDA"
    catalogo = cliente.get("/api/catalogos", headers=qf).json()
    assert {"codigo": "INHALADOR", "nombre": "Inhalador"} in catalogo["formas_farmaceuticas"]


# ---------------------------------------------------------------- rol médico
def test_it78_medico_emite_recetas_pero_no_dispensa(cliente, cabeceras, datos, db):
    login = cliente.post("/api/auth/login", json={"rut": "13579246-2", "password": "Farmacia2026!"})
    medico = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert cliente.get("/api/auth/yo", headers=medico).json()["rol"] == "MEDICO"
    r = cliente.post("/api/recetas", headers=medico, json={
        "id_paciente": buscar(cliente, cabeceras, "14141414-3")["paciente"]["id_paciente"], "folio": "RX-9001",
        "fecha_emision": hoy().isoformat(),
        "lineas": [{"id_medicamento": datos["medicamentos"]["LOS50"], "cant_prescrita": 30, "posologia": "1 al día"}]})
    assert r.status_code == 201, r.text
    assert db.get(Recetas, r.json()["id_receta"]).id_medico == datos["usuarios"]["MEDICO"]
    dispensa = cliente.post("/api/dispensaciones", headers=medico, json={
        "id_receta": r.json()["id_receta"], "clave_idempotencia": uuid.uuid4().hex,
        "lineas": [{"id_detalle_receta": r.json()["detalles"][0]["id_detalle_receta"], "cantidad": 30}]})
    assert dispensa.status_code == 403
