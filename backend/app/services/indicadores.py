"""Indicadores del Programa Fondo de Farmacia (OT FOFAR, sección 4.2).

  1. Recetas con despacho total y oportuno (meta 100 %): solicitudes del período de
     recetas del Programa de Salud Cardiovascular (HTA, DM2 y dislipidemia: programas
     Cardiovascular y Diabetes) entregadas completas en el momento. El rechazo del
     paciente no cuenta como incumplimiento; se informa aparte.
  2. Reclamos con solución en menos de 24 horas hábiles (meta 100 %). Los reclamos
     no atingentes al programa quedan fuera.
  3. Merma valorizada / inventario valorizado (meta <= 0,99 %), sin insulinas. El
     inventario se valoriza al cierre del período, reconstruido desde el kardex.
  4. Actividades farmacéuticas realizadas / programadas en el año (meta 50 % a junio
     y 100 % a diciembre).
"""

from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (ActividadesFarmaceuticas, Faltantes, Lotes, Medicamentos, MovimientosStock,
                      ProgramacionActividades, Reclamos, SolicitudesDespacho)
from .inventario import costo_unitario
from .reportes import a_csv, validar_rango

PROGRAMAS_PSCV = ("Cardiovascular", "Diabetes")
META_MERMA = 0.99


def _utc(momento: datetime) -> datetime:
    return momento.replace(tzinfo=UTC) if momento.tzinfo is None else momento


def _porcentaje(parte: float, total: float) -> float | None:
    return round(parte * 100 / total, 1) if total else None


def _es_pscv(solicitud: SolicitudesDespacho) -> bool:
    return any(l.get("programa") in PROGRAMAS_PSCV for l in solicitud.detalle)


def _solicitudes_pscv(db: Session, desde: date, hasta: date) -> list[SolicitudesDespacho]:
    inicio, fin = validar_rango(desde, hasta)
    filas = db.scalars(select(SolicitudesDespacho).where(
        SolicitudesDespacho.estado == "VIGENTE", SolicitudesDespacho.fecha_hora >= inicio,
        SolicitudesDespacho.fecha_hora < fin).order_by(SolicitudesDespacho.id_solicitud)).unique()
    return [s for s in filas if _es_pscv(s)]


def _faltantes_de(db: Session, solicitudes: list[SolicitudesDespacho]) -> list[Faltantes]:
    ids = [s.id_solicitud for s in solicitudes]
    if not ids:
        return []
    return list(db.scalars(select(Faltantes).where(Faltantes.id_solicitud.in_(ids))).unique())


def _dias(f: Faltantes) -> float:
    return (_utc(f.fecha_solucion) - _utc(f.fecha_registro)).total_seconds() / 86400


def despacho_oportuno(db: Session, desde: date, hasta: date) -> dict:
    solicitudes = _solicitudes_pscv(db, desde, hasta)
    por_resultado = defaultdict(int)
    for s in solicitudes:
        por_resultado[s.resultado] += 1
    cumplidas = por_resultado["COMPLETA"] + por_resultado["RECHAZO"]
    brechas = defaultdict(lambda: {"faltantes": 0, "entregados_despues": 0, "pendientes": 0, "dias": []})
    for f in _faltantes_de(db, solicitudes):
        if f.motivo != "SIN_STOCK" or f.estado == "ANULADO":
            continue
        b = brechas[f.detalle_receta.medicamento.nombre]
        b["faltantes"] += 1
        if f.estado == "ENTREGADO":
            b["entregados_despues"] += 1
            b["dias"].append(_dias(f))
        else:
            b["pendientes"] += 1
    return {"solicitudes": len(solicitudes), "cumplidas": cumplidas, "completas": por_resultado["COMPLETA"],
            "sin_stock": por_resultado["SIN_STOCK"], "rechazo_paciente": por_resultado["RECHAZO"],
            "porcentaje": _porcentaje(cumplidas, len(solicitudes)), "meta": 100,
            "cumple": bool(solicitudes) and cumplidas == len(solicitudes),
            "brechas": sorted(({"medicamento": m, "faltantes": b["faltantes"], "entregados_despues": b["entregados_despues"],
                                "pendientes": b["pendientes"],
                                "dias_promedio": round(sum(b["dias"]) / len(b["dias"]), 1) if b["dias"] else None}
                               for m, b in brechas.items()), key=lambda x: -x["faltantes"])}


def reclamos_24_horas(db: Session, desde: date, hasta: date, momento: datetime) -> dict:
    inicio, fin = validar_rango(desde, hasta)
    reclamos = db.scalars(select(Reclamos).where(Reclamos.fecha_reclamo >= inicio, Reclamos.fecha_reclamo < fin,
                                                 Reclamos.estado != "NO_ATINGENTE")).unique().all()
    en_plazo = fuera = en_curso = 0
    for r in reclamos:
        plazo = _utc(r.plazo)
        if r.estado == "RESUELTO":
            if _utc(r.fecha_solucion) <= plazo:
                en_plazo += 1
            else:
                fuera += 1
        elif momento > plazo:
            fuera += 1
        else:
            en_curso += 1
    return {"reclamos": len(reclamos), "resueltos_en_plazo": en_plazo, "fuera_de_plazo": fuera, "en_curso": en_curso,
            "porcentaje": _porcentaje(en_plazo, len(reclamos)), "meta": 100,
            "cumple": fuera == 0 and en_curso == 0}


def _es_insulina(med: Medicamentos) -> bool:
    return (med.principio_activo or med.nombre).lower().startswith("insulina")


