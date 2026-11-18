"""Concurrencia (criterio de salida de la Tabla 28: "sin stock negativo en concurrencia").

Solo se ejecuta sobre PostgreSQL, que tiene bloqueo por fila (SELECT ... FOR UPDATE).
"""

import threading

import pytest
from sqlalchemy import select

from app.db import motor
from app.models import Dispensaciones, Lotes

pytestmark = pytest.mark.skipif(motor.dialect.name != "postgresql",
                                reason="requiere PostgreSQL (SISGEF_PRUEBAS_DATABASE_URL)")

PARALELO = 8


def test_it40_misma_receta_atendida_en_paralelo_se_entrega_una_sola_vez(cliente, cabeceras, datos, db):
    tecnico = cabeceras("TECNICO")
    barrera = threading.Barrier(PARALELO)
    estados: list[int] = []

    def atender(i: int):
        cuerpo = {"id_receta": datos["recetas"]["RX-1001"], "clave_idempotencia": f"concurrencia-{i:04d}",
                  "lineas": [{"id_detalle_receta": datos["detalles"]["RX-1001"][0], "cantidad": 30,
                              "lotes_escaneados": ["L-2502"]}]}
        barrera.wait()  # todos los técnicos confirman exactamente al mismo tiempo
        estados.append(cliente.post("/api/dispensaciones", json=cuerpo, headers=tecnico).status_code)

    hilos = [threading.Thread(target=atender, args=(i,)) for i in range(PARALELO)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sorted(estados) == [201] + [422] * (PARALELO - 1)
    assert db.scalar(select(Lotes.unidades_disp).where(Lotes.codigo_lote == "L-2502")) == 30
    assert len(db.scalars(select(Dispensaciones).where(
        Dispensaciones.id_receta == datos["recetas"]["RX-1001"])).all()) == 1
