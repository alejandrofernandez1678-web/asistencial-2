"""Ciclo de vida del lote (RN-01, RN-02, RN-03) y alerta de recepción.

Los estados coinciden con el diagrama de estados de la clase Lotes:
  VIGENTE (> 60 días) y ALERTA (<= 60 días) forman el estado compuesto
  "Dispensable"; NO_DISPENSABLE (<= 30 días); RETIRO_OBLIGATORIO
  (<= 14 días); AGOTADO (sin unidades); ALERTA_SANITARIA (bloqueo ISP);
  MERMA (retirado) y ANULADO (lote mal ingresado, dado de baja).
"""

from calendar import monthrange
from datetime import date
from enum import StrEnum


DIAS_ALERTA = 60            # RN-01
DIAS_NO_DISPENSABLE = 30    # RN-02
DIAS_RETIRO = 14            # RN-03
MESES_ALERTA_RECEPCION = 6  # RF-07


class EstadosLote(StrEnum):
    VIGENTE = "VIGENTE"
    ALERTA = "ALERTA"
    NO_DISPENSABLE = "NO_DISPENSABLE"
    RETIRO_OBLIGATORIO = "RETIRO_OBLIGATORIO"
    AGOTADO = "AGOTADO"
    ALERTA_SANITARIA = "ALERTA_SANITARIA"
    MERMA = "MERMA"
    ANULADO = "ANULADO"


class EstadosRegistroLote(StrEnum):
    """Estado persistido en la tabla lotes (el resto se calcula por fecha)."""
    DISPONIBLE = "DISPONIBLE"
    ALERTA_SANITARIA = "ALERTA_SANITARIA"
    MERMA = "MERMA"
    ANULADO = "ANULADO"


DISPENSABLES = frozenset({EstadosLote.VIGENTE, EstadosLote.ALERTA})


def dias_para_vencer(fecha_vencimiento: date, hoy: date) -> int:
    return (fecha_vencimiento - hoy).days


def estado_lote(fecha_vencimiento: date, unidades: int, hoy: date,
                estado_registro: str = EstadosRegistroLote.DISPONIBLE) -> EstadosLote:
    if estado_registro != EstadosRegistroLote.DISPONIBLE:
        return EstadosLote(estado_registro)
    if unidades <= 0:
        return EstadosLote.AGOTADO
    dias = dias_para_vencer(fecha_vencimiento, hoy)
    if dias <= DIAS_RETIRO:
        return EstadosLote.RETIRO_OBLIGATORIO
    if dias <= DIAS_NO_DISPENSABLE:
        return EstadosLote.NO_DISPENSABLE
    if dias <= DIAS_ALERTA:
        return EstadosLote.ALERTA
    return EstadosLote.VIGENTE


def es_dispensable(estado: EstadosLote) -> bool:
    return estado in DISPENSABLES


def sumar_meses(fecha: date, meses: int) -> date:
    mes_total = fecha.month - 1 + meses
    anio, mes = fecha.year + mes_total // 12, mes_total % 12 + 1
    return date(anio, mes, min(fecha.day, monthrange(anio, mes)[1]))


def vencimiento_corto_en_recepcion(fecha_vencimiento: date, hoy: date) -> bool:
    """RF-07: alerta si el lote recibido vence antes de 6 meses."""
    return fecha_vencimiento < sumar_meses(hoy, MESES_ALERTA_RECEPCION)
