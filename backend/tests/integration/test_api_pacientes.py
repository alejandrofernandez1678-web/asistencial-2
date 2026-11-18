"""Integración: registro de pacientes (RF-04)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import EventosPendientes, Pacientes
from app.reloj import hoy

RUT_NUEVO = "11222333-9"


def programas(cliente, cabeceras):
    return {p["nombre"]: p["id_programa"]
            for p in cliente.get("/api/catalogos", headers=cabeceras("TECNICO")).json()["programas"]}


def test_it30_tecnico_registra_paciente_y_luego_lo_encuentra(cliente, cabeceras, db):
    ids = programas(cliente, cabeceras)
    r = cliente.post("/api/pacientes", headers=cabeceras("TECNICO"), json={
        "rut": "11.222.333-9", "nombre": "Pedro Rojas", "fecha_nacimiento": "1960-04-12",
        "tramo_fonasa": "C", "programas": [ids["Diabetes"], ids["Cardiovascular"]]})
    assert r.status_code == 201, r.text
    assert r.json()["rut"] == "11.222.***-9"
    assert sorted(r.json()["programas"]) == ["Cardiovascular", "Diabetes"]

    buscado = cliente.post("/api/pacientes/buscar", json={"rut": RUT_NUEVO}, headers=cabeceras("TECNICO"))
    assert buscado.status_code == 200
    assert buscado.json()["paciente"]["nombre"] == "Pedro Rojas" and buscado.json()["recetas"] == []

    paciente = db.scalars(select(Pacientes).where(Pacientes.nombre == "Pedro Rojas")).one()
    assert RUT_NUEVO.split("-")[0] not in paciente.rut_hmac  # el RUT no se guarda en claro
    evento = db.scalars(select(EventosPendientes).where(EventosPendientes.tipo_evento == "PACIENTE_CREADO")).one()
    assert evento.id_entidad == paciente.id_paciente and RUT_NUEVO not in str(evento.payload)


def test_it31_qf_registra_paciente_solo_con_datos_minimos(cliente, cabeceras):
    r = cliente.post("/api/pacientes", headers=cabeceras("QF"), json={"rut": RUT_NUEVO, "nombre": "Rosa Díaz"})
    assert r.status_code == 201, r.text
    assert r.json()["programas"] == [] and r.json()["tramo_fonasa"] is None


def test_it32_rut_ya_registrado_se_rechaza(cliente, cabeceras):
    r = cliente.post("/api/pacientes", headers=cabeceras("TECNICO"), json={"rut": "12345678-5", "nombre": "Otra María"})
    assert r.status_code == 422 and r.json()["codigo"] == "RUT_DUPLICADO"


@pytest.mark.parametrize("cambios,codigo", [
    ({"rut": "11222333-0"}, "RUT_INVALIDO"),
    ({"fecha_nacimiento": (hoy() + timedelta(days=1)).isoformat()}, "FECHA_INVALIDA"),
    ({"programas": [9999]}, "PROGRAMA_INVALIDO"),
])
def test_it33_datos_invalidos_se_rechazan(cliente, cabeceras, cambios, codigo):
    cuerpo = {"rut": RUT_NUEVO, "nombre": "Pedro Rojas", **cambios}
    r = cliente.post("/api/pacientes", headers=cabeceras("TECNICO"), json=cuerpo)
    assert r.status_code == 422 and r.json()["codigo"] == codigo


@pytest.mark.parametrize("cuerpo", [
    {"rut": RUT_NUEVO, "nombre": "Pe"},                                 # nombre muy corto
    {"rut": RUT_NUEVO, "nombre": "Pedro Rojas", "tramo_fonasa": "Z"},   # tramo inexistente
    {"rut": RUT_NUEVO, "nombre": "Pedro Rojas", "prevision": "ISAPRE"}, # campo desconocido
])
def test_it34_entrada_mal_formada_se_rechaza(cliente, cabeceras, cuerpo):
    assert cliente.post("/api/pacientes", headers=cabeceras("TECNICO"), json=cuerpo).status_code == 422


@pytest.mark.parametrize("rol", ["BODEGUERO", "ADMIN"])
def test_it35_roles_sin_permiso_no_registran_pacientes(cliente, cabeceras, rol):
    r = cliente.post("/api/pacientes", headers=cabeceras(rol), json={"rut": RUT_NUEVO, "nombre": "Pedro Rojas"})
    assert r.status_code == 403
