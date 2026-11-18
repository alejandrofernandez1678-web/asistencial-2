"""Seed con volumen: seis meses de historia generados con los servicios quedan coherentes."""

from datetime import timedelta

from sqlalchemy import func, select

from app.db import Base, SesionLocal, motor
from app.models import (Dispensaciones, Faltantes, Lotes, MovimientosStock, Pacientes, Reclamos, Recetas,
                        SolicitudesDespacho, borrar_esquema)
from app.reloj import ahora, hoy
from app.seed import poblar
from app.services.dispensacion import verificar_libro
from app.services.indicadores import resumen_fofar


def test_it140_historia_de_seis_meses_coherente():
    borrar_esquema(motor)
    Base.metadata.create_all(motor)
    with SesionLocal() as db:
        resultado = poblar(db, hoy(), volumen=80)
        db.commit()
        h = resultado["historia"]
        assert h["pacientes"] == 80 and h["entregas"] > 200 and h["actividades"] > 20
        assert db.scalar(select(func.count()).select_from(Pacientes)) == 80 + 8

        # Las entregas quedaron repartidas en el pasado, no todas "hoy"
        primera = db.scalar(select(func.min(Dispensaciones.fecha_hora)))
        assert primera.date() < hoy() - timedelta(days=90)
        assert db.scalar(select(func.max(Dispensaciones.fecha_hora))).replace(tzinfo=None) <= ahora().replace(tzinfo=None)

        # Estado de cada receta coherente con lo entregado
        for receta in db.scalars(select(Recetas)).unique():
            entregado = [d.cant_entregada for d in receta.detalles]
            if all(c == 0 for c in entregado):
                assert receta.estado in ("PENDIENTE", "ANULADA")
            elif all(d.cant_entregada == d.cant_prescrita for d in receta.detalles):
                assert receta.estado == "DISPENSADA"
            else:
                assert receta.estado == "PARCIAL"

        # Kardex: el saldo de cada lote es el del último movimiento
        for lote in db.scalars(select(Lotes)).unique():
            ultimo = db.scalar(select(MovimientosStock.saldo_resultante).where(MovimientosStock.id_lote == lote.id_lote)
                               .order_by(MovimientosStock.id_movimiento.desc()).limit(1))
            assert ultimo == lote.unidades_disp, lote.codigo_lote

        assert verificar_libro(db)["integra"] is True
        # El quiebre de atorvastatina dejó compromisos cumplidos y reclamos cerrados con acta
        assert db.scalar(select(func.count()).select_from(Faltantes).where(Faltantes.estado == "ENTREGADO")) >= 1
        assert db.scalar(select(func.count()).select_from(SolicitudesDespacho)) > h["entregas"] - 1
        cerrados = db.scalars(select(Reclamos).where(Reclamos.estado == "RESUELTO")).all()
        assert all(r.recibe_nombre and r.fecha_solucion for r in cerrados)

        indicadores = resumen_fofar(db, hoy() - timedelta(days=180), hoy(), ahora())
        assert indicadores["despacho"]["solicitudes"] > 50 and 80 <= indicadores["despacho"]["porcentaje"] < 100
        assert indicadores["merma"]["merma_valorizada"] > 0 and indicadores["actividades"]["realizadas"] > 20
