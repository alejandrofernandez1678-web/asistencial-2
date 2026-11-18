"""Fuente única de fecha y hora, para poder fijarla en las pruebas y en los datos de demostración."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

_desfase = timedelta(0)


def ahora() -> datetime:
    return datetime.now(UTC) + _desfase


def hoy() -> date:
    return (datetime.now() + _desfase).date()


@contextmanager
def simular(momento: datetime) -> Iterator[None]:
    """Hace que ahora() devuelva `momento` (y que el tiempo siga corriendo desde ahí).

    Solo para el seed con historia: permite registrar entregas, mermas y reclamos
    "en el pasado" usando los mismos servicios que la aplicación. Nunca se usa en la API.
    """
    global _desfase
    anterior = _desfase
    _desfase = momento - datetime.now(UTC)
    try:
        yield
    finally:
        _desfase = anterior


def iso_utc(momento: datetime | None) -> str | None:
    """ISO 8601 con zona: SQLite devuelve las fechas sin zona aunque se guardaron en UTC."""
    if momento is None:
        return None
    return (momento.replace(tzinfo=UTC) if momento.tzinfo is None else momento).isoformat()
