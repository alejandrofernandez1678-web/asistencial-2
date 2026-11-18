"""Plazos en horas hábiles (FOFAR: reclamos y faltantes se resuelven en 24 horas hábiles).

"24 horas hábiles" cuenta el tiempo corrido de los días hábiles: no corre los sábados,
domingos ni feriados. Un faltante registrado el viernes a las 10:00 vence el lunes a
las 10:00; uno registrado un sábado empieza a correr el lunes a las 00:00.

FERIADOS_CHILE contiene los feriados nacionales de 2026 y 2027 (Ley 2.977 y sus
modificaciones). Se revisa cada año con el calendario oficial: los feriados que
se trasladan (San Pedro y San Pablo, Encuentro de Dos Mundos) cambian de fecha.
"""

from datetime import date, datetime, time, timedelta

PLAZO_FOFAR_HORAS = 24

FERIADOS_CHILE: dict[date, str] = {
    date(2026, 1, 1): "Año Nuevo", date(2026, 4, 3): "Viernes Santo", date(2026, 4, 4): "Sábado Santo",
    date(2026, 5, 1): "Día del Trabajo", date(2026, 5, 21): "Día de las Glorias Navales",
    date(2026, 6, 21): "Día de los Pueblos Indígenas", date(2026, 6, 29): "San Pedro y San Pablo",
    date(2026, 7, 16): "Virgen del Carmen", date(2026, 8, 15): "Asunción de la Virgen",
    date(2026, 9, 18): "Independencia Nacional", date(2026, 9, 19): "Glorias del Ejército",
    date(2026, 10, 12): "Encuentro de Dos Mundos", date(2026, 10, 31): "Iglesias Evangélicas y Protestantes",
    date(2026, 11, 1): "Todos los Santos", date(2026, 12, 8): "Inmaculada Concepción", date(2026, 12, 25): "Navidad",
    date(2027, 1, 1): "Año Nuevo", date(2027, 3, 26): "Viernes Santo", date(2027, 3, 27): "Sábado Santo",
    date(2027, 5, 1): "Día del Trabajo", date(2027, 5, 21): "Día de las Glorias Navales",
    date(2027, 6, 21): "Día de los Pueblos Indígenas", date(2027, 6, 28): "San Pedro y San Pablo",
    date(2027, 7, 16): "Virgen del Carmen", date(2027, 8, 15): "Asunción de la Virgen",
    date(2027, 9, 18): "Independencia Nacional", date(2027, 9, 19): "Glorias del Ejército",
    date(2027, 10, 11): "Encuentro de Dos Mundos", date(2027, 10, 31): "Iglesias Evangélicas y Protestantes",
    date(2027, 11, 1): "Todos los Santos", date(2027, 12, 8): "Inmaculada Concepción", date(2027, 12, 25): "Navidad",
}


def es_dia_habil(dia: date, feriados=FERIADOS_CHILE) -> bool:
    return dia.weekday() < 5 and dia not in feriados


def sumar_horas_habiles(inicio: datetime, horas: float = PLAZO_FOFAR_HORAS, feriados=FERIADOS_CHILE) -> datetime:
    """Momento en que se cumplen `horas` hábiles contadas desde `inicio` (con su zona horaria)."""
    restante = timedelta(hours=horas)
    actual = inicio
    while True:
        medianoche = datetime.combine(actual.date() + timedelta(days=1), time.min, tzinfo=actual.tzinfo)
        if es_dia_habil(actual.date(), feriados):
            disponible = medianoche - actual
            if restante <= disponible:
                return actual + restante
            restante -= disponible
        actual = medianoche


def horas_habiles_entre(inicio: datetime, fin: datetime, feriados=FERIADOS_CHILE) -> float:
    """Horas hábiles transcurridas entre dos momentos (0 si fin <= inicio)."""
    total = timedelta()
    actual = inicio
    while actual < fin:
        medianoche = datetime.combine(actual.date() + timedelta(days=1), time.min, tzinfo=actual.tzinfo)
        tramo_fin = min(medianoche, fin)
        if es_dia_habil(actual.date(), feriados):
            total += tramo_fin - actual
        actual = tramo_fin
    return total.total_seconds() / 3600
