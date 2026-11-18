"""Acceso a datos de lotes (consulta FEFO del Código 2 del informe)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.fefo import LoteFEFO
from ..models import Lotes


def lotes_de_medicamento(db: Session, id_medicamento: int, *, bloquear: bool = False) -> list[Lotes]:
    """Lotes con stock del medicamento en orden FEFO.

    Con bloquear=True usa SELECT ... FOR UPDATE: dos dispensaciones
    simultáneas del mismo medicamento se atienden una después de la otra y
    el stock no puede quedar negativo (en SQLite la escritura ya es exclusiva).
    """
    consulta = (select(Lotes)
                .where(Lotes.id_medicamento == id_medicamento, Lotes.unidades_disp > 0)
                .order_by(Lotes.fecha_vencimiento, Lotes.id_lote))
    if bloquear:
        consulta = consulta.with_for_update(of=Lotes)
    return list(db.scalars(consulta).unique())


def a_lote_fefo(lote: Lotes) -> LoteFEFO:
    return LoteFEFO(id_lote=lote.id_lote, codigo_lote=lote.codigo_lote, id_medicamento=lote.id_medicamento,
                    fecha_vencimiento=lote.fecha_vencimiento, unidades_disp=lote.unidades_disp,
                    ubicacion=lote.ubicacion.codigo, estado_registro=lote.estado)
