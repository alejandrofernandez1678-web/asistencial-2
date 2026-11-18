"""Series de tiempo para los gráficos del panel, los indicadores y las alertas.

Las fechas se agrupan en la hora local del CESFAM (SQLite guarda UTC sin zona).
"""

from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.lotes import sumar_meses
from ..models import ActividadesFarmaceuticas, DetallesDispensacion, Dispensaciones, Lotes, ProgramacionActividades
from .indicadores import despacho_oportuno, merma_valorizada
from .inventario import costo_unitario
from .reportes import validar_rango

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _local(momento: datetime) -> date:
    return (momento.replace(tzinfo=UTC) if momento.tzinfo is None else momento).astimezone().date()


def _etiqueta_mes(anio: int, mes: int) -> str:
    return f"{MESES[mes - 1]} {anio}"


def entregas_por_dia(db: Session, hoy: date, dias: int = 30) -> list[dict]:
    """Entregas vigentes y unidades entregadas por día, incluidos los días sin entregas."""
    desde = hoy - timedelta(days=dias - 1)
    inicio = datetime.combine(desde, time.min).astimezone(UTC)
    por_dia = defaultdict(lambda: {"entregas": set(), "unidades": 0})
    for disp_id, fecha_hora, cantidad in db.execute(
            select(Dispensaciones.id_dispensacion, Dispensaciones.fecha_hora, DetallesDispensacion.cantidad)
            .join(DetallesDispensacion, DetallesDispensacion.id_dispensacion == Dispensaciones.id_dispensacion)
            .where(Dispensaciones.estado == "VIGENTE", Dispensaciones.fecha_hora >= inicio)):
        dia = por_dia[_local(fecha_hora)]
        dia["entregas"].add(disp_id)
        dia["unidades"] += cantidad
    return [{"fecha": d.isoformat(), "entregas": len(por_dia[d]["entregas"]), "unidades": por_dia[d]["unidades"]}
            for d in (desde + timedelta(days=i) for i in range(dias))]


def fofar_mensual(db: Session, desde: date, hasta: date) -> dict:
    """Indicadores 1 y 3 mes a mes dentro del período, y las actividades del año de `hasta` acumuladas por mes."""
    validar_rango(desde, hasta)
    filas = []
    mes = desde.replace(day=1)
    while mes <= hasta:
        primero, ultimo = max(mes, desde), min(mes.replace(day=monthrange(mes.year, mes.month)[1]), hasta)
        despacho = despacho_oportuno(db, primero, ultimo)
        merma = merma_valorizada(db, primero, ultimo)
        filas.append({"mes": primero.isoformat()[:7], "etiqueta": _etiqueta_mes(primero.year, primero.month),
                      "solicitudes": despacho["solicitudes"], "despacho": despacho["porcentaje"],
                      "sin_stock": despacho["sin_stock"], "merma": merma["porcentaje"],
                      "merma_valorizada": merma["merma_valorizada"]})
        mes = sumar_meses(mes, 1)
    hoy = hasta
    fechas = db.scalars(select(ActividadesFarmaceuticas.fecha).where(
        ActividadesFarmaceuticas.estado == "VIGENTE", ActividadesFarmaceuticas.fecha >= date(hoy.year, 1, 1),
        ActividadesFarmaceuticas.fecha <= hoy)).all()
    por_mes = defaultdict(int)
    for f in fechas:
        por_mes[f.month] += 1
    acumulado, actividades = 0, []
    for mes in range(1, hoy.month + 1):
        acumulado += por_mes[mes]
        actividades.append({"mes": f"{hoy.year}-{mes:02d}", "etiqueta": _etiqueta_mes(hoy.year, mes),
                            "realizadas": por_mes[mes], "acumuladas": acumulado})
    programacion = db.get(ProgramacionActividades, hoy.year)
    return {"meses": filas, "actividades": actividades, "programadas": programacion.cantidad if programacion else None}


def vencimientos_por_mes(db: Session, hoy: date, meses: int = 6) -> list[dict]:
    """Stock que vence en cada uno de los próximos meses (unidades, valor y lotes)."""
    limite = sumar_meses(hoy.replace(day=1), meses)
    grupos = defaultdict(lambda: {"unidades": 0, "valor": 0.0, "lotes": 0, "sin_costo": 0})
    for lote in db.scalars(select(Lotes).where(Lotes.unidades_disp > 0, Lotes.fecha_vencimiento < limite,
                                               Lotes.estado.in_(["DISPONIBLE", "ALERTA_SANITARIA"]))).unique():
        clave = (max(lote.fecha_vencimiento, hoy).year, max(lote.fecha_vencimiento, hoy).month)
        g = grupos[clave]
        g["unidades"] += lote.unidades_disp
        g["lotes"] += 1
        costo = costo_unitario(lote)
        if costo is None:
            g["sin_costo"] += 1
        else:
            g["valor"] += lote.unidades_disp * costo
    resultado = []
    for i in range(meses):
        mes = sumar_meses(hoy.replace(day=1), i)
        g = grupos[(mes.year, mes.month)]
        resultado.append({"mes": mes.isoformat()[:7], "etiqueta": _etiqueta_mes(mes.year, mes.month),
                          "unidades": g["unidades"], "valor": round(g["valor"]), "lotes": g["lotes"],
                          "sin_costo": g["sin_costo"]})
    return resultado