def merma_valorizada(db: Session, desde: date, hasta: date) -> dict:
    inicio, fin = validar_rango(desde, hasta)
    merma, sin_costo = 0.0, 0
    for mov, lote in db.execute(select(MovimientosStock, Lotes).join(Lotes, Lotes.id_lote == MovimientosStock.id_lote)
                                .where(MovimientosStock.tipo == "MERMA", MovimientosStock.fecha_hora >= inicio,
                                       MovimientosStock.fecha_hora < fin)).unique():
        if _es_insulina(lote.medicamento):
            continue
        costo = costo_unitario(lote)
        if costo is None:
            sin_costo += 1
        else:
            merma += -mov.cantidad * costo
    # Saldo de cada lote al cierre del período: el del último movimiento anterior al cierre.
    ultimo = (select(MovimientosStock.id_lote, func.max(MovimientosStock.id_movimiento).label("id_mov"))
              .where(MovimientosStock.fecha_hora < fin).group_by(MovimientosStock.id_lote).subquery())
    inventario, lotes_sin_costo = 0.0, 0
    for saldo, lote in db.execute(select(MovimientosStock.saldo_resultante, Lotes)
                                  .join(ultimo, ultimo.c.id_mov == MovimientosStock.id_movimiento)
                                  .join(Lotes, Lotes.id_lote == MovimientosStock.id_lote)).unique():
        if saldo <= 0 or _es_insulina(lote.medicamento):
            continue
        costo = costo_unitario(lote)
        if costo is None:
            lotes_sin_costo += 1
        else:
            inventario += saldo * costo
    porcentaje = round(merma * 100 / inventario, 2) if inventario else None
    return {"merma_valorizada": round(merma), "inventario_valorizado": round(inventario), "porcentaje": porcentaje,
            "meta": META_MERMA, "cumple": porcentaje is not None and porcentaje <= META_MERMA,
            "mermas_sin_costo": sin_costo, "lotes_sin_costo": lotes_sin_costo}


def actividades_farmaceuticas(db: Session, hasta: date) -> dict:
    anio = hasta.year
    filas = db.execute(select(ActividadesFarmaceuticas.tipo, func.count())
                       .where(ActividadesFarmaceuticas.estado == "VIGENTE",
                              ActividadesFarmaceuticas.fecha >= date(anio, 1, 1),
                              ActividadesFarmaceuticas.fecha <= hasta)
                       .group_by(ActividadesFarmaceuticas.tipo)).all()
    por_tipo = {tipo: cantidad for tipo, cantidad in filas}
    realizadas = sum(por_tipo.values())
    programacion = db.get(ProgramacionActividades, anio)
    programadas = programacion.cantidad if programacion else None
    meta = 50 if hasta <= date(anio, 6, 30) else 100
    porcentaje = _porcentaje(realizadas, programadas) if programadas else None
    return {"anio": anio, "realizadas": realizadas, "programadas": programadas, "porcentaje": porcentaje,
            "meta": meta, "cumple": porcentaje is not None and porcentaje >= meta, "por_tipo": por_tipo}


def resumen_fofar(db: Session, desde: date, hasta: date, momento: datetime) -> dict:
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "despacho": despacho_oportuno(db, desde, hasta),
            "reclamos": reclamos_24_horas(db, desde, hasta, momento),
            "merma": merma_valorizada(db, desde, hasta),
            "actividades": actividades_farmaceuticas(db, hasta)}


def rem_a04_j(db: Session, desde: date, hasta: date) -> str:
    """Base para el REM A04 sección J (recetas cardiovasculares), por medicamento.

    Oportunidad: lo que faltó y se entregó después. Completitud: lo que aún no se entrega.
    """
    solicitudes = _solicitudes_pscv(db, desde, hasta)
    faltantes = {(f.id_solicitud, f.id_detalle_receta): f for f in _faltantes_de(db, solicitudes)
                 if f.estado != "ANULADO"}
    filas = defaultdict(lambda: {"programa": "", "solicitadas": 0, "oportunas": 0, "oportunidad": 0,
                                 "completitud": 0, "rechazo": 0, "dias": []})
    for s in solicitudes:
        for linea in s.detalle:
            fila = filas[linea["medicamento"]]
            fila["programa"] = linea.get("programa") or "Sin programa"
            fila["solicitadas"] += 1
            if linea["entregada"] >= linea["corresponde"]:
                fila["oportunas"] += 1
                continue
            f = faltantes.get((s.id_solicitud, linea["id_detalle_receta"]))
            if linea.get("motivo") == "RECHAZO_PACIENTE":
                fila["rechazo"] += 1
            elif f is not None and f.estado == "ENTREGADO":
                fila["oportunidad"] += 1
                fila["dias"].append(_dias(f))
            else:
                fila["completitud"] += 1
    return a_csv(["Programa", "Medicamento", "Solicitadas", "Despacho total y oportuno",
                  "Incumplida por oportunidad (entregada después)", "Incumplida por completitud (pendiente)",
                  "Rechazo del paciente", "Días promedio de demora"],
                 [[f["programa"], medicamento, f["solicitadas"], f["oportunas"], f["oportunidad"], f["completitud"],
                   f["rechazo"], str(round(sum(f["dias"]) / len(f["dias"]), 1)).replace(".", ",") if f["dias"] else ""]
                  for medicamento, f in sorted(filas.items(), key=lambda x: (x[1]["programa"], x[0]))])
