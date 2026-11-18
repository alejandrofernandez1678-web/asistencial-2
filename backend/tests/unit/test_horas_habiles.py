"""Plazos FOFAR de 24 horas hábiles: no corren sábados, domingos ni feriados."""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.horas_habiles import es_dia_habil, horas_habiles_entre, sumar_horas_habiles

CHILE = timezone(timedelta(hours=-3))


def momento(texto: str) -> datetime:
    return datetime.fromisoformat(texto).replace(tzinfo=CHILE)


@pytest.mark.parametrize("inicio,plazo", [
    ("2026-11-17T10:00", "2026-11-18T10:00"),   # martes -> miércoles
    ("2026-11-20T10:00", "2026-11-23T10:00"),   # viernes -> lunes (el fin de semana no corre)
    ("2026-11-21T15:30", "2026-11-24T00:00"),   # sábado: empieza a correr el lunes 00:00
    ("2026-12-07T09:00", "2026-12-09T09:00"),   # lunes; el martes 8 es feriado (Inmaculada Concepción)
    ("2026-09-17T18:00", "2026-09-21T18:00"),   # jueves; 18 y 19 de septiembre y domingo no corren
])
def test_u40_sumar_24_horas_habiles(inicio, plazo):
    assert sumar_horas_habiles(momento(inicio)) == momento(plazo)


def test_u41_horas_habiles_entre_descuenta_fin_de_semana():
    assert horas_habiles_entre(momento("2026-11-20T10:00"), momento("2026-11-23T10:00")) == 24
    assert horas_habiles_entre(momento("2026-11-23T10:00"), momento("2026-11-20T10:00")) == 0


def test_u42_dias_habiles():
    assert es_dia_habil(momento("2026-11-17T00:00").date())
    assert not es_dia_habil(momento("2026-11-22T00:00").date())          # domingo
    assert not es_dia_habil(momento("2026-12-25T00:00").date())          # Navidad
